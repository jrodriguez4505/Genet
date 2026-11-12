# Genet review brief

Notes for a reviewer, in about ten minutes: what Genet is, what every live run showed and how much of that is noise, what limits those results, and where outside thoughts would help most. Current as of v0.13.0 (11 November 2026). The full record is in [LIVE_TESTS.md](LIVE_TESTS.md).

Genet is a policy-governed agent runtime. Models propose and code decides what runs. It asks one question of every added agent: is it doing work the first could not?

## Why it exists

It began as a reaction to a claim heard often now: teams of hundreds of agents on one task, sometimes thousands. A count like that says what was spent, not what was gained. Genet takes the opposite default. A task starts with one agent, and every agent added has to earn its place by doing work the others could not.

The picture behind it is a small, cohesive team. A lead knows what each member can do, everyone works from the same goal and purpose, responsibility is shared, and the outcome is the lead's. The yardstick is whether the team does better than its members could alone.

## How it works

The lead can propose sub-agents, but only as text in a fixed JSON reply, which the kernel treats as untrusted input. Three gates in code judge each proposal, in order, and each one fails closed. No reply can touch the roster, the tools or the budget, and every decision goes on the run's log. An independent verifier, shown files the kernel picks, checks the product before a run finishes.

1. **Can someone else?** Refused if the work is already covered, already staffed, a repeat, or verification.
2. **Should we?** Needs a named failure and a measured reason: declared isolation, or material that does not fit one call.
3. **Could we?** Needs a known skill, a tier that allows a split, a budget for the work plus merge and verify, and room under the cap of 4.

Since 11 November a split rule comes before the gates. When files are read a page at a time and one agent reading a page of each file can hold what the goal needs in one call, there is no planning call at all: the lead works alone. Otherwise the lead plans and the gates judge the plan as before.

## How many agents a task needs

The test aimed most directly at the question. The same questions over 20 companies' notes, split by the kernel into 2, 4, 10 or 20 parts, one sub-agent each, against one agent and against Genet's own plan. Twice: with each call capped at 8,000 tokens, where the 20 files do not fit one call, and at 64,000, where they do. Both limits are Genet's own, set to make work that does not fit one call at small scale; the model takes far more. Haiku 5.5, 12 questions a row, bars written before the run.

| Right of 12 (tokens a question) | 8,000: does not fit one call | 64,000: fits one call |
|---|---|---|
| One agent | 1 (54k) | 11 (82k) |
| 2 parts | 0 (42k) | 12 (53k) |
| **4 parts** | **10 (52k)** | **12 (41k)** |
| 10 parts | 11 (65k) | 12 (64k) |
| 20 parts | 9 (98k) | 9 (100k) |
| Genet's own plan | 9 (54k) | 11 (90k), one agent |

- **At 8,000, splitting was needed, and about four was right.** One agent's 1 of 12 against 8 to 11 for every working split is beyond noise (p at most 0.01). Four parts cost the fewest tokens of the settings that worked, and were as right as any.
- **At a real limit, one agent kept up.** At 8,000 one agent could not page through the notes, so it could not see most of them. With each note grown to 30,000 characters, about 270,000 tokens a question against a real 100,000-token limit, one agent that searched got 6 of 12, 4 parts 4 and Genet 4: within noise. Most of the runs that stopped had products that said themselves they were unfinished, among look-alike names, other years' figures and undated lines. So the sweep's big win for splitting was the 8,000 cap's.
- **Splitting's one gain beyond noise is time.** On the big work, parts running side by side finished 34 to 57% sooner. On Loong's smaller work, Genet's planning call and merge made it 27% slower than one agent.
- **Twenty agents cost about twice as much,** beyond noise, and were no more right. Each saw one file, so none could tell a company from its look-alike, and the lead had 20 reports to merge.
- **On Sonnet 5.5 the count changed the cost, not the answer.** Rerun at 8,000, every split got the right answer on all 12 questions, at 4, 10 and 20 parts alike, and nothing finished wrong. 10 parts cost 1.56 times the tokens of 4, and 20 parts 2.35 times.
- **Too few fails when a part does not fit.** Two parts of 10 files stopped on size 10 times in 12.
- **Keeping fitting work to one agent costs tokens.** Where the work fits, one agent sends everything it has read again every round: twice the tokens of 4 parts. Prompt caching closed most of that gap in a follow-up (1.12 times), but the cached single agent read less and finished 3 answers wrong, so it is off until rerun.

