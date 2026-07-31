# Eval harness

Measures whether a retriever actually answers everything the person said.

## Running

From `backend/`:

```bash
pytest evals -q                                   # fast tests, no model, no API
pytest evals -q -m slow                           # retriever integration (loads mpnet)

python evals/run.py --retriever baseline --no-judge   # retrieval only, no API calls
python evals/run.py --retriever baseline              # full scoring -> results/baseline.json
python evals/run.py --rejudge results/baseline.json   # regrade stored quotes, don't re-retrieve
```

A `--no-judge` run writes `results/<retriever>.smoke.json`, not
`<retriever>.json` — it has no coverage numbers, and landing it on the tracked
baseline would wipe the reference every later stage is compared against.

`--rejudge` is for changing the *judge*. The agents are slow, expensive and
non-deterministic, so re-running them after a rubric change confounds two
variables: you can't tell whether a number moved because the judge changed its
mind or because the agent searched differently. Regrading the stored quote sets
holds retrieval fixed and swaps only the rubric. `top_score`, `api_calls` and
`seconds` carry over untouched; the file records `rejudged_from` so a regraded
run is never mistaken for a fresh one.

## The metric

**Facet coverage** — each query in `queries.json` is labeled with the distinct
emotional facets it contains. Coverage is the fraction of those facets that at
least one returned quote genuinely speaks to.

Cosine similarity can't answer that: a quote can score 0.42 and still be filler.
So `judge.py` asks `claude-opus-5` per query, with the facets and quotes
together, under a rubric that explicitly rejects generic inspirational lines.

Each facet is graded **three times and the majority wins** (`ROUNDS` in
`judge.py`), and each verdict records its `votes` so a 2–1 call stays visible in
the results file. `summary.split_verdict_rate` is how often the rounds
disagreed — the metric's own error bar, measured on the run it belongs to.

The summary reports overall coverage and **compound-only** coverage separately.
Single-facet queries are controls — the baseline scores 1.00 on all three, which
is what proves the metric isn't just measuring a broken retriever.

## Caching

Judge verdicts are cached under `.cache/judge/`, keyed by query + facets + the
exact quote texts + the round index. A re-run costs nothing (80s → 4s) and stays
deterministic while you iterate. Scores are excluded from the key so float drift
doesn't cause a spurious miss; the round index *is* in the key, or the rounds of
a majority vote would read back each other's verdicts and be unanimous by
construction. Bump `PROMPT_VERSION` in `judge.py` when the rubric changes — it's
part of the key, so old verdicts are discarded rather than reused under new
criteria.

The cache is gitignored; `results/` is tracked.

## Results

**The scored comparison lives in [`results/README.md`](results/README.md)** —
one table, so it can't drift out of sync with a copy. The short version:
compound coverage goes 0.412 (baseline) → 0.716 (same search, 12 results) →
0.882 (agent), so about two-thirds of the raw gain is volume and the rest is the
agent decomposing the query. Mean top-1 score, which volume cannot move at all,
goes 0.473 → 0.629.

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

**Consequence.** Any coverage difference under ~0.1 on this query set was
unmeasurable under prompt v1. The baseline-to-agent gap (0.716 → 0.88) is many
times that and stood regardless — but the implementation comparison did not.

**Resolved in Stage 5 (prompt v2).** The rubric now rules on the borderline
explicitly — *grade the feeling, not its object* — and each facet is graded
three times with the majority winning. All three previously-unstable queries now
come back 6/6. Full account, including what is still outstanding, in
[`results/README.md`](results/README.md#judge-reliability).

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
