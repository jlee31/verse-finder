"""Scoring functions for the retrieval eval.

Pure functions over already-collected data — no model loading, no API calls —
so they can be tested without touching the network.
"""
from statistics import mean


def facet_coverage(covered: list[bool]) -> float:
    """Fraction of a query's facets that at least one returned quote addressed.

    This is the headline metric. A compound query like "grieving my dad and
    angry at my family" has two facets; if the results only speak to grief,
    coverage is 0.5.
    """
    if not covered:
        raise ValueError("a query must have at least one facet")
    return sum(covered) / len(covered)


def summarize(rows: list[dict]) -> dict:
    """Aggregate per-query rows into the numbers that go in the results table.

    Each row needs "coverage", "top_score", "n_facets", and "api_calls".
    """
    if not rows:
        raise ValueError("no rows to summarize")

    compound = [r for r in rows if r["n_facets"] > 1]
    verdicts = [v for r in rows for v in r.get("verdicts", [])]

    return {
        "n_queries": len(rows),
        "facet_coverage": mean(r["coverage"] for r in rows),
        # The compound queries are the ones the agent is meant to fix, so they
        # get their own line — a strong single-facet score can otherwise mask
        # a flat result on the cases that motivated the work.
        "facet_coverage_compound_only": (
            mean(r["coverage"] for r in compound) if compound else None
        ),
        "n_compound": len(compound),
        "fully_covered_rate": mean(1.0 if r["coverage"] == 1.0 else 0.0 for r in rows),
        "mean_top_score": mean(r["top_score"] for r in rows),
        "mean_api_calls": mean(r["api_calls"] for r in rows),
        # How often the judge's rounds disagreed about the same facet on the
        # same quotes. This is the metric's own error bar, measured on the run
        # it belongs to: two retrievers whose coverage differs by less than
        # this have not been shown to differ at all.
        "split_verdict_rate": split_verdict_rate(verdicts),
    }


def split_verdict_rate(verdicts: list[dict]) -> float | None:
    """Fraction of facet verdicts the judge's rounds did not agree on.

    None when the verdicts carry no vote counts — a single-round run, or a
    results file written before majority voting existed.
    """
    voted = [v for v in verdicts if v.get("rounds", 1) > 1]
    if not voted:
        return None
    return mean(1.0 if 0 < v["votes"] < v["rounds"] else 0.0 for v in voted)


def format_table(summary: dict, label: str) -> str:
    """Render a summary as a plain-text block for the terminal."""
    def fmt(v):
        return "  n/a" if v is None else f"{v:.3f}"

    return "\n".join([
        f"  {label}",
        f"    queries               {summary['n_queries']} ({summary['n_compound']} compound)",
        f"    facet coverage        {fmt(summary['facet_coverage'])}",
        f"    ^ compound only       {fmt(summary['facet_coverage_compound_only'])}",
        f"    fully covered         {fmt(summary['fully_covered_rate'])}",
        f"    mean top-1 score      {fmt(summary['mean_top_score'])}",
        f"    mean API calls/query  {fmt(summary['mean_api_calls'])}",
        f"    split judge verdicts  {fmt(summary.get('split_verdict_rate'))}",
    ])
