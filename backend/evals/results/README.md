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

Judge: `claude-sonnet-5`, prompt v2, 3 rounds per facet, majority wins.

| | baseline | baseline-wide | agentic | agentic-run2 | agentic-lc |
| --- | --- | --- | --- | --- | --- |
| facet coverage | 0.500 | 0.717 | 0.808 | 0.900 | 0.883 |
| **compound only** (n=17) | **0.412** | **0.667** | **0.775** | **0.882** | **0.863** |
| fully covered | 0.30 | 0.55 | 0.65 | 0.80 | 0.80 |
| mean top-1 score | 0.473 | 0.473 | **0.629** | **0.661** | **0.627** |
| quotes returned / query | 3.0 | 12.0 | 12.1 | 12.6 | 11.1 |
| API calls / query | 0 | 0 | 2.70 | 2.80 | 2.75 |
| seconds / query | 0.23 | 0.28 | 16.1 | 326 † | 16.1 |
| split judge verdicts | 0.000 | 0.026 | 0.051 | 0.051 | 0.026 |

† `agentic-run2` hit API rate limiting and spent most of that in backoff. It is
a control on *coverage*, not on latency; 16s is what the agent costs.

## What it says

**The agent beats the pipeline, and beats the volume control.** Compound
coverage goes 0.412 → 0.775–0.882. Against `baseline-wide` — the honest bar —
it is 0.667 → 0.775–0.882, so **more than half the raw gain over `baseline` is
just volume**, and 0.11–0.22 is the decomposition actually working. Both agent
runs clear the control; the margin is wide because the agent is
non-deterministic (see below).

**Mean top-1 score is the evidence that doesn't depend on any of this.** It is
raw cosine similarity — no LLM judge involved, nothing to be strict or lenient
about. `baseline` and `baseline-wide` are pinned at exactly 0.473, because `k`
cannot change what the *best* match is: returning nine more quotes never
improves the first one. All three agent runs land at 0.627–0.661. That gap is
immune to volume and immune to the judge, which makes it the single most
defensible number here.

**What it costs.** ~70× the latency (0.23s → 16s) and 2.7 API calls per query
where the baseline makes none. For a reflection someone reads once, that trade
is defensible; for autocomplete it would not be.

**The remaining misses are the corpus, not the retrieval.** On `grief-anger`
the agent searched family anger four different ways. The quote does not exist
in this corpus. No amount of agentic looping fixes a gap in the data, and a
metric that cannot distinguish those two failures would have sent us tuning the
loop forever.

## What the noise actually is

**Do not read `agentic-lc` (0.863) as better than `agentic` (0.775).** They are
the same agent, the same model, the same system prompt *object*, and the same
tool. But the reason has changed, and the earlier explanation in this repo was
wrong:

| | compound coverage |
| --- | --- |
| `agentic` | 0.775 |
| `agentic-run2` — **the same code, run again** | 0.882 |
| `agentic-lc` | 0.863 |

**Two runs of identical code differ by 0.107.** The gap to the LangGraph version
is 0.088 — *smaller* than that, and `agentic-lc` sits inside the band the
hand-rolled agent spans on its own. There is no evidence of a framework
difference.

### The earlier explanation was wrong

Stage 3 concluded the gap was **the judge** flipping on borderline facets, on
the strength of one facet coming back covered 2/6 on a fixed quote set. That
observation was real, and the rubric fix below was worth making. But "judge
noise exists" was quietly treated as "*this gap* is judge noise," and the v2
data does not support it:

- The judge is now demonstrably stable — `split_verdict_rate` is 0.000–0.051
  across all five runs, and the three previously-flipping queries come back 6/6.
- The gap did not close. It went from 0.069 to **0.088**.

The variance was never mostly in the instrument. It is in the agent: it rewords
its searches every run, so it retrieves genuinely different quote sets. The v1
judge scored the two hand-rolled runs at 0.882 and 0.873 and made them look
reproducible; the v2 judge separates them at 0.775 and 0.882 — which is the
more believable reading, because their quote sets are *not* the same.

**So the noise floor moved from the measuring instrument to the thing being
measured, and it is roughly 0.11 on compound coverage.** That is the number any
future comparison has to clear.

### What this means for the headline claim

The baseline→agent gap survives comfortably: `baseline-wide` is deterministic at
0.667, and both agent runs beat it (+0.108 and +0.215). But with **n=2** agent
runs, the *size* of that win is only known to within about a tenth. Anyone
wanting a tighter estimate should run the agent 5+ times, not build a better
judge. The judge is no longer the bottleneck.

The mean top-1 score sidesteps the problem entirely — it is cosine similarity
with no judge in the loop, and it separates 0.473 from 0.627–0.661 across every
agent run.

## The judge

### The rubric fix (prompt v2)

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

Every facet is graded three times, so residual disagreement is visible in the
table rather than hidden: `split_verdict_rate` runs 0.000–0.051, against a v1
floor of ~0.1.

### Why the judge is Sonnet, not Opus

The judge runs 3× per facet across 5 retrievers — it is the most-called model in
the project, far more than the agent it grades. Grading against a rubric this
explicit is classification, not open-ended reasoning, so it does not need the
biggest model. Sonnet 5 cut the regrade from roughly $5.50 to $2.

That is only safe if it grades the *same way*, which is a measurement, not an
assumption. Because the model is part of the judge cache key, both judges'
verdicts survive on disk and comparing them costs nothing:

```text
python evals/judge_models.py --offline

claude-opus-5  vs  claude-sonnet-5      (same v2 rubric, identical inputs)
  compared             30 facets
  agreement            0.900
  candidate stricter   3
  candidate looser     0
```

**Every disagreement runs the same direction.** Sonnet is never more generous —
stricter on 3 of 30, identical on the rest. That shape matters more than the
raw 0.900: a uniform bias shifts every retriever equally and preserves the
ranking, which is the only thing this eval needs to be right about. Scattered
disagreement would have ruled the swap out.

Two honest limits on that number. The 30 facets all come from `baseline`, the
*worst* retriever, so they are mostly uncovered facets — Sonnet's strictness in
the regime where quotes are actually good is not directly measured. And the
comparison is 30 facets, not 300, because the Opus run it is drawn from ran out
of credit partway. Extending it to the agentic files would cost ~$1.10 in Opus
calls.

The visible effect of the swap is a uniform downward shift: `baseline-wide`
0.716 → 0.667, `agentic-lc` 0.951 → 0.863. The ranking is unchanged.

## Reproducing

```bash
python evals/run.py --retriever baseline            # rescore from scratch
python evals/run.py --rejudge results/agentic.json  # regrade stored quotes only
python evals/judge_stability.py --rounds 6          # measure the judge
python evals/judge_stability.py --rounds 6 --vote 3 # measure what run.py uses
python evals/judge_models.py --offline              # compare two judges, free
```

Regrading all five files is ~$2 and about 14 minutes.

`--rejudge` exists because the agents are slow, expensive, and
non-deterministic. Re-running them to test a rubric change would confound the
two — you could not tell whether a number moved because the judge changed its
mind or because the agent searched differently. Holding the quote sets fixed and
swapping only the judge is the controlled version of that experiment.

Verdicts are cached in `../.cache/judge/` (gitignored), keyed on the rubric
version, the model, the query, the facets, the quote texts, and the round index.
Bumping `PROMPT_VERSION` discards the lot rather than silently mixing rubrics.
