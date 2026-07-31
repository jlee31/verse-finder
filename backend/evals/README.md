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

A `--no-judge` run writes `results/<retriever>.smoke.json`, not
`<retriever>.json` — it has no coverage numbers, and landing it on the tracked
baseline would wipe the reference every later stage is compared against.

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

## Results (2026-07-30, 20 queries)

| metric | baseline | baseline-wide | agentic |
| --- | --- | --- | --- |
| facet coverage | 0.500 | 0.758 | **0.900** |
| compound only (17 queries) | 0.412 | 0.716 | **0.882** |
| fully covered | 0.300 | 0.550 | **0.800** |
| mean top-1 score | 0.473 | 0.473 | **0.629** |
| API calls / query | 0 | 0 | 2.7 |
| seconds / query | 0.4 | 0.4 | 16 |

`baseline-wide` is the same one-shot search at k=12 — the **volume control**. The
agent returns roughly that many quotes across all its searches, and more quotes
means more chances to cover a facet. Without this column, most of the agent's
apparent win is just volume: raw k takes compound coverage from 0.412 to 0.716
with no intelligence at all.

Against that honest bar the agent still wins clearly, 0.716 → 0.882. The
cleanest evidence it isn't volume is the **mean top-1 score**: k cannot change
which quote ranks first, so `baseline-wide` is pinned at the baseline's 0.473,
while the agent reaches 0.629. Rephrasing a facet into its own query finds
better matches, not just more of them.

It costs 2.7 API calls and ~40x the latency per query.

### Where it still fails, and why

The four queries below 1.00 are **corpus limits, not agent failures**. On
`grief-anger` the agent ran four searches, two of them aimed squarely at family
anger — `"anger and resentment toward one's own family"` and `"feeling let down
and hurt by the people closest to me"` — and the judge still marked the facet
uncovered: *"Anger quotes are generic and none address family conflict."* There
is no such quote in the 1,625 to find. `tired-lonely-meaningless` spent its
whole six-search budget and never found loneliness or meaninglessness.

Better searching cannot retrieve what was never written down. The next real
coverage gain is a bigger corpus, not a smarter loop.

## Adding a retriever

Add a class to `retrievers.py` with a `name` and `search(text) -> Result`, then
register it in `REGISTRY`. Nothing else changes.
