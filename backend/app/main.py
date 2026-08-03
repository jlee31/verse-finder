"""The HTTP surface: one-shot RAG, the agent, and the LIME explainer.

Two retrieval endpoints on purpose. `/api/verses/search` is the original
pipeline — one embedding lookup, one generation — and stays exactly as it was,
because it is the baseline every claim about the agent is measured against.
`/api/verses/search/agentic` runs the Stage 2/3 loop, which searches as many
times as it takes and reports what it searched for.

The trace is the reason the agentic response has its own shape. A one-shot
lookup has nothing to show; the agent's decision to search again for the facet
it missed is the whole product, so it goes in the payload rather than the logs.
"""
import importlib.util
from contextlib import asynccontextmanager
from enum import Enum
from importlib import import_module
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv() # get the anthropic api key


# --------------------------------------------------------------------------
# lazy imports
# --------------------------------------------------------------------------

_loaded: dict[str, object] = {}


def _lazy(module: str, attr: str):
    """Import `module.attr` on first use, then cache it.

    Importing `app.rag.retriever` loads the mpnet model and the embedding
    matrix (~20s), and `app.rag.agent_lc` drags in all of LangChain. At module
    scope that cost lands on anything that so much as imports this file —
    including the API tests, which then couldn't run in the fast suite.

    The server still pays it up front: `lifespan` below warms the retriever at
    startup so the first real request isn't the one that waits.
    """
    key = f"{module}:{attr}"
    if key not in _loaded:
        _loaded[key] = getattr(import_module(module), attr)
    return _loaded[key]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the model now, not on the first request.
    _lazy("app.rag.retriever", "retrieve")
    yield


app = FastAPI(title="Verse Finder API", lifespan=lifespan)

# The app serves its own frontend (see the static mount at the bottom), so the
# browser never makes a cross-origin request and none of this is load-bearing.
# It stays for direct API callers — curl, /docs, a separately-hosted frontend.
#
# `allow_credentials` is off deliberately. Paired with `allow_origins=["*"]` it
# is the one combination that turns a public read-only API into an authenticated
# one that any site can call on a visitor's behalf. There are no cookies here
# today, so it was inert — but this is a public URL now, and the flag would only
# be noticed after whatever made it dangerous had already shipped.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class PromptRequest(BaseModel): # response from frontend
    mainPrompt: str

class Source(BaseModel): # quotes + the recieved cosine similarity score
    text: str
    author: str
    score: float

class PromptResponse(BaseModel): # response (generated reflection AG and R from quotes
    query: str
    reflection: str
    sources: list[Source]

@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "Verse Finder API is running"}

@app.post("/api/verses/search", response_model=PromptResponse)
def search_verses(request: PromptRequest):
    # RAG PIPELINE FOUND HERE
    # 1. Retrieve: find the quotes most similar to what the user wrote. This is
    #    local and in-process — if it raises, that is our bug, and the 500 that
    #    FastAPI produces is the honest answer. Left unwrapped on purpose.
    sources = _lazy("app.rag.retriever", "retrieve")(request.mainPrompt, k=3)

    # 2. Generate: hand those quotes to Claude to write a grounded reflection.
    #    This one leaves the process, so its failures are not our bug: a missing
    #    ANTHROPIC_API_KEY, an exhausted credit balance, an upstream outage. The
    #    agent route already answers those with a 502 and a reason; without the
    #    same treatment here, a deployment missing its key looked like a crash.
    try:
        reflection = _lazy("app.rag.generator", "generate_reflection")(
            request.mainPrompt, sources
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"reflection failed: {type(e).__name__}: {e}"
        )

    return PromptResponse(
        query=request.mainPrompt,
        reflection=reflection,
        sources=sources,
    )


# --------------------------------------------------------------------------
# the agent
# --------------------------------------------------------------------------

