"""Score a retriever over the labeled query set.

    PYTHONPATH=. python evals/run.py --retriever baseline
    PYTHONPATH=. python evals/run.py --retriever baseline --no-judge   # no API calls
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
from evals.judge import Judge  # noqa: E402


def display_path(path: Path) -> str:
    """Path relative to backend/ when it's under it, absolute otherwise.

    `--out` can point anywhere, so relative_to() is not safe to call blind.
    """
    try:
        return str(path.relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


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
        "total_seconds": round(time.time() - started, 1),
        "summary": metrics.summarize(rows) if judge is not None else None,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retriever", default="baseline",
                        choices=sorted(retrievers.REGISTRY))
    parser.add_argument("--queries", type=Path, default=EVALS_DIR / "queries.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="default: evals/results/<retriever>.json")
    parser.add_argument("--limit", type=int, default=None,
                        help="only score the first N queries")
    parser.add_argument("--no-judge", action="store_true",
                        help="skip LLM grading — retrieval smoke test, no API calls")
    args = parser.parse_args()

    # The judge needs ANTHROPIC_API_KEY, which lives in backend/.env.
    if not args.no_judge:
        from dotenv import load_dotenv

        load_dotenv(BACKEND_DIR / ".env")

    queries = load_queries(args.queries)
    if args.limit:
        queries = queries[: args.limit]

    print(f"\n{args.retriever} over {len(queries)} queries"
          f"{' (retrieval only)' if args.no_judge else ''}")
    print("  loading model and embeddings...")

    retriever = retrievers.build(args.retriever)
    judge = None if args.no_judge else Judge()

    report = evaluate(retriever, queries, judge)

    if report["summary"]:
        print()
        print(metrics.format_table(report["summary"], args.retriever))
        print(f"    judge cache           {judge.hits} hit / {judge.misses} miss")

    out = args.out or RESULTS_DIR / f"{args.retriever}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\n  wrote {display_path(out)}  ({report['total_seconds']}s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