## Across models

The same 66 trials run on Haiku 5.5, Sonnet 5.5 and Opus 5.5 with identical settings, so each pairs question by question: 10- and 20-company questions, one agent, the told crew and Genet.

| One question set, 66 trials | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Right answers | 52 | 59 | 59 |
| Finished with a wrong answer | 4 | 0 | 1 |
| 20 companies, one agent, of 6 | 0 | 0 | 0 |
| 20 companies, Genet, of 6 | 2 | 5 | 6 |
| Cost, and per right answer | $0.46, $0.009 | $5.82, $0.099 | $11.78, $0.200 |

- **What is left of the errors is reading.** Haiku's wrong answers set a true figure aside because a prior-year line or a look-alike's note sat next to it. Across two question sets Sonnet finished wrong 0 times in 132, Haiku 6.
- **Opus matched Sonnet at twice the price.** Its one wrong answer was a sum off by 0.1, not a figure set aside.
- **A stronger checker does not make up for the reader.** Haiku authors with a Sonnet verifier, 120 trials, cut wrong answers from 5 to 2 but stopped 16, against 7 for Haiku alone and 4 for Sonnet.
- **The design holds on all three,** at this limit. One agent cannot do the 20-company work here, which is a size limit by construction. Genet's own plan got better with the model: 2, 5 and 6 of 6.

## Against another framework

Genet against CrewAI 1.15.30 in its hierarchical mode, a manager and 4 readers, on public questions, run on 9 November. Loong: 40 questions over real 2024 SEC filings, 240,000 to 517,000 characters a question, judged by Sonnet 5.5 with Loong's own prompt. HotpotQA: 20 short questions, exact match. Haiku 5.5 for every contender, the same limits (100,000 tokens a call, 80 calls), and CrewAI on its own native tool calls with Genet's client underneath to size, cap and tape every call. Bars written first; $2.85 in all.

| Loong, of 40 | One agent | Told crew | Genet, as run 9 November | CrewAI |
|---|---|---|---|---|
| Right (judge score of 80 or more) | 22 | 20 | 20 | 25 |
| Finished with a wrong answer | 15 | 14 | 12 | 15 |
| Tokens a question | 75k | 95k | **88k** | 127k |
| HotpotQA right, of 20 | 12 | 9 | 12 | 8, or 12 in substance |

- **No right or wrong difference here is beyond noise.** Genet missed the accuracy bar it set itself, CrewAI's 25 less 3, but CrewAI's 25 against Genet's 20 is p 0.12 on 40 questions, and Genet's 12 wrong against CrewAI's 15 is p 0.45.
- **The token gap is beyond noise.** Genet used 39,600 fewer tokens a question than CrewAI (95% range 5,100 to 76,100), and one agent fewer still.
- **Where Genet split, it was right on 4 of 13,** where one agent got 7. Too few to settle on its own, but it pointed the next test at the decision to split (below). Since 11 November, Genet keeps every one of these 40 questions to one agent, so today's Genet is the one-agent column.
- **The judge's cut-off matters.** Sonnet gave no answer 100, even one that matched word for word, so right became 80 or more, set from the calibration before results. At 90, CrewAI falls to 19.

### Four fixes after the split, all left off

Read again, the tapes showed two things after a split. The parts each flagged that the line a question names was not in their filing, and the lead's merge carried the flags up as a hedge. The checker then failed the merge, often for a figure "not read", which the merging lead had no tool to read. Each fix below was tested live with its bars written first.

| Fix, and the trials it was tested on | Right | Finished wrong | Bars |
|---|---|---|---|
| Writers told a filing may name a line differently, and to use the line that measures the same thing. Told crew and Genet, the 9 questions this hit, 18 trials | 6 to 8 | 4 to 6 | missed |
| A narrower note: only the same measure under another name, and the checker told the same. 12 Loong questions no earlier run used, 24 trials | 9 to 10 | 8 to 11 | missed |
| The rework after a merge may read, as a single agent's can. The 20 split trials whose merge the checker sent back, live from the rework on | 0 to 4 | 3 to 9 | 2 of 3 missed |
| The rework carries what the failed product's call read, so it reads again only what is missing. The 36 Loong trials whose rework follows a read, live from the rework on | 7 to 6 | 19 to 21 | all 3 missed |

