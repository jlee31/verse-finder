"""Tests for the HTTP surface.

These run without the network and without loading the mpnet model — which is
only possible because `main._lazy` defers the heavy imports. Faking that one
function replaces retrieval, generation, and the agent in a single place.

    pytest -q                  # these run by default
    pytest -q -m live          # the real end-to-end call (costs money)
"""
import importlib.util

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import AGENT_MODULES, Implementation, app
from app.rag.agent import AgentResult

client = TestClient(app)


QUOTES = [
    {"text": "Holding on to anger is like grasping a hot coal.", "author": "Buddha", "score": 0.49},
    {"text": "The wound is the place where the Light enters you.", "author": "Rumi", "score": 0.44},
]

TRACE = [
    {"step": 1, "tool": "search_quotes", "query": "grief over losing a parent",
     "returned": 3, "top_score": 0.469},
    {"step": 2, "tool": "search_quotes", "query": "anger toward family",
     "returned": 3, "top_score": 0.491},
]


@pytest.fixture
def fake_backends(monkeypatch):
    """Swap out everything `_lazy` would import. Returns the call log.

    The default agent result is a two-search run, i.e. the behaviour the whole
    plan exists to produce.
    """
    calls = []
    result = AgentResult(reflection="a reflection", quotes=list(QUOTES),
                         trace=list(TRACE), api_calls=3, stopped_early=False)
    state = {"result": result, "raises": None, "generate_raises": None}

    def reflect(text, **kwargs):
        calls.append(("reflect", text))
        if state["raises"] is not None:
            raise state["raises"]
        return state["result"]

    def generate_reflection(text, sources):
        if state["generate_raises"] is not None:
            raise state["generate_raises"]
        return "a one-shot reflection"

    def fake_lazy(module, attr):
        calls.append((module, attr))
        if attr == "reflect":
            return reflect
        if attr == "retrieve":
            return lambda text, k=3: list(QUOTES)[:k]
        if attr == "generate_reflection":
            return generate_reflection
        raise AssertionError(f"unexpected lazy import {module}.{attr}")

    monkeypatch.setattr(main, "_lazy", fake_lazy)
    return calls, state


def _post(path, prompt="i'm grieving my dad and angry at my family", **params):
    return client.post(path, json={"mainPrompt": prompt}, params=params)


# --------------------------------------------------------------------------
# health + baseline
# --------------------------------------------------------------------------

def test_root_reports_ok():
    assert client.get("/api/health").json()["status"] == "ok"


def test_baseline_search_still_returns_the_original_shape(fake_backends):
    body = _post("/api/verses/search").json()

    assert set(body) == {"query", "reflection", "sources"}
    assert body["reflection"] == "a one-shot reflection"
    assert len(body["sources"]) == 2


def test_baseline_search_has_no_trace(fake_backends):
    # The one-shot pipeline made no decisions, so it has nothing to show. If a
    # trace ever appears here, the two endpoints have been conflated.
    assert "trace" not in _post("/api/verses/search").json()


def test_a_failed_reflection_is_a_502_with_the_reason(fake_backends):
    # Deploying without ANTHROPIC_API_KEY used to surface here as a bare 500
    # with no body, which reads as "the server is broken" — so the first place
    # you look is the server, not the missing variable. The agent route already
    # answered this case properly; this one didn't.
    _, state = fake_backends
    state["generate_raises"] = RuntimeError("The api_key client option must be set")

    res = _post("/api/verses/search")
    assert res.status_code == 502
    assert "api_key" in res.json()["detail"]
    assert "RuntimeError" in res.json()["detail"]


def test_retrieval_failures_are_not_disguised_as_upstream_ones(monkeypatch):
    # Retrieval is local, so a failure there is our bug and must not be laundered
    # into a 502. Only the call that leaves the process gets that treatment.
    def broken_lazy(module, attr):
        if attr == "retrieve":
            raise RuntimeError("embedding matrix is missing")
        raise AssertionError("generation should never be reached")

    monkeypatch.setattr(main, "_lazy", broken_lazy)

    with pytest.raises(RuntimeError, match="embedding matrix"):
        _post("/api/verses/search")


def test_cors_never_pairs_a_wildcard_origin_with_credentials(fake_backends):
    # The combination that makes a public API callable by any site on a logged-in
    # visitor's behalf. There are no cookies here yet, which is exactly why this
    # needs a test: the flag would otherwise be noticed only after auth shipped.
    res = client.post(
        "/api/verses/search",
        json={"mainPrompt": "hello"},
        headers={"Origin": "https://evil.example"},
    )
    assert res.headers.get("access-control-allow-credentials") is None
    assert res.headers["access-control-allow-origin"] == "*"


# --------------------------------------------------------------------------
# the agentic endpoint
# --------------------------------------------------------------------------

def test_agentic_returns_the_baseline_fields_plus_the_trace(fake_backends):
    body = _post("/api/verses/search/agentic").json()

    # A superset of the baseline shape: the frontend renders both with one
    # code path and only adds the panel when a trace is present.
    assert {"query", "reflection", "sources"} <= set(body)
    assert body["reflection"] == "a reflection"
    assert [s["author"] for s in body["sources"]] == ["Buddha", "Rumi"]
    assert body["stopped_early"] is False


