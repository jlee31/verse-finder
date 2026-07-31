"""Score a retriever over the labeled query set.

    PYTHONPATH=. python evals/run.py --retriever baseline
    PYTHONPATH=. python evals/run.py --retriever baseline --no-judge   # no API calls
    PYTHONPATH=. python evals/run.py --rejudge results/agentic.json    # regrade, don't re-retrieve
"""
import argparse
import json
import sys
import time
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent
RESULTS_DIR = EVALS_DIR / "results"

# Allow `python evals/run.py` to work without PYTHONPATH being set.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evals import metrics, retrievers  # noqa: E402
from evals.judge import PROMPT_VERSION, Judge  # noqa: E402


def display_path(path: Path) -> str:
    """Path relative to backend/ when it's under it, absolute otherwise.

    `--out` can point anywhere, so relative_to() is not safe to call blind.
    """
    try:
        return str(path.relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


def default_out_path(retriever: str, judged: bool) -> Path:
    """Where a run writes when `--out` isn't given.

    A `--no-judge` run must NOT land on `<retriever>.json`: that file is the
    committed reference baseline, and an unjudged smoke run has `summary: null`
    and no coverage numbers. Writing it there silently destroys the numbers
    every later stage is compared against.
    """
    suffix = "" if judged else ".smoke"
    return RESULTS_DIR / f"{retriever}{suffix}.json"


def load_queries(path: Path) -> list[dict]:
    queries = json.loads(path.read_text())
    validate_queries(queries)
    return queries


def validate_queries(queries: list[dict]) -> None:
    """Catch dataset mistakes here rather than as a confusing scoring bug."""
    if not queries:
        raise ValueError("query set is empty")

    seen = set()
    for i, q in enumerate(queries):
        where = f"query {i} ({q.get('id', '<no id>')})"
        for key in ("id", "text", "facets"):
            if key not in q:
                raise ValueError(f"{where}: missing {key!r}")
        if q["id"] in seen:
            raise ValueError(f"{where}: duplicate id")
        seen.add(q["id"])
        if not isinstance(q["facets"], list) or not q["facets"]:
            raise ValueError(f"{where}: facets must be a non-empty list")
        if len(set(q["facets"])) != len(q["facets"]):
            raise ValueError(f"{where}: duplicate facet labels")
        if not q["text"].strip():
            raise ValueError(f"{where}: text is empty")


def evaluate(retriever, queries: list[dict], judge: Judge | None) -> dict:
    rows = []
    started = time.time()

    for i, q in enumerate(queries, 1):
        t0 = time.time()
        result = retriever.search(q["text"])
        elapsed = time.time() - t0

        if judge is None:
            # Retrieval-only smoke run: no coverage number, just proof the
            # retriever returns sane quotes.
            verdicts = [
                {"facet": f, "covered": False, "quote": "", "reason": "not judged"}
                for f in q["facets"]
            ]
            coverage = 0.0
        else:
            verdicts = judge.judge(q["text"], q["facets"], result.quotes)
            coverage = metrics.facet_coverage([v["covered"] for v in verdicts])

        rows.append({
            "id": q["id"],
            "text": q["text"],
            "n_facets": len(q["facets"]),
            "coverage": coverage,
            "top_score": result.top_score,
            "api_calls": result.api_calls,
            "seconds": round(elapsed, 2),
            "quotes": result.quotes,
            "trace": result.trace,
            "verdicts": verdicts,
        })

        flag = "" if judge is None else ("  " if coverage == 1.0 else " <-")
        cov = "  --  " if judge is None else f"{coverage:.2f}"
        print(f"  [{i:2}/{len(queries)}] {cov}  {q['id']:28} {elapsed:5.2f}s{flag}")

    return {
        "retriever": retriever.name,
        "judged": judge is not None,
        # Which rubric and which judge produced these numbers. Two files scored
        # under different versions are not comparable, and without this you
        # cannot tell.
        "judge_prompt_version": PROMPT_VERSION if judge is not None else None,
        "judge_model": judge.model if judge is not None else None,
        "total_seconds": round(time.time() - started, 1),
        "summary": metrics.summarize(rows) if judge is not None else None,
        "rows": rows,
    }


def rejudge(report: dict, queries: list[dict], judge: Judge) -> dict:
    """Re-grade a finished run's stored quotes, without retrieving again.

    The retrievers are expensive and two of them are non-deterministic, so
    re-running them to test a rubric change would confound the two: you would
    not know whether the number moved because the judge changed its mind or
    because the agent searched differently. Holding the quote sets fixed and
    swapping only the judge is the controlled version of that experiment — and
    it costs judge calls instead of agent runs.

    Everything the retriever measured (`top_score`, `api_calls`, `seconds`)
    carries over untouched. Only the verdicts and the coverage are recomputed.
    """
    if not report.get("judged"):
        raise SystemExit(
            "that run was never judged (summary: null), so there is nothing to "
            "regrade — run the retriever properly first"
        )

    facets_by_id = {q["id"]: q["facets"] for q in queries}
    started = time.time()
    rows = []

    for i, row in enumerate(report["rows"], 1):
        facets = facets_by_id.get(row["id"])
        if facets is None:
            raise SystemExit(
                f"query {row['id']!r} is in the results file but not in the "
                f"query set — the dataset has changed; re-run the retriever"
            )

        verdicts = judge.judge(row["text"], facets, row["quotes"])
        coverage = metrics.facet_coverage([v["covered"] for v in verdicts])

        was = row["coverage"]
        moved = "" if coverage == was else f"   was {was:.2f}"
        print(f"  [{i:2}/{len(report['rows'])}] {coverage:.2f}  {row['id']:28}{moved}")

        rows.append({**row, "n_facets": len(facets), "coverage": coverage,
                     "verdicts": verdicts})

    return {
        **report,
        "judge_prompt_version": PROMPT_VERSION,
        "judge_model": judge.model,
        "rejudged_from": {
            "judge_prompt_version": report.get("judge_prompt_version"),
            "judge_model": report.get("judge_model"),
            "facet_coverage": report["summary"]["facet_coverage"],
        },
        # The retrieval time is the original run's and stays; this is only how
        # long the regrade took.
        "rejudge_seconds": round(time.time() - started, 1),
        "summary": metrics.summarize(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retriever", default="baseline",
                        choices=sorted(retrievers.REGISTRY))
    parser.add_argument("--queries", type=Path, default=EVALS_DIR / "queries.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="default: evals/results/<retriever>.json "
                             "(<retriever>.smoke.json with --no-judge)")
    parser.add_argument("--limit", type=int, default=None,
                        help="only score the first N queries")
    parser.add_argument("--no-judge", action="store_true",
                        help="skip LLM grading — retrieval smoke test, no API calls")
    parser.add_argument("--rejudge", type=Path, default=None,
                        help="regrade a finished results file's stored quotes "
                             "under the current rubric, without retrieving "
                             "again. Overwrites it unless --out says otherwise.")
    args = parser.parse_args()

    if args.rejudge and args.no_judge:
        parser.error("--rejudge regrades; --no-judge skips grading. Pick one.")

    # The judge needs ANTHROPIC_API_KEY, which lives in backend/.env.
    if not args.no_judge:
        from dotenv import load_dotenv

        load_dotenv(BACKEND_DIR / ".env")

    queries = load_queries(args.queries)

    if args.rejudge:
        # --limit deliberately ignored: the rows to regrade are whatever the
        # source file holds, and every one of them needs its facet labels.
        source = json.loads(args.rejudge.read_text())
        label = source["retriever"]
        print(f"\nregrading {label} from {display_path(args.rejudge)} "
              f"(prompt v{source.get('judge_prompt_version')} -> v{PROMPT_VERSION})")
        judge = Judge()
        report = rejudge(source, queries, judge)
    else:
        if args.limit:
            queries = queries[: args.limit]
        label = args.retriever
        print(f"\n{label} over {len(queries)} queries"
              f"{' (retrieval only)' if args.no_judge else ''}")
        print("  loading model and embeddings...")

        retriever = retrievers.build(args.retriever)
        judge = None if args.no_judge else Judge()
        report = evaluate(retriever, queries, judge)

    if report["summary"]:
        print()
        print(metrics.format_table(report["summary"], label))
        print(f"    judge cache           {judge.hits} hit / {judge.misses} miss")

    out = args.out or args.rejudge or default_out_path(
        args.retriever, judged=not args.no_judge
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    took = report.get("rejudge_seconds", report["total_seconds"])
    print(f"\n  wrote {display_path(out)}  ({took}s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
