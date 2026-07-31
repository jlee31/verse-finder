# Results

Does the agent actually retrieve better than the pipeline, or does it just cost
five extra API calls?

Each `<retriever>.json` here is one scored run over `../queries.json` — 20
queries, 17 of them compound, each labeled with its emotional facets. The
headline metric is **facet coverage**: the fraction of a query's labeled facets
that at least one returned quote genuinely speaks to, graded by an LLM judge
(`../judge.py`).

## The runs

| file | what it is | why it's here |
| --- | --- | --- |
| `baseline.json` | one search, top 3 | the shipped app — every claim is relative to this |
| `baseline-wide.json` | one search, top 12 | **the control.** Same dumb single search, just more results |
| `agentic.json` | hand-rolled loop (`app/rag/agent.py`) | the agent |
| `agentic-lc.json` | LangGraph loop (`app/rag/agent_lc.py`) | the same agent, different machinery |
| `agentic-run2.json` | `agentic` again, unchanged | **the variance control** — how much the agent moves run to run |

`baseline-wide` is the one that keeps the comparison honest. The agent returns
~12 quotes across all its searches against the baseline's 3, and more quotes
means more chances to cover a facet. Without a control at matched volume you
cannot tell "searched better" from "returned more."

## The table

Scored under judge prompt **v1**. See [Judge reliability](#judge-reliability) —
these numbers carry a noise floor of roughly 0.1, and a v2 regrade is outstanding.

| | baseline | baseline-wide | agentic | agentic-lc | agentic-run2 |
| --- | --- | --- | --- | --- | --- |
| facet coverage | 0.500 | 0.758 | 0.900 | 0.958 | 0.892 |
| **compound only** (n=17) | **0.412** | **0.716** | **0.882** | **0.951** | **0.873** |
| fully covered | 0.30 | 0.55 | 0.80 | 0.90 | 0.75 |
| mean top-1 score | 0.473 | 0.473 | 0.629 | 0.627 | 0.661 |
| quotes returned / query | 3.0 | 12.0 | 12.1 | 11.1 | 12.6 |
| API calls / query | 0 | 0 | 2.70 | 2.75 | 2.80 |
| seconds / query | 0.23 | 0.28 | 16.1 | 16.1 | 326 † |

† `agentic-run2` hit API rate limiting and spent most of that in backoff. It is
a control on *coverage*, not on latency; the 16s figure is what the agent costs.

## What it says

**The agent beats the pipeline, and beats the control.** Compound coverage goes
0.412 → 0.882. Against `baseline-wide` — the honest bar — it is 0.716 → 0.882,
so **roughly two-thirds of the raw gain over `baseline` is just volume**, and
about 0.17 is the decomposition actually working.

**Mean top-1 score is the clean evidence.** `baseline` and `baseline-wide`
score identically at 0.473, because `k` cannot change what the *best* match is
— returning nine more quotes does not improve the first one. The agent moves it
to 0.629. That number is untouchable by volume, so it isolates the one thing
the agent does that a pipeline cannot: search again, with different words.

**What it costs.** ~70x the latency (0.23s → 16s) and 2.7 API calls per query,
where the baseline makes none. For a reflection someone reads once, that trade
is defensible; for autocomplete it would not be.

**The remaining misses are the corpus, not the retrieval.** On `grief-anger`
the agent searched family anger four different ways. The quote does not exist
in this corpus. No amount of agentic looping fixes a gap in the data, and a
metric that cannot distinguish those two failures would have sent us tuning the
loop forever.

## Judge reliability

**Do not read `agentic-lc` (0.951) as better than `agentic` (0.882).** They are
the same agent, the same model, the same system prompt object, and the same
tool. Two independent lines of evidence say the gap is measurement:

1. **The same agent run twice** — `agentic` and `agentic-run2` — scores 0.882
   and 0.873. Run-to-run spread is about 0.01.
2. **Holding the quote set completely fixed** and re-grading it six times with a
   cold cache, one facet came back covered 2/6. Reproduce with
   `python evals/judge_stability.py`.

So the judge was flipping, not the code. That set a noise floor of roughly
**0.1** on this query set — which is larger than the entire agentic/agentic-lc
gap, and comfortably smaller than the baseline→agent gap of 0.17–0.47.

### The fix (prompt v2)

Every disagreement sat on one axis: **a quote that speaks to the emotion but not
to its object.** Does "holding on to anger is like grasping a hot coal" cover
the facet *anger toward family*? The v1 rubric never said, so the judge decided
afresh each time — and the four unstable facets in the set were all this same
question (`anger toward family`, `burnout and exhaustion from work`,
`losing work`, `searching for meaning`).

v2 rules on it explicitly: **grade the feeling, not its object.** A general
truth about anger covers a facet about family anger; a line that names no
emotion at all ("life is 10% what happens to you") still covers nothing. On top
of that, every facet is now graded three times and the majority wins, with the
vote count recorded in each verdict so a 2–1 call stays visible in the data.

Measured effect so far, on the three queries that were unstable under v1:

| query | v1 | v2 (6 rounds, single call) |
| --- | --- | --- |
| `grief-anger` | `anger toward family` covered 2/6 | **6/6 on both facets** |
| `job-money-family` | disagreed across runs | **6/6 on all three facets** |
| `death-meaning` | disagreed across runs | **6/6 on both facets** |

And across the 15 baseline queries regraded so far, the three voting rounds were
unanimous on every facet — `split_verdict_rate` 0.000, against a v1 floor of
~0.1. The rubric addressed the cause; the vote is insurance against the residue.

The rubric is looser, so scores rise: baseline over those 15 queries goes 0.467
→ 0.567. It rises for every retriever equally, and the metric still discriminates
— the baseline is nowhere near saturated.

### Outstanding

**The v2 regrade is not finished.** It stopped partway through `baseline.json`
when the Anthropic account ran out of credit, so **every `.json` in this
directory is still v1** and the table above is the v1 table. Completed judge
calls are cached on disk, so resuming only pays for what is left:

```
python evals/run.py --rejudge evals/results/baseline.json
python evals/run.py --rejudge evals/results/baseline-wide.json
python evals/run.py --rejudge evals/results/agentic.json
python evals/run.py --rejudge evals/results/agentic-lc.json
python evals/run.py --rejudge evals/results/agentic-run2.json
```

Then replace the table above and drop the v1 noise-floor caveat.

## Reproducing

```
python evals/run.py --retriever baseline          # rescore from scratch
python evals/run.py --rejudge results/agentic.json # regrade stored quotes only
python evals/judge_stability.py --rounds 6         # measure the judge
python evals/judge_stability.py --rounds 6 --vote 3 # measure what run.py uses
```

`--rejudge` exists because the agents are slow, expensive, and
non-deterministic. Re-running them to test a rubric change would confound the
two — you could not tell whether a number moved because the judge changed its
mind or because the agent searched differently. Holding the quote sets fixed and
swapping only the judge is the controlled version of that experiment.

Verdicts are cached in `../.cache/judge/` (gitignored), keyed on the rubric
version, the model, the query, the facets, the quote texts, and the round index.
Bumping `PROMPT_VERSION` discards the lot rather than silently mixing rubrics.
