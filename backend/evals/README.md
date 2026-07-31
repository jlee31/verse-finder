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

Judge verdicts are cached under `.cache/judge/`, keyed by rubric version, judge
model, round index, query, facets, and the exact quote texts. A re-run costs
nothing (80s → 4s) and stays deterministic while you iterate.

Each part of that key earns its place. Scores are *excluded* so float drift
doesn't cause a spurious miss. The round index is *included*, or the rounds of a
majority vote would read back each other's verdicts and be unanimous by
construction. The model is *included*, so swapping judges doesn't reuse the old
one's answers — and as a side effect both judges' verdicts survive on disk,
which is what makes `judge_models.py` free to run. Bump `PROMPT_VERSION` when
the rubric changes.

## Which judge

`MODEL` in `judge.py`. It runs 3× per facet across 5 retrievers, so it is the
most-called model in the project — far more than the agent it grades.

`judge_models.py` compares two judges on identical inputs and reports
**facet-level** agreement, not a coverage delta: two judges can land on the same
headline number while disagreeing about which facets they covered, and that is
not the same instrument.

```bash
python evals/judge_models.py                        # opus vs sonnet
python evals/judge_models.py --offline              # only what's already cached
```

The cache is gitignored; `results/` is tracked.

## Results

**The scored comparison lives in [`results/README.md`](results/README.md)** —
one table, so it can't drift out of sync with a copy. The short version:
compound coverage goes 0.412 (baseline) → 0.667 (same search, 12 results) →
0.775–0.882 (agent), so more than half the raw gain is volume and the rest is
the agent decomposing the query. Mean top-1 score, which volume cannot move at
all, goes 0.473 → 0.63.

### A wrong turn worth keeping: the 0.882 vs 0.951 gap

> **This section records a conclusion that later turned out to be wrong.** It is
> kept because the investigation was sound and the correction is the more
> interesting half. The verdict is at the bottom.

`agentic-lc` scored 0.951 against `agentic`'s 0.882 under the v1 judge. Chasing
it through both implementations found nothing wrong with either, and the
evidence pointed at the **judge changing its mind about identical input**.

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

That is a genuine **reliability limit in the metric**: on borderline facets —
where a quote names the emotion but not its object — the v1 judge was roughly a
coin flip, and one such facet is worth ~0.06 of compound coverage on a 17-query
set. Fixing it was worth doing, and Stage 5 did: the v2 rubric rules on the
borderline explicitly (*grade the feeling, not its object*) and every facet is
graded three times. All three previously-unstable queries now come back 6/6, and
`split_verdict_rate` sits at 0.000–0.051 across every run.

### The correction

**But "judge noise exists" is not "*this gap* is judge noise," and step 4 above
only established the first.** With the judge stabilised, the gap did not close —
it went from 0.069 to 0.088.

Step 1 is where the reasoning actually went wrong. Two `agentic` runs scoring
0.882 and 0.873 was read as *the harness is reproducible*, so the remaining
variance had to be the judge. Under the v2 judge those same two runs score
**0.775 and 0.882** — a spread of 0.107, wider than the gap being explained.
The two runs retrieved genuinely different quote sets, because the agent rewords
its searches every time; the v1 judge just wasn't sharp enough to tell them
apart, and its coincidental agreement was mistaken for reproducibility.

So the conclusion survives — `agentic-lc` sits inside the band the hand-rolled
agent spans on its own, and there is no framework difference — but the mechanism
was the **agent's** non-determinism, not the judge's. The noise floor is ~0.11
and it lives in the thing being measured, not the instrument.

Full account in [`results/README.md`](results/README.md#what-the-noise-actually-is).

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