def test_the_trace_shows_every_search_in_order(fake_backends):
    trace = _post("/api/verses/search/agentic").json()["trace"]

    assert [t["step"] for t in trace] == [1, 2]
    assert [t["query"] for t in trace] == ["grief over losing a parent", "anger toward family"]
    assert trace[0]["top_score"] == 0.469


def test_defaults_to_the_handrolled_loop(fake_backends):
    calls, _ = fake_backends
    body = _post("/api/verses/search/agentic").json()

    assert body["implementation"] == "handrolled"
    assert ("app.rag.agent", "reflect") in calls


def test_the_query_param_picks_the_langgraph_loop(fake_backends):
    calls, _ = fake_backends
    body = _post("/api/verses/search/agentic", implementation="langgraph").json()

    assert body["implementation"] == "langgraph"
    assert ("app.rag.agent_lc", "reflect") in calls


def test_an_unknown_implementation_is_rejected(fake_backends):
    res = _post("/api/verses/search/agentic", implementation="pipeline")
    assert res.status_code == 422


def test_both_implementations_name_a_module_that_exists():
    """A typo in AGENT_MODULES would only surface as a 502 at request time.

    find_spec resolves the path without importing, so this stays fast and
    doesn't drag LangChain into the offline suite.
    """
    for implementation, module in AGENT_MODULES.items():
        assert importlib.util.find_spec(module) is not None, implementation
    assert set(AGENT_MODULES) == set(Implementation)


def test_a_stopped_early_run_says_so(fake_backends):
    _, state = fake_backends
    state["result"] = AgentResult(reflection="salvaged", quotes=list(QUOTES),
                                  trace=list(TRACE), api_calls=7, stopped_early=True)

    body = _post("/api/verses/search/agentic").json()
    # The quotes are real either way — the run was just cut short. Silently
    # returning them as a complete answer would overstate what happened.
    assert body["stopped_early"] is True
    assert body["reflection"] == "salvaged"


def test_a_failed_search_survives_into_the_trace(fake_backends):
    _, state = fake_backends
    state["result"] = AgentResult(
        reflection="r", quotes=[],
        trace=[{"step": 1, "tool": "search_quotes", "query": None, "returned": 0,
                "top_score": None, "error": "Invalid arguments: query must be a non-empty string"}],
    )

    step = _post("/api/verses/search/agentic").json()["trace"][0]
    # top_score and query are legitimately null on a failed call; a stricter
    # model here would 500 on the one response worth seeing.
    assert step["error"].startswith("Invalid arguments")
    assert step["top_score"] is None
    assert step["query"] is None


def test_a_blank_prompt_is_the_callers_mistake(fake_backends):
    _, state = fake_backends
    state["raises"] = ValueError("text must be a non-empty string")

    res = _post("/api/verses/search/agentic", prompt="   ")
    assert res.status_code == 422
    assert "non-empty" in res.json()["detail"]


def test_an_upstream_failure_is_a_502_not_a_traceback(fake_backends):
    _, state = fake_backends
    state["raises"] = RuntimeError("connection reset")

    res = _post("/api/verses/search/agentic")
    assert res.status_code == 502
    assert "connection reset" in res.json()["detail"]
    assert "RuntimeError" in res.json()["detail"]


def test_a_missing_prompt_field_is_rejected(fake_backends):
    assert client.post("/api/verses/search/agentic", json={}).status_code == 422


# --------------------------------------------------------------------------
# lazy loading
# --------------------------------------------------------------------------

def test_lazy_imports_once_and_caches(monkeypatch):
    """The agent modules must not be re-imported per request.

    `app.rag.agent_lc` pulls in all of LangChain; doing that on every call
    would add seconds to a request that is already slow.
    """
    imports = []
    real = main.import_module

    def counting_import(name):
        imports.append(name)
        return real(name)

    monkeypatch.setattr(main, "import_module", counting_import)
    monkeypatch.setattr(main, "_loaded", {})

    main._lazy("app.rag.tools", "search_quotes")
    main._lazy("app.rag.tools", "search_quotes")
    assert imports == ["app.rag.tools"]


def test_the_openapi_schema_still_generates():
    # pydantic was raised to 2.13.4 for LangChain while FastAPI stayed at
    # 0.104.1. /docs breaking is the way that mismatch would show up.
    schema = app.openapi()
    assert "/api/verses/search/agentic" in schema["paths"]
    assert "/api/verses/search" in schema["paths"]


# --------------------------------------------------------------------------
# end to end (real API calls)
# --------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.slow
def test_the_agent_is_reachable_over_http():
    """Stage 4's accept criterion, minus the browser."""
    res = _post("/api/verses/search/agentic")
    assert res.status_code == 200

    body = res.json()
    assert body["reflection"].strip()
    assert len(body["trace"]) >= 2  # it split the compound query
    assert body["sources"]