- **Each fix took away a reason to stop, and more wrong answers finished than right ones.** Every one of these right and wrong differences is within noise, too, so none earned its place. The kept pages also raised tokens, from 6.1 to 7.2 million on the 36.
- **What was left after reading was not reading.** When the rework read and quoted its figures, the checker passed them. The new wrong answers dated figures by the statement's period where Loong dates them by the file, answered "cannot be determined" for a line name no filing uses, or put a company one size band off.

## When to split: the split rule

The tests moved earlier, to the decision to split. The rule: with paged reads, when one agent reading a page of each file can hold what the goal needs in one call, the lead works alone with no planning call. When it cannot, Genet plans and splits as before. On the CrewAI 40 it keeps every question to one agent, and on every generated tape it changes nothing.

First run, 10 November, on 54 Loong questions no earlier run used: right 24 to 28, wrong 24 to 24, but tokens rose because of two long trials, so one of its three bars missed and it stayed off. The rule changes only the questions Genet splits, so the 54 were drawn again, with bars written first and read where the rule acts.

| The 51 trials where Genet split, two draws | Genet as it was | The split rule |
|---|---|---|
| Right | 16 | **24** (+8 / -0, p 0.008) |
| Finished with a wrong answer | 24 | 26 |
| Stopped | 11 | 1 |
| Time a question | 28.4 s | **19.7 s** (-31%, p under 0.001) |
| Tokens a question | about the same | -1.3k, within noise |

- **All three bars held,** and it became the default on 11 November. Each draw alone gave the same +4 / -0. Wherever the two differed on a right answer, the rule was the one that was right.
- **The gain was Genet's stops.** Split runs often ended with the checker refusing the merge. One agent reading page by page answered most of those, 5 of 11 right.
- **Over all 54 questions in each draw it is within noise** (right 49 to 56, p 0.09). The rule acts on under half of them; where Genet keeps one agent it changes nothing.
- **On big work it still splits.** Where a page of each file does not fit one call, as in the real-limit test above, it plans as Genet always did: 12 of 12 replayed identically.

## What the tapes said about the checker

Every live run is taped, and since 11 November a tape marks the trial behind each request, so any part of a run replays exactly at no cost. Read that way, the checker's work was audited and two kernel bugs were found.

- **The rework pays on generated questions and is about even on real filings.** On the generated tapes it fixed 35 wrong products for 2 it broke. Under the split rule on Loong, 24 of 108 trials were reworked and ended 9 right, 11 wrong and 4 stopped, at 19% of the tokens.
- **The checker turned down right answers about 3 times in 10.** The judge scored 7 of the 24 failed products right. The rework gave 5 of those back and turned none wrong; of the other 17, 11 went back out wrong.
- **Two causes of its false alarms were the kernel's own, both now fixed.**
  - Loong's 2024 filings put an invisible zero-width space after many figures. A quote leaves it out, and the kernel's quote check did not read it as a space, so 31 of its 190 flags on the Loong tapes were false.
  - The kernel put the product's evidence, its quote check and the sources straight after the product, with nothing to mark where the product ends. Of 28 failures saying "the ANSWER line is not last", 26 were of products that end with it.
- **Each fix was measured live from the first request it changes.** A trial replays its tape up to there and runs live from that point.
  - The quote fix touched 11 trials: no answer changed, and three reworks caused only by false flags were saved.
  - The marked view, rerun on all 108 trials from their first check: answers within noise (right 56 to 57, wrong 48 to 47), the checker's failures down from 28 to 20, and the false complaint down from 4 to 1.
- **Old runs stay reproducible.** Each changed setting is recorded in a run's config, and a tape from before replays under what it ran with.

## Where it stands

**Built and on**
- The gates, and rules in code that refuse illegal changes to a run.
- The split rule: one agent wherever a page of each file fits one call.
- Hard budgets on calls, tokens and time, and read-only sandboxed tools.
- An independent verifier, shown files the kernel picks, a quote check in code, and a view that marks where the product ends.
- A second try at a refused plan, a rework told what the verifier said, and rounds of reads that fit the next call.
- Tapes that replay live runs exactly with no key, noise with every comparison (`taskorg paired`), and fixes measured live from the first request they change.
- Blameless reviews of failed runs.
- Fixes from an independent security review on 11 November. It found nothing in the model-output boundary and ten issues outside it ([SECURITY.md](../SECURITY.md)).

