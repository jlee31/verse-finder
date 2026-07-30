"""Tests for the agent's tools.

Everything here runs without the network. The tests that load the mpnet model
are marked `slow`:

    pytest -q                  # fast only (deselect slow)
    pytest -q -m slow          # the retrieval integration tests
"""
import pytest

from app.rag import tools
from app.rag.tools import (
    DEFAULT_K,
    MAX_K,
    MIN_USEFUL_SCORE,
    SEARCH_QUOTES_TOOL,
    format_results,
    run_tool,
    search_quotes,
)


def _quote(text, score, author="A"):
    return {"text": text, "author": author, "score": score}


@pytest.fixture
def fake_retrieve(monkeypatch):
    """Replace retrieval with a recorder, so the model never loads.

    Returns the call log: [(query, k), ...].
    """
    calls = []

    def fake(query, k=DEFAULT_K):
        calls.append((query, k))
        return [_quote(f"quote {i}", 0.5 - i * 0.01) for i in range(k)]

    monkeypatch.setattr(tools, "_retrieve", fake)
    return calls


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

def test_schema_shape_matches_what_the_api_accepts():
    schema = SEARCH_QUOTES_TOOL["input_schema"]
    assert SEARCH_QUOTES_TOOL["name"] == "search_quotes"
    assert SEARCH_QUOTES_TOOL["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"query", "k"}


def test_only_query_is_required():
    # Verified live: strict:True accepts an optional property, and the model
    # omits `k` when it has no reason to set one. If `k` ever becomes required
    # the model has to invent a number on every call.
    assert SEARCH_QUOTES_TOOL["input_schema"]["required"] == ["query"]


def test_description_tells_the_model_when_to_call_not_just_what_it_does():
    """The decomposition behaviour is driven entirely by this sentence.

    If it gets edited down to "searches for quotes", the agent stops splitting
    compound queries and Stage 2 quietly regresses to the baseline.
    """
    description = SEARCH_QUOTES_TOOL["description"].lower()
    assert "once per" in description
    assert "two feelings" in description
    assert "0.35" in description


# --------------------------------------------------------------------------
# search_quotes
# --------------------------------------------------------------------------

def test_search_passes_query_and_k_through(fake_retrieve):
    search_quotes("anger toward family", k=2)
    assert fake_retrieve == [("anger toward family", 2)]


def test_search_defaults_k(fake_retrieve):
    search_quotes("grief")
    assert fake_retrieve[0][1] == DEFAULT_K


def test_search_strips_whitespace(fake_retrieve):
    search_quotes("  grief  ")
    assert fake_retrieve[0][0] == "grief"


@pytest.mark.parametrize("asked, expected", [(0, 1), (-5, 1), (MAX_K + 50, MAX_K)])
def test_k_is_clamped_not_rejected(fake_retrieve, asked, expected):
    # k bounds a resource, not a meaning — an over-eager value gets capped so
    # the agent doesn't burn a turn recovering from a trivial mistake.
    search_quotes("grief", k=asked)
    assert fake_retrieve[0][1] == expected


def test_none_k_falls_back_to_the_default(fake_retrieve):
    # The model can emit an explicit null for an optional property.
    search_quotes("grief", k=None)
    assert fake_retrieve[0][1] == DEFAULT_K


@pytest.mark.parametrize("bad", ["", "   ", None, 42])
def test_blank_or_non_string_query_is_rejected(fake_retrieve, bad):
    with pytest.raises(ValueError, match="non-empty string"):
        search_quotes(bad)
    assert fake_retrieve == []


@pytest.mark.parametrize("bad", ["3", 2.5, True])
def test_non_integer_k_is_rejected(fake_retrieve, bad):
    # True is an int in Python; letting it through would silently mean k=1.
    with pytest.raises(ValueError, match="must be an integer"):
        search_quotes("grief", k=bad)


# --------------------------------------------------------------------------
# format_results
# --------------------------------------------------------------------------

def test_format_includes_score_text_and_author():
    out = format_results([_quote("Hold on.", 0.47, author="Rilke")])
    assert "[0.47]" in out
    assert "Hold on." in out
    assert "Rilke" in out


def test_format_numbers_results_in_order():
    out = format_results([_quote("a", 0.6), _quote("b", 0.5)])
    assert out.index("1.") < out.index("2.")


def test_format_warns_when_nothing_scored_well():
    # This hint is what pushes the agent to rephrase instead of accepting
    # filler — the exact failure the baseline exhibits.
    out = format_results([_quote("filler", MIN_USEFUL_SCORE - 0.01)])
    assert "doesn't cover this theme" in out


def test_format_stays_quiet_on_a_good_match():
    out = format_results([_quote("on point", MIN_USEFUL_SCORE + 0.2)])
    assert "doesn't cover this theme" not in out


def test_format_handles_no_results():
    assert format_results([]) == "No quotes found."


# --------------------------------------------------------------------------
# run_tool — the dispatch the agent loop calls
# --------------------------------------------------------------------------

def test_run_tool_returns_content_and_no_error_on_success(fake_retrieve):
    content, is_error = run_tool("search_quotes", {"query": "grief"})
    assert is_error is False
    assert "quote 0" in content


def test_run_tool_honours_k(fake_retrieve):
    run_tool("search_quotes", {"query": "grief", "k": 5})
    assert fake_retrieve[0][1] == 5


def test_unknown_tool_is_an_error_not_an_exception(fake_retrieve):
    content, is_error = run_tool("delete_everything", {"query": "x"})
    assert is_error is True
    assert "search_quotes" in content  # tell the model what it can call


def test_bad_arguments_come_back_as_an_error_the_model_can_read(fake_retrieve):
    content, is_error = run_tool("search_quotes", {"query": ""})
    assert is_error is True
    assert "Invalid arguments" in content


def test_missing_query_is_an_error(fake_retrieve):
    content, is_error = run_tool("search_quotes", {})
    assert is_error is True


def test_non_dict_input_is_an_error(fake_retrieve):
    content, is_error = run_tool("search_quotes", "grief")
    assert is_error is True


def test_retrieval_blowing_up_does_not_escape(monkeypatch):
    """A raised exception here would end the agent run mid-loop.

    The model can't fix a broken index, but the harness must still return a
    tool_result so the conversation can close cleanly.
    """
    def boom(query, k=DEFAULT_K):
        raise RuntimeError("index unreadable")

    monkeypatch.setattr(tools, "_retrieve", boom)
    content, is_error = run_tool("search_quotes", {"query": "grief"})
    assert is_error is True
    assert "index unreadable" in content


# --------------------------------------------------------------------------
# retrieval integration (loads the model)
# --------------------------------------------------------------------------

@pytest.mark.slow
def test_search_returns_scored_quotes_best_first():
    quotes = search_quotes("i feel lonely", k=3)

    assert len(quotes) == 3
    for q in quotes:
        assert {"text", "author", "score"} <= set(q)
        assert 0.0 <= q["score"] <= 1.0
    scores = [q["score"] for q in quotes]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.slow
def test_the_tool_finds_the_anger_quotes_the_compound_query_missed():
    """Stage 1's accept criterion.

    The baseline returns zero anger quotes for "grieving my dad and angry at my
    family". Searching that one facet on its own finds them — which is why
    giving the model a tool it can call more than once is the fix.
    """
    from app.rag.retriever import retrieve

    compound = {q["text"] for q in retrieve("i'm grieving my dad and angry at my family", k=3)}
    anger = search_quotes("anger toward family", k=3)

    assert "anger" in " ".join(q["text"] for q in anger).lower()
    assert not ({q["text"] for q in anger} & compound), (
        "the compound query now returns these anger quotes — the defect the "
        "agent work exists to fix may be gone"
    )


@pytest.mark.slow
def test_run_tool_end_to_end_on_the_real_corpus():
    content, is_error = run_tool("search_quotes", {"query": "grief over losing a parent"})
    assert is_error is False
    assert content.count("\n") >= 2  # three numbered quotes
    assert "[0." in content
