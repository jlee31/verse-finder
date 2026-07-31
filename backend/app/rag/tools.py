"""Tools the agent can call.

Stage 1 of the agent plan: one read-only tool wrapping `retrieve()` untouched.

Three things live here, and the split matters for the loop in Stage 2:

- `SEARCH_QUOTES_TOOL` — the schema sent to the API in `tools=[...]`
- `search_quotes()`    — the Python function, usable and testable on its own
- `dispatch()`         — execution that **never raises**, returning everything a
  `tool_result` block needs

That last one is the point. A tool that throws inside the agent loop kills the
whole request; the recoverable behaviour is to hand the model an error it can
read and retry differently.
"""
from dataclasses import dataclass, field

DEFAULT_K = 3
MAX_K = 10

# Below this, cosine similarity means "nothing in the corpus is really about
# this" rather than "here is a weak match". Measured: the compound queries in
# the plan all top out around 0.40-0.52, and genuine matches sit above that.
MIN_USEFUL_SCORE = 0.35

SEARCH_QUOTES_TOOL = {
    "name": "search_quotes",
    "description": (
        "Search the quote corpus for a single emotional theme. Call once per "
        "distinct feeling in the person's message — a query naming two feelings "
        "matches neither well. Returns quotes with cosine similarity in [0,1]; "
        "below ~0.35 means nothing in the corpus really fits, so try rephrasing "
        "the theme rather than accepting a weak match."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "One emotional theme, e.g. 'grief over losing a parent'",
            },
            "k": {
                "type": "integer",
                "description": f"How many quotes to return (default {DEFAULT_K}, max {MAX_K})",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    # Verified against the API: strict accepts an optional property, and the
    # model omits `k` when it has no reason to set it.
    "strict": True,
}

TOOLS = [SEARCH_QUOTES_TOOL]

_retrieve = None


def _retrieve_lazy():
    """Import `retrieve` on first use.

    `app.rag.retriever` loads the mpnet model and the embedding matrix at import
    time (~20s). Schema and validation tests must not pay that cost.
    """
    global _retrieve
    if _retrieve is None:
        from app.rag.retriever import retrieve

        _retrieve = retrieve
    return _retrieve


def search_quotes(query: str, k: int = DEFAULT_K) -> list[dict]:
    """Return up to k quotes matching one emotional theme, best first.

    Each result is {"text", "author", "score"}. `k` is clamped to [1, MAX_K] —
    it is a resource bound, not a semantic input, so an over-eager value is
    capped rather than failed.

    Raises ValueError on a missing or blank query.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")

    if k is None:
        k = DEFAULT_K
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError(f"k must be an integer, got {type(k).__name__}")
    k = max(1, min(k, MAX_K))

    return _retrieve_lazy()(query.strip(), k=k)


def format_results(quotes: list[dict]) -> str:
    """Render quotes as the text body of a `tool_result` block.

    Scores are included deliberately: the model needs them to judge whether a
    facet was actually covered or whether it should search again.
    """
    if not quotes:
        return "No quotes found."

    lines = [
        f"{i}. [{q['score']:.2f}] \"{q['text']}\" — {q['author']}"
        for i, q in enumerate(quotes, 1)
    ]
    if quotes[0]["score"] < MIN_USEFUL_SCORE:
        lines.append(
            f"\nNothing scored above {MIN_USEFUL_SCORE:.2f}. The corpus probably "
            "doesn't cover this theme — try naming the feeling differently."
        )
    return "\n".join(lines)


@dataclass
class ToolOutcome:
    """One executed tool call.

    `content` and `is_error` are what the API needs in a `tool_result` block.
    `quotes` is for the harness: the agent builds its source list from the
    structured results, which the rendered text has already flattened away.
    """

    content: str
    is_error: bool = False
    quotes: list[dict] = field(default_factory=list)


def dispatch(name: str, tool_input: dict) -> ToolOutcome:
    """Execute a tool call from the model. Never raises.

    Everything the model got wrong comes back as text it can act on, because a
    raised exception here would end the agent run instead of giving it a chance
    to correct the call.
    """
    if name != SEARCH_QUOTES_TOOL["name"]:
        return ToolOutcome(
            f"Unknown tool {name!r}. Available: {SEARCH_QUOTES_TOOL['name']}.",
            is_error=True,
        )

    if not isinstance(tool_input, dict):
        return ToolOutcome("Tool input must be an object.", is_error=True)

    try:
        quotes = search_quotes(tool_input.get("query"), tool_input.get("k", DEFAULT_K))
    except ValueError as e:
        return ToolOutcome(f"Invalid arguments: {e}", is_error=True)
    except Exception as e:  # retrieval itself failed — model can't fix it, but shouldn't crash
        return ToolOutcome(f"Search failed: {type(e).__name__}: {e}", is_error=True)

    return ToolOutcome(format_results(quotes), is_error=False, quotes=quotes)


def run_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """`dispatch()` as the (content, is_error) pair, for callers that only
    need what goes on the wire."""
    outcome = dispatch(name, tool_input)
    return outcome.content, outcome.is_error
