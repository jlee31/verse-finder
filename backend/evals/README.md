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

## Results (2026-07-31, 20 queries)

| metric | baseline | baseline-wide | agentic | agentic-lc |
| --- | --- | --- | --- | --- |
| facet coverage | 0.500 | 0.758 | 0.900 | 0.958 |
| compound only (17 queries) | 0.412 | 0.716 | 0.882 | 0.951 |
| fully covered | 0.300 | 0.550 | 0.800 | 0.900 |
| mean top-1 score | 0.473 | 0.473 | **0.629** | **0.627** |
| API calls / query | 0 | 0 | 2.70 | 2.75 |
| seconds / query | 0.4 | 0.4 | 16 | 16 |

`agentic` is the hand-rolled loop; `agentic-lc` is the same agent in LangGraph.

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

### The 0.882 vs 0.951 gap is the judge, not the implementations

`agentic-lc` scored 0.951 against `agentic`'s 0.882. Chasing that through both
implementations found nothing wrong with either — the difference is the **judge
changing its mind about identical input**.

The trail:

1. A second `agentic` run scored 0.892 / 0.873 compound, near-identical to the
   first. Only 2 of 20 queries moved, in opposite directions. So the harness is
   reproducible in aggregate and the 0.951 isn't obviously sampling luck.
2. But `grief-anger` and `burnout-fear` failed in **both** `agentic` runs and
   passed for `agentic-lc` — stable disagreement, not coin flips.
3. Both agents had retrieved the same anger material. The judge's own words
   give it away. On `agentic`: *"Anger quotes are generic and not about family
   conflict"* → uncovered. On `agentic-lc`: covered, because *"quotes address
   anger and resentment, **though not the family relational aspect**"* — the
   same observation, opposite verdict.
4. Held the quote set fixed and judged it six times with a cold cache:

   ```text
   grief over losing a parent       covered 6/6
   anger toward family              covered 2/6   <- UNSTABLE
   ```

Reproduce it with `python evals/judge_stability.py`.

So the two implementations are the same agent, as designed. What the exercise
actually found is a **reliability limit in the metric**: on borderline facets —
where a quote names the emotion but not its object — the judge is roughly a
coin flip, and one such facet is worth ~0.06 of compound coverage on a 17-query
set.

**Consequence for Stage 5.** Any coverage difference under ~0.1 on this query
set is unmeasurable as things stand. Fixing it means majority-voting the judge
over 3 rounds, or sharpening the rubric so "names the emotion but not its
object" resolves the same way every time — and re-running every retriever after
a `PROMPT_VERSION` bump. The baseline-to-agent gap (0.716 → 0.88) is many times
the noise floor and stands regardless.

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