**Built, off**
- A different model per role, priced per model. Tried once: a Sonnet checker over Haiku authors did not reach Sonnet alone.
- Prompt caching, and fixed splits of 2 to 20 parts for measuring.
- Three ways to stop answers that set a figure aside: two verifier sentences and a check in code. Each stopped wrong answers and too many right ones.
- Four fixes after a split on real filings: two notes on line names, a rework that may read, and one that keeps its pages.
- `--cards`, `--report-up` and `--author-rule headed`.

**Designed only**
- A reviewer that checks the plan against the purpose.
- Methods made of moves the kernel runs, so a chain is not split.
- Teams that nest under the same gates, and a lead that can be replaced from the record.

## What limits all of this

- **Mostly one kind of task.** Questions over generated company notes, with prior-year figures and look-alike names as traps, and public runs on Loong (40 questions, then 54 more in two draws) and 20 HotpotQA questions.
- **Scale, at a real limit once.** Most runs use 20 files of about 900 tokens, with calls capped at 8,000 tokens. One test grew the notes past a real 100,000-token limit, and there one agent that searched kept up with the splits.
- **Three models, unevenly.** Haiku 5.5 for most runs, Sonnet 5.5 on two question sets and the sweep, Opus 5.5 on one question set.
- **Small counts.** 12 to 54 questions an arm. Every readout now gives its noise, and on Loong every right or wrong difference so far is within it, except the split rule's gain where it acts. Live testing so far cost about $61 in model calls.
- **One outside comparison.** CrewAI as configured here, on one benchmark subset, one call limit and one model, against Genet as it was on 9 November.

## Where thoughts would help most

1. **Should the split decision weigh cost and time as well as fit?** Where the work fits one call, 4 parts cost half what one agent did. On big work, parts side by side finished a third to a half sooner, and that is splitting's one gain beyond noise so far. Is that a rule for the gate, or a reason to cache?
2. **Is a fixed cap of 4 sub-agents right?** The sweep says about four on this work. What would make the cap a measured number rather than a constant?
3. **Is a wrong answer worse than no answer?** On real filings the rework ends about as often wrong as right, and every verifier rule tried so far stopped wrong answers and right ones in about equal numbers. Where would you draw the line for a task like this?
4. **Is the kernel worth its weight?** The split rule's gain on Loong came from not splitting, and at a real limit one agent that searched kept up. The gates' clearest gains are keeping work to one agent and time on big work.
5. **Is replaying a tape to the first request a change touches, then going live, a sound way to measure a fix?** It keeps everything before that point identical and costs a fraction of a rerun. What would you check about it?
6. **What test would convince you?** Which real task, at what size, would make or break the idea?
7. **Where would you split `loop.py`?** It is about 1,400 lines and holds briefs, calls, staffing, merge and verify.

The full list of open questions is in [ARCHITECTURE.md](../ARCHITECTURE.md), along with the design decisions and why each was made.

## How to look at it

- [ARCHITECTURE.md](../ARCHITECTURE.md): start here. Written for a reviewer: run flow, modules, rules, decisions and open questions.
- [README.md](../README.md): how to use it, and a summary of the live results.
- [LIVE_TESTS.md](LIVE_TESTS.md): every run on a real model, with its bars, costs, noise and what it did not show.
- [TEAM_DESIGN.md](TEAM_DESIGN.md): where the team goes next, with related work.

None of this needs a key or spends anything. The tests take a minute or two.

```bash
git clone https://github.com/jrodriguez4505/Genet
cd Genet
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 or later
pip install -e ".[dev]"
pytest -q                                            # no network, no key
python -m taskorg.cli compare --adapter sim          # simulated reader, $0
```

Runs through 6 November can be replayed from [the published tapes](https://github.com/jrodriguez4505/Genet/releases), each with its replay command. The tapes since are kept locally for now. The head-to-head's hold SEC filing text and HotpotQA paragraphs, so they wait on a licence check.
