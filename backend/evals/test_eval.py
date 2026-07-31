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
from evals.judge import Judge, _align, _cache_key, _vote
from evals.run import (
    BACKEND_DIR,
    EVALS_DIR,
    default_out_path,
    display_path,
    load_queries,
    rejudge,
    validate_queries,
)


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


def test_judge_stability_finds_the_requested_query(tmp_path):
    from evals.judge_stability import load_row

    results = tmp_path / "r.json"
    results.write_text(json.dumps({"rows": [{"id": "a"}, {"id": "b"}]}))
    assert load_row(results, "b") == {"id": "b"}


def test_judge_stability_lists_the_ids_it_does_have(tmp_path):
    # A typo'd --query should say what's available, not just fail.
    from evals.judge_stability import load_row

    results = tmp_path / "r.json"
    results.write_text(json.dumps({"rows": [{"id": "grief-anger"}]}))
    with pytest.raises(SystemExit, match="grief-anger"):
        load_row(results, "typo")


def test_every_registered_retriever_reports_its_registry_name():
    """`name` picks the results filename.

    A variant that inherited `name = "baseline"` would quietly overwrite the
    reference numbers the moment it was scored.
    """
    from evals import retrievers

    for key in retrievers.REGISTRY:
        assert retrievers.build(key).name == key


def test_a_smoke_run_cannot_clobber_the_reference_baseline():
    # `--no-judge` produces summary: null. Landing that on baseline.json wipes
    # the numbers every later stage is measured against — which is exactly what
    # happened once.
    judged = default_out_path("baseline", judged=True)
    smoke = default_out_path("baseline", judged=False)
    assert judged.name == "baseline.json"
    assert judged != smoke


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


def test_cache_key_differs_per_round():
    # Rounds sharing a key would read back round 0's verdict and make every
    # vote unanimous by construction — the noise would vanish from the numbers
    # without ever leaving the judge.
    assert _cache_key("x", ["anger"], QUOTES, 0) != _cache_key("x", ["anger"], QUOTES, 1)


def test_offline_judge_raises_instead_of_calling_api(tmp_path):
    judge = Judge(offline=True, cache_dir=tmp_path)
    with pytest.raises(RuntimeError, match="offline"):
        judge.judge("i'm angry", ["anger"], QUOTES)


def _cache_round(tmp_path, round_, covered, text="i'm angry", facets=("anger",)):
    key = _cache_key(text, list(facets), QUOTES, round_)
    payload = {"facets": [{"facet": f, "covered": c, "quote": "", "reason": "r"}
                          for f, c in zip(facets, covered)]}
    (tmp_path / f"{key}.json").write_text(json.dumps(payload))


def test_judge_reads_cached_verdicts_without_the_api(tmp_path):
    judge = Judge(offline=True, cache_dir=tmp_path, rounds=3)
    for r in range(3):
        _cache_round(tmp_path, r, [True])

    out = judge.judge("i'm angry", ["anger"], QUOTES)
    assert out[0]["covered"] is True
    assert judge.hits == 3
    assert judge.misses == 0


def test_a_majority_carries_a_split_facet(tmp_path):
    # Two rounds say covered, one says not. The whole point of voting: the
    # verdict is the majority, and `votes` records that it was not unanimous.
    judge = Judge(offline=True, cache_dir=tmp_path, rounds=3)
    for r, covered in enumerate([True, False, True]):
        _cache_round(tmp_path, r, [covered])

    out = judge.judge("i'm angry", ["anger"], QUOTES)
    assert out[0]["covered"] is True
    assert (out[0]["votes"], out[0]["rounds"]) == (2, 3)
    assert judge.split == 1


def test_a_minority_does_not_carry(tmp_path):
    judge = Judge(offline=True, cache_dir=tmp_path, rounds=3)
    for r, covered in enumerate([True, False, False]):
        _cache_round(tmp_path, r, [covered])

    out = judge.judge("i'm angry", ["anger"], QUOTES)
    assert out[0]["covered"] is False
    assert out[0]["votes"] == 1


def test_a_unanimous_verdict_is_not_counted_as_split(tmp_path):
    judge = Judge(offline=True, cache_dir=tmp_path, rounds=3)
    for r in range(3):
        _cache_round(tmp_path, r, [False])

    judge.judge("i'm angry", ["anger"], QUOTES)
    assert judge.split == 0


def test_an_even_round_count_is_rejected(tmp_path):
    # Two rounds have no majority to take.
    with pytest.raises(ValueError, match="odd"):
        Judge(offline=True, cache_dir=tmp_path, rounds=2)


def _verdict(facet, covered, votes=3, rounds=3):
    return {"facet": facet, "covered": covered, "quote": "",
            "reason": f"{facet} reason", "votes": votes, "rounds": rounds}


