"""Tests for the eval harness.

Everything here runs without the network. The one test that loads the mpnet
model is marked `slow`:

    pytest evals -q                  # fast only (deselect slow)
    pytest evals -q -m slow          # the retriever integration test
"""
import json
from pathlib import Path

import pytest

from evals import metrics
from evals.judge import Judge, _align, _cache_key
from evals.run import BACKEND_DIR, EVALS_DIR, display_path, load_queries, validate_queries


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def test_facet_coverage_all_covered():
    assert metrics.facet_coverage([True, True]) == 1.0


def test_facet_coverage_half():
    # The defect this whole plan exists for: one of two facets answered.
    assert metrics.facet_coverage([True, False]) == 0.5


def test_facet_coverage_none():
    assert metrics.facet_coverage([False, False]) == 0.0


def test_facet_coverage_thirds():
    assert metrics.facet_coverage([True, False, False]) == pytest.approx(1 / 3)


def test_facet_coverage_rejects_empty():
    with pytest.raises(ValueError):
        metrics.facet_coverage([])


def _row(coverage, n_facets=2, top_score=0.4, api_calls=0):
    return {"coverage": coverage, "n_facets": n_facets,
            "top_score": top_score, "api_calls": api_calls}


def test_summarize_separates_compound_from_single():
    rows = [
        _row(0.5, n_facets=2),   # compound, half covered
        _row(0.5, n_facets=2),   # compound, half covered
        _row(1.0, n_facets=1),   # single facet, covered
    ]
    s = metrics.summarize(rows)

    assert s["n_queries"] == 3
    assert s["n_compound"] == 2
    assert s["facet_coverage"] == pytest.approx(2 / 3)
    # The single-facet win must not inflate the compound number — that split is
    # the whole reason the field exists.
    assert s["facet_coverage_compound_only"] == pytest.approx(0.5)
    assert s["fully_covered_rate"] == pytest.approx(1 / 3)


def test_summarize_handles_no_compound_queries():
    s = metrics.summarize([_row(1.0, n_facets=1)])
    assert s["facet_coverage_compound_only"] is None
    assert s["n_compound"] == 0


def test_summarize_rejects_empty():
    with pytest.raises(ValueError):
        metrics.summarize([])


def test_format_table_renders_none_without_crashing():
    s = metrics.summarize([_row(1.0, n_facets=1)])
    out = metrics.format_table(s, "baseline")
    assert "baseline" in out
    assert "n/a" in out  # the compound-only row


# --------------------------------------------------------------------------
# dataset
# --------------------------------------------------------------------------

def test_shipped_queries_are_valid():
    queries = load_queries(EVALS_DIR / "queries.json")
    assert len(queries) >= 20


def test_shipped_queries_include_compound_and_single():
    queries = load_queries(EVALS_DIR / "queries.json")
    n_compound = sum(1 for q in queries if len(q["facets"]) > 1)
    n_single = sum(1 for q in queries if len(q["facets"]) == 1)
    # Single-facet queries are the control: if the baseline scores badly on
    # those too, the problem isn't compound-query averaging.
    assert n_compound >= 15
    assert n_single >= 3


def test_shipped_queries_cover_the_three_measured_cases():
    ids = {q["id"] for q in load_queries(EVALS_DIR / "queries.json")}
    assert {"grief-anger", "burnout-fear", "lonely-hope"} <= ids


def test_display_path_shortens_paths_under_backend():
    assert display_path(EVALS_DIR / "results" / "baseline.json") == "evals/results/baseline.json"


def test_display_path_handles_paths_outside_backend():
    # `--out /tmp/x.json` used to crash here, after the results file had
    # already been written — a traceback and a nonzero exit on a successful run.
    assert display_path(Path("/tmp/cold.json")) == "/tmp/cold.json"


@pytest.mark.parametrize("bad, msg", [
    ([], "empty"),
    ([{"id": "a", "text": "hi"}], "facets"),
    ([{"id": "a", "text": "hi", "facets": []}], "non-empty"),
    ([{"id": "a", "text": "  ", "facets": ["x"]}], "text is empty"),
    ([{"id": "a", "text": "hi", "facets": ["x", "x"]}], "duplicate facet"),
    ([{"id": "a", "text": "hi", "facets": ["x"]},
      {"id": "a", "text": "yo", "facets": ["y"]}], "duplicate id"),
])
def test_validate_queries_rejects_bad_datasets(bad, msg):
    with pytest.raises(ValueError, match=msg):
        validate_queries(bad)