class Implementation(str, Enum):
    """Which agent loop to run.

    Both expose the same `reflect()` and produce the same result shape — that
    is the point of having built the loop twice. Exposing the choice here means
    you can compare them from the browser, not just in the eval harness.
    """

    handrolled = "handrolled"  # app/rag/agent.py — raw Anthropic SDK
    langgraph = "langgraph"    # app/rag/agent_lc.py — StateGraph


AGENT_MODULES = {
    Implementation.handrolled: "app.rag.agent",
    Implementation.langgraph: "app.rag.agent_lc",
}


class TraceStep(BaseModel):
    """One search the agent decided to run."""

    step: int
    tool: str
    query: str | None = None
    returned: int
    top_score: float | None = None
    error: str | None = None  # the tool failed; the model saw this text and could retry


class AgenticResponse(PromptResponse):
    """The baseline shape plus the agent's account of how it got there."""

    trace: list[TraceStep]
    implementation: Implementation
    # True when the loop used up its iteration budget still searching and the
    # reflection came from the salvage call. The quotes are real either way,
    # but the run was cut short and the panel says so.
    stopped_early: bool


@app.post("/api/verses/search/agentic", response_model=AgenticResponse)
def search_verses_agentic(
    request: PromptRequest,
    implementation: Implementation = Query(
        Implementation.handrolled,
        description="Which agent loop to run. Both return the same shape.",
    ),
):
    """Search as many times as it takes, then reflect — and show the searches."""
    reflect = _lazy(AGENT_MODULES[implementation], "reflect")

    try:
        result = reflect(request.mainPrompt)
    except ValueError as e:
        # Blank prompt. The caller's mistake, not ours.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # A missing API key or an upstream failure. Returning a 502 with the
        # reason beats a bare traceback, since the browser is the caller.
        raise HTTPException(
            status_code=502, detail=f"agent run failed: {type(e).__name__}: {e}"
        )

    return AgenticResponse(
        query=request.mainPrompt,
        reflection=result.reflection,
        sources=result.quotes,
        trace=result.trace,
        implementation=implementation,
        stopped_early=result.stopped_early,
    )


# --------------------------------------------------------------------------
# the explainer — optional
# --------------------------------------------------------------------------
# lime pulls scikit-image, matplotlib and scipy behind it, roughly 150 MB, for
# an endpoint the frontend never calls. It lives in requirements-dev.txt, so a
# production image built from requirements.txt does not have it.
#
# Detected rather than configured. A flag would be a second thing to keep in
# sync with the actual install, and it would let you switch on a route whose
# import cannot succeed. `find_spec` asks the only question that matters — is
# the package importable — without paying the import cost here; `_lazy` still
# defers that to the first request.
#
# When it is absent the route is not registered at all, so it 404s and /docs
# stops advertising it. The alternative — always register, fail at request time
# with an explanation — documents itself better but publishes an endpoint that
# cannot work, which is the worse lie.

EXPLAIN_AVAILABLE = importlib.util.find_spec("lime") is not None


class WordImportance(BaseModel):
    """One query word and how much it pulled toward the matched quote."""
    word: str
    weight: float

class ExplainResponse(BaseModel):
    """LIME's view of why the top quote was retrieved for this query."""
    query: str
    matched_quote: str
    matched_author: str
    score: float
    word_importances: list[WordImportance]


if EXPLAIN_AVAILABLE:
    @app.post("/api/verses/explain", response_model=ExplainResponse)
    def explain_verses(request: PromptRequest):
        """Explain the retrieval: which query words drove the top match (LIME).

        Development-only: served when lime is installed (requirements-dev.txt).
        """
        return _lazy("app.rag.explain", "explain_retrieval")(request.mainPrompt)


# --------------------------------------------------------------------------
# the frontend
# --------------------------------------------------------------------------
# Mounted last and at "/" so the API routes above (all exact paths) still win;
# only requests that don't match one of them fall through to static files.
# This makes the API and the UI one deployable unit — no separate frontend
# host, no CORS story, no hardcoded API base URL in app.js.

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