def test_vote_takes_the_reason_from_the_winning_side():
    # A 2-1 verdict quoting the dissent's reason would read as a contradiction
    # of the verdict recorded next to it.
    rounds = [
        [{"facet": "anger", "covered": True, "quote": "q", "reason": "yes it does"}],
        [{"facet": "anger", "covered": False, "quote": "", "reason": "no it doesn't"}],
        [{"facet": "anger", "covered": True, "quote": "q", "reason": "clearly anger"}],
    ]
    out = _vote(rounds, ["anger"])
    assert out[0]["covered"] is True
    assert out[0]["reason"] == "yes it does"


def test_vote_scores_each_facet_independently():
    rounds = [
        [{"facet": "grief", "covered": True, "quote": "", "reason": "r"},
         {"facet": "anger", "covered": False, "quote": "", "reason": "r"}],
        [{"facet": "grief", "covered": True, "quote": "", "reason": "r"},
         {"facet": "anger", "covered": True, "quote": "", "reason": "r"}],
        [{"facet": "grief", "covered": True, "quote": "", "reason": "r"},
         {"facet": "anger", "covered": False, "quote": "", "reason": "r"}],
    ]
    out = _vote(rounds, ["grief", "anger"])
    assert [v["covered"] for v in out] == [True, False]
    assert [v["votes"] for v in out] == [3, 1]


def test_split_verdict_rate_counts_only_disagreements():
    verdicts = [_verdict("a", True, votes=3), _verdict("b", True, votes=2),
                _verdict("c", False, votes=0), _verdict("d", False, votes=1)]
    assert metrics.split_verdict_rate(verdicts) == pytest.approx(0.5)


def test_split_verdict_rate_is_none_for_single_round_verdicts():
    # Results files written before voting existed carry no vote counts. They
    # must report "unknown", not a confident zero.
    assert metrics.split_verdict_rate([{"facet": "a", "covered": True}]) is None


# --------------------------------------------------------------------------
# rejudge
# --------------------------------------------------------------------------

def _report(coverage=0.5, covered=(True, False)):
    return {
        "retriever": "agentic",
        "judged": True,
        "judge_prompt_version": 1,
        "total_seconds": 400.0,
        "summary": {"facet_coverage": coverage},
        "rows": [{
            "id": "grief-anger",
            "text": "grieving my dad and angry at my family",
            "n_facets": 2,
            "coverage": coverage,
            "top_score": 0.63,
            "api_calls": 3,
            "seconds": 16.0,
            "quotes": list(QUOTES),
            "trace": [{"step": 1}],
            "verdicts": [_verdict("grief", covered[0]), _verdict("anger", covered[1])],
        }],
    }


QUERY_SET = [{"id": "grief-anger",
              "text": "grieving my dad and angry at my family",
              "facets": ["grief", "anger toward family"]}]


class _FixedJudge:
    """Returns a set verdict without touching the network."""

    def __init__(self, covered):
        self.covered = covered
        self.hits = self.misses = self.split = 0

    def judge(self, text, facets, quotes):
        return [_verdict(f, c) for f, c in zip(facets, self.covered)]


def test_rejudge_recomputes_coverage_from_the_new_verdicts():
    out = rejudge(_report(coverage=0.5), QUERY_SET, _FixedJudge([True, True]))
    assert out["rows"][0]["coverage"] == 1.0
    assert out["summary"]["facet_coverage"] == 1.0


def test_rejudge_keeps_what_the_retriever_measured():
    # Regrading must not touch retrieval numbers, or the table would credit a
    # rubric change with a latency or API-call difference.
    row = rejudge(_report(), QUERY_SET, _FixedJudge([True, True]))["rows"][0]
    assert (row["top_score"], row["api_calls"], row["seconds"]) == (0.63, 3, 16.0)
    assert row["quotes"] == list(QUOTES)
    assert row["trace"] == [{"step": 1}]


def test_rejudge_records_where_it_came_from():
    # Without this a regraded file is indistinguishable from a fresh run, and
    # you cannot tell which rubric produced the number.
    out = rejudge(_report(coverage=0.5), QUERY_SET, _FixedJudge([True, True]))
    assert out["rejudged_from"] == {"judge_prompt_version": 1, "facet_coverage": 0.5}
    assert out["judge_prompt_version"] != 1


def test_rejudge_takes_facets_from_the_dataset_not_the_old_verdicts():
    # The old file labels the facet "anger"; the dataset says "anger toward
    # family". The dataset is the source of truth, or a rename would silently
    # keep grading against the stale label.
    out = rejudge(_report(), QUERY_SET, _FixedJudge([True, True]))
    assert [v["facet"] for v in out["rows"][0]["verdicts"]] == QUERY_SET[0]["facets"]


def test_rejudge_refuses_an_unjudged_run():
    report = _report()
    report["judged"] = False
    with pytest.raises(SystemExit, match="never judged"):
        rejudge(report, QUERY_SET, _FixedJudge([True]))


def test_rejudge_refuses_when_the_dataset_no_longer_has_the_query():
    with pytest.raises(SystemExit, match="dataset has changed"):
        rejudge(_report(), [{"id": "other", "text": "x", "facets": ["y"]}],
                _FixedJudge([True]))


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