# --------------------------------------------------------------------------
# judge
# --------------------------------------------------------------------------

QUOTES = [{"text": "Being angry never solves anything.", "author": "A", "score": 0.4}]


def test_cache_key_is_stable_across_calls():
    a = _cache_key("i'm angry", ["anger"], QUOTES)
    b = _cache_key("i'm angry", ["anger"], QUOTES)
    assert a == b


def test_cache_key_changes_with_quotes():
    other = [{"text": "Different quote.", "author": "B", "score": 0.4}]
    assert _cache_key("i'm angry", ["anger"], QUOTES) != _cache_key("i'm angry", ["anger"], other)


def test_cache_key_changes_with_facets():
    assert _cache_key("x", ["anger"], QUOTES) != _cache_key("x", ["grief"], QUOTES)


def test_cache_key_ignores_score_drift():
    # Scores are floats that can wobble; the verdict depends on the quote text,
    # so a re-run must not miss cache over a rounding difference.
    drifted = [{"text": QUOTES[0]["text"], "author": "A", "score": 0.40000001}]
    assert _cache_key("x", ["anger"], QUOTES) == _cache_key("x", ["anger"], drifted)


def test_align_fills_in_a_dropped_facet():
    verdicts = [{"facet": "anger", "covered": True, "quote": "q", "reason": "r"}]
    out = _align(verdicts, ["anger", "grief"])
    assert [v["facet"] for v in out] == ["anger", "grief"]
    # A facet the judge silently skipped must score as uncovered, not vanish.
    assert out[1]["covered"] is False


def test_align_restores_requested_order():
    verdicts = [
        {"facet": "grief", "covered": True, "quote": "q", "reason": "r"},
        {"facet": "anger", "covered": False, "quote": "", "reason": "r"},
    ]
    out = _align(verdicts, ["anger", "grief"])
    assert [v["facet"] for v in out] == ["anger", "grief"]
    assert out[0]["covered"] is False
    assert out[1]["covered"] is True


def test_offline_judge_raises_instead_of_calling_api(tmp_path):
    judge = Judge(offline=True, cache_dir=tmp_path)
    with pytest.raises(RuntimeError, match="offline"):
        judge.judge("i'm angry", ["anger"], QUOTES)


def test_judge_reads_a_cached_verdict_without_the_api(tmp_path):
    judge = Judge(offline=True, cache_dir=tmp_path)
    key = _cache_key("i'm angry", ["anger"], QUOTES)
    payload = {"facets": [{"facet": "anger", "covered": True,
                           "quote": QUOTES[0]["text"], "reason": "on point"}]}
    (tmp_path / f"{key}.json").write_text(json.dumps(payload))

    out = judge.judge("i'm angry", ["anger"], QUOTES)
    assert out[0]["covered"] is True
    assert judge.hits == 1
    assert judge.misses == 0


# --------------------------------------------------------------------------
# retriever integration (loads the model)
# --------------------------------------------------------------------------

@pytest.mark.slow
def test_baseline_retriever_returns_scored_quotes():
    from evals.retrievers import BaselineRetriever

    r = BaselineRetriever(k=3)
    result = r.search("i feel lonely")

    assert len(result.quotes) == 3
    assert result.api_calls == 0
    for q in result.quotes:
        assert {"text", "author", "score"} <= set(q)
        assert 0.0 <= q["score"] <= 1.0
    # Best-first ordering is what top_score assumes.
    scores = [q["score"] for q in result.quotes]
    assert scores == sorted(scores, reverse=True)
    assert result.top_score == scores[0]


@pytest.mark.slow
def test_baseline_drops_a_facet_on_a_compound_query():
    """The defect, pinned as a test.

    Searching for anger alone finds anger quotes; asking for grief AND anger
    together does not. If this ever fails, the premise of the agent work has
    changed and the plan needs revisiting.
    """
    from evals.retrievers import BaselineRetriever

    r = BaselineRetriever(k=3)
    anger_alone = r.search("i'm angry at my family")
    compound = r.search("i'm grieving my dad and angry at my family")

    anger_texts = {q["text"] for q in anger_alone.quotes}
    compound_texts = {q["text"] for q in compound.quotes}

    assert "angry" in " ".join(anger_texts).lower()
    assert not (anger_texts & compound_texts), (
        "compound query now returns anger quotes — the motivating defect may be gone"
    )
