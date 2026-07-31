"""How reliable is the judge?

Grades one fixed quote set several times with a cold cache each round. The
retriever is held constant, so every disagreement is the judge changing its
mind about identical input.

    python evals/judge_stability.py                       # grief-anger, 6 rounds
    python evals/judge_stability.py --query burnout-fear --rounds 10
    python evals/judge_stability.py --results agentic-lc.json

Why this exists: `agentic` and `agentic-lc` are the same agent, and they scored
0.882 and 0.951. Chasing that gap through both implementations found nothing —
it was the judge flipping on borderline facets. Any coverage difference smaller
than this script's spread is not evidence of anything.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent
RESULTS_DIR = EVALS_DIR / "results"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evals.judge import Judge  # noqa: E402


def load_row(results: Path, query_id: str) -> dict:
    rows = json.loads(results.read_text())["rows"]
    for row in rows:
        if row["id"] == query_id:
            return row
    raise SystemExit(
        f"no query {query_id!r} in {results.name}; have: "
        f"{', '.join(r['id'] for r in rows)}"
    )


def stability(row: dict, rounds: int) -> dict[str, int]:
    """Judge the same input `rounds` times. Returns covered-count per facet."""
    facets = [v["facet"] for v in row["verdicts"]]
    tally = {f: 0 for f in facets}

    for i in range(1, rounds + 1):
        # A fresh cache dir every round: the whole point is to force a real
        # judge call, and the cache exists precisely to prevent that.
        cache = Path(tempfile.mkdtemp(prefix="judge-stability-"))
        try:
            verdicts = Judge(cache_dir=cache).judge(row["text"], facets, row["quotes"])
        finally:
            shutil.rmtree(cache, ignore_errors=True)

        for v in verdicts:
            tally[v["facet"]] += bool(v["covered"])
        marks = "".join("X" if v["covered"] else "." for v in verdicts)
        print(f"  round {i:2}  [{marks}]")

    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="grief-anger")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--results", default="agentic.json",
                        help="which results file to pull the quote set from")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")

    row = load_row(RESULTS_DIR / args.results, args.query)
    print(f"\n{args.query}: {len(row['quotes'])} quotes, judged {args.rounds}x "
          f"with a cold cache")
    print(f"  {row['text']!r}\n")

    tally = stability(row, args.rounds)

    print()
    unstable = False
    for facet, n in tally.items():
        flag = ""
        if 0 < n < args.rounds:
            flag = "  <- UNSTABLE"
            unstable = True
        print(f"  {facet:34} covered {n}/{args.rounds}{flag}")

    if unstable:
        print("\n  A facet that flips on identical input sets the noise floor for"
              "\n  the whole metric. Differences smaller than that mean nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
