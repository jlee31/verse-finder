"""Do two judge models agree?

The judge is the measuring instrument, so swapping it for a cheaper model is
only safe if it grades the same way. This compares two models' verdicts on
**identical inputs** — same query, same facets, same quotes, same rubric — and
reports facet-level agreement.

    python evals/judge_models.py
    python evals/judge_models.py --baseline claude-opus-5 --candidate claude-sonnet-5

It reads verdicts out of the judge cache and calls the API only for the ones
that aren't there yet. Once both models have graded a run, this costs nothing:
the model is part of the cache key, so switching judges leaves the old judge's
answers on disk rather than overwriting them.

Agreement is reported per facet rather than as a coverage delta. Two judges can
land on the same headline number while disagreeing about which facets were
covered, and that would not be the same instrument.
"""
import argparse
import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent
RESULTS_DIR = EVALS_DIR / "results"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evals.judge import Judge  # noqa: E402

DEFAULT_RESULTS = ["baseline", "baseline-wide", "agentic", "agentic-lc"]


def verdicts_for(judge: Judge, rows: list[dict], facets_by_id: dict) -> dict:
    """`{(query_id, facet): covered}` for one judge.

    Offline, a row with no cached verdict is skipped rather than fatal: a judge
    that only ever graded part of the set is still worth comparing over the
    part it did, and `compare()` scores the overlap. Bailing on the first miss
    would throw away a usable comparison.
    """
    out = {}
    for row in rows:
        facets = facets_by_id.get(row["id"])
        if facets is None:
            continue
        try:
            graded = judge.judge(row["text"], facets, row["quotes"])
        except RuntimeError:
            continue  # offline and uncached
        for v in graded:
            out[(row["id"], v["facet"])] = v["covered"]
    return out


def compare(baseline: dict, candidate: dict) -> dict:
    """Agreement between two judges over the facets they both graded."""
    shared = sorted(set(baseline) & set(candidate))
    if not shared:
        raise SystemExit("the two judges have no facets in common to compare")

    disagreements = [k for k in shared if baseline[k] != candidate[k]]
    # Which direction the candidate leans matters more than the raw rate: a
    # judge that is uniformly more generous shifts every retriever equally and
    # preserves the ranking, while scattered disagreement does not.
    stricter = [k for k in disagreements if baseline[k] and not candidate[k]]

    return {
        "n": len(shared),
        "agreement": (len(shared) - len(disagreements)) / len(shared),
        "disagreements": disagreements,
        "candidate_stricter": len(stricter),
        "candidate_looser": len(disagreements) - len(stricter),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="claude-opus-5",
                        help="the judge the committed numbers were scored with")
    parser.add_argument("--candidate", default="claude-sonnet-5",
                        help="the judge being considered as a replacement")
    parser.add_argument("--results", nargs="+", default=DEFAULT_RESULTS)
    parser.add_argument("--rounds", type=int, default=1,
                        help="grading calls per verdict; 1 compares the raw models")
    parser.add_argument("--offline", action="store_true",
                        help="compare only what's already cached — no API calls")
    parser.add_argument("--queries", type=Path, default=EVALS_DIR / "queries.json")
    args = parser.parse_args()

    if not args.offline:
        from dotenv import load_dotenv

        load_dotenv(BACKEND_DIR / ".env")

    facets_by_id = {q["id"]: q["facets"] for q in json.loads(args.queries.read_text())}
    rows = []
    for name in args.results:
        path = RESULTS_DIR / f"{name}.json"
        if path.exists():
            rows.extend(json.loads(path.read_text())["rows"])

    print(f"\n{args.baseline}  vs  {args.candidate}")
    print(f"  {len(rows)} scored queries, {args.rounds} round(s) per verdict\n")

    graded = {}
    for model in (args.baseline, args.candidate):
        judge = Judge(offline=args.offline, rounds=args.rounds, model=model)
        graded[model] = verdicts_for(judge, rows, facets_by_id)
        if not graded[model]:
            raise SystemExit(
                f"no cached verdicts for {model}; drop --offline to grade with it"
            )
        print(f"  {model:20} {len(graded[model]):3} facets "
              f"({judge.hits} cached / {judge.misses} fetched)")

    report = compare(graded[args.baseline], graded[args.candidate])

    print(f"\n  compared             {report['n']} facets")
    print(f"  agreement            {report['agreement']:.3f}")
    print(f"  candidate stricter   {report['candidate_stricter']}")
    print(f"  candidate looser     {report['candidate_looser']}")

    if report["disagreements"]:
        print("\n  where they differ:")
        for qid, facet in report["disagreements"]:
            was = "covered" if graded[args.baseline][(qid, facet)] else "uncovered"
            now = "covered" if graded[args.candidate][(qid, facet)] else "uncovered"
            print(f"    {qid:28} {facet:34} {was} -> {now}")
    else:
        print("\n  the two judges agreed on every facet.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
