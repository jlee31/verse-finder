# Eval harness

Measures whether a retriever actually answers everything the person said.

## Running

From `backend/`:

```bash
pytest evals -q                                   # fast tests, no model, no API
pytest evals -q -m slow                           # retriever integration (loads mpnet)

python evals/run.py --retriever baseline --no-judge   # retrieval only, no API calls
python evals/run.py --retriever baseline              # full scoring -> results/baseline.json
```

## The metric

**Facet coverage** — each query in `queries.json` is labeled with the distinct
emotional facets it contains. Coverage is the fraction of those facets that at
least one returned quote genuinely speaks to.

Cosine similarity can't answer that: a quote can score 0.42 and still be filler.
So `judge.py` asks `claude-opus-5` once per query, with the facets and quotes
together, under a rubric that explicitly rejects generic inspirational lines.

The summary reports overall coverage and **compound-only** coverage separately.
Single-facet queries are controls — the baseline scores 1.00 on all three, which
is what proves the metric isn't just measuring a broken retriever.

## Caching

Judge verdicts are cached under `.cache/judge/`, keyed by query + facets + the
exact quote texts. A re-run costs nothing (80s → 4s) and stays deterministic
while you iterate. Scores are excluded from the key so float drift doesn't cause
a spurious miss. Bump `PROMPT_VERSION` in `judge.py` when the rubric changes —
it's part of the key, so old verdicts are discarded rather than reused under new
criteria.

The cache is gitignored; `results/` is tracked.

## Baseline (2026-07-30, 20 queries)

| metric | value |
| --- | --- |
| facet coverage | 0.500 |
| compound only (17 queries) | 0.412 |
| fully covered | 0.300 |
| mean top-1 score | 0.473 |

Every later stage is measured against this.

## Adding a retriever

Add a class to `retrievers.py` with a `name` and `search(text) -> Result`, then
register it in `REGISTRY`. Nothing else changes.
