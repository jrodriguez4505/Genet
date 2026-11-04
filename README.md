# Genet

[Apache-2.0](LICENSE) · Python 3.11+ · kernel, not a cloud · [Website](https://jrodriguez4505.github.io/Genet/)

One organism. Many stems.

**The question is not how many agents you can run. It is whether a second one is doing new work.**

Genet is a policy-governed agent runtime: models propose, and code decides what runs. Agent counts have become a headline number, with products advertising hundreds of sub-agents on one task, but a count says what was spent, not what was gained. Most stacks treat headcount as capacity; Genet treats it as a cost. A task starts with one lead agent (the orchestrator). The lead may propose sub-agents, each with the skill its sub-task needs, and policy gates in code decide whether any of them run. Default is a single agent. Authority lives in the graph, not in the prompt.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/patterns-dark.svg">
  <img alt="Three ways to staff the same task: a single agent; an always-split crew that pays for a planner, workers and a merge every time; and Genet, where policy gates decide whether a fan-out happens at all." src="docs/img/patterns-light.svg" width="100%">
</picture>

*Same task, three ways to staff it. A crew fans out on every task. Genet's lead proposes, and the gates decide whether a fan-out happens at all.*

The team is small, and every agent can switch skills, with specialists added only when a sub-task needs one. The lead owns the roster. The goal stays fixed while the method changes. Work fans out to sub-agents only when the gates find a measured reason, then merges back. The gates do not yet check that the parts are independent: a chain whose material does not fit one call can still split (design part 9).

Quality of process over quantity of agents: possibly more efficient, and possibly more effective. That stays a claim until measured. `taskorg compare` exists to measure it (see [Proving it](#proving-it)).

## The team

Genet is built for a small, cohesive team:

- The lead knows what each member can do.
- Members differ where it matters: in what they see, what they may open, and which model fills them. They do not differ by a persona in the prompt.
- Everyone works from the same goal, purpose and done-when.
- Responsibility is shared. Decisions and the outcome are the lead's.

Every agent is the same model and could hold any skill. So a member is a position, not a kind of agent, and authority belongs to the position. Each member the team adds must do work the others could not.

Built so far:
- an independent verifier, shown sources the kernel picks (see [Verification](#verification));
- a shared situation that the kernel acts on and keeps current: decision points with its own forecasts, abort criteria you set, a main effort, and sub-agents that can hand a part back (see [The shared situation](#the-shared-situation));
- a lead that knows its members: a card for each position it can staff, with the record the kernel keeps of each, shown with `--cards` (see [The members](#the-members)).

Designed, not built:
- a reviewer that checks the plan against the purpose before the work starts;
- a method made of moves the kernel runs, so that a chain of dependent parts is not split;
- teams that nest under the same gates, and trade updates with their peers without merging contexts;
- a lead that can be replaced from the record.

The design is in [docs/TEAM_DESIGN.md](docs/TEAM_DESIGN.md), which also records what became of Genet's first design. [ARCHITECTURE.md](ARCHITECTURE.md) maps the code.

## What it refuses

- Org-chart roleplay as architecture
- Workers that spawn workers
- `could we` as the first question
- Staying on a dead plan because the team looks aligned
- Unbounded loops

## Who decides what

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/control-dark.svg">
  <img alt="Models only return JSON. Every change to the team, the tools or the budget is decided by code in the control plane and logged; there is no direct path from a model to the roster." src="docs/img/control-light.svg" width="100%">
</picture>

*Models propose; code disposes. Nothing a model writes reaches the roster, the tools or the budget without passing a check in code, and every decision lands in the audit log.*

Models only fill a fixed JSON artifact: `claim`, `evidence`, `uncertainty`, `channel_id`, `context_update`, `requests`. Any other key is rejected. The lead proposes sub-agents as `requests` entries like `subtask:<channel>@<skill>=<named_failure>`. It cannot write the roster.

A run has four steps:

1. **Read and propose.** The lead reads the context and proposes sub-tasks, or none.
2. **Judge.** The gates decide. Two or more legal sub-tasks run as parallel sub-agents, each blind to the others, and the lead merges their results. A sub-agent that fails hands its part back to the lead. Otherwise a single agent does the work, switching to whatever skill the job needs.
3. **Verify.** If the product fails and the budget tier allows, the lead requests a replan, changes the method and reworks once.
4. **Answer from the record.** The operator's question is answered from the gate record, and the run closes. A closed run is read-only. If anything failed, the kernel's review is the last entry on the record.

## Shared ownership

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/ownership-dark.svg">
  <img alt="One sub-agent's reply is malformed. Its part goes back to the lead, who merges the other results, covers the part and hands the product to the verifier. After any failure the kernel writes a blameless review, and its lessons reach every brief in the next run." src="docs/img/ownership-light.svg" width="100%">
</picture>

*A failed part is not lost, and a failure is not wasted. Authority violations, budget halts and crashes still stop the run at once.*

The lead makes every decision; the outcome is the team's. When something goes wrong, the run does not single out an agent and stop. The team absorbs what it can, and records what happened so the next run starts better.

- **A failed part goes back to the team.** When a sub-agent's reply is malformed (`SCHEMA`) or its call to the model fails (`LIVE`), the run goes on. The other sub-agents' results are merged, and the lead covers the failed part the same way it covers a part the gates refused. An authority violation, such as a tool the skill does not allow or a roster change, still stops the run at once, as do a budget halt and a crash.
- **A blameless review after every failure.** When anything failed, even if the team recovered, the kernel writes a review on the run: what failed, what became of each part, and what the team did about it. It is built from the record, never from model text, and it names no agent as the cause.
- **Lessons for the next run.** Each kind of failure maps to one fixed lesson, which goes into `guidelines/lessons.md` in the store. Every agent's brief carries the guidelines, so the next run starts with what the last one learned. Repeats are counted, at most 10 lessons are kept, and `--no-lessons` turns it off. Comparison trials each use a fresh store, so no lesson carries from one strategy to another. Lessons cost tokens, and whether they pay is not measured: on the simulated reader, a store with 10 lessons adds 31% to a small run.

Decisions stay with one owner because shared authority is no authority: the roster, the gates and the budget answer to the lead and the kernel alone. What is shared is responsibility for the result.

## Gates

Every proposed sub-task goes through three gates in order, and they fail closed: **can someone else → should we → could we.** In industry terms this is admission control for sub-agents. Each proposal gets a full gate record, legal or not.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/gates-dark.svg">
  <img alt="Five proposed sub-tasks pass three gates in order: two are refused because the work is already covered, one because it names no failure and goes back to the lead, and two clear all three gates to run as parallel sub-agents." src="docs/img/gates-light.svg" width="100%">
</picture>

*Refused work is either already covered or goes back to the lead; it is never silently dropped.*

| Gate | Refuses a sub-task when |
|---|---|
| Can someone else | A file or channel in the world already covers it, the channel is already staffed, it repeats another proposal, or it is verification (the verifier's job). A single open sub-task is the lead's job, not a new agent's. |
| Should we | It names no failure: what goes wrong if a single agent does it. Then, for the team: there is no measurable reason a single agent would fail. A fan-out needs one of two reasons: the operator declared that the sub-tasks must stay isolated (`--isolate`), or their material does not fit in one call. The room in one call is the per-call limit less what the lead's own planning call cost, brief and reply. A part must also fit a sub-agent's own call: its brief, what reading adds to its files, and the room its reply needs. A plan with a part too big gets one more try, told what the gates measured, when a split could still be paid for. Files the goal names that no part names go to the lead to cover. Material is estimated from the sizes of the workspace files each sub-task covers: a file named for its channel, and any it names in its note. When the workspace does not fit one call, the plan brief tells the lead to name a group's files that way, and when the files the goal names do not fit, what they come to. A name counts however a model spelled it (`cobalt ridge.md`, `cobaltridge.md`, `q3 report.md`), and a part that names no file the workspace holds goes to the lead while the rest of the plan stands. A file several sub-tasks need counts once, and a split that leaves one sub-agent carrying all of the material is not a reason. If the material can't be measured, it doesn't count as a reason. |
| Could we | Its skill is unknown, or its channel id is unusable or reserved. The budget tier does not allow a fan-out. The call budget cannot pay for the sub-agents plus merge and verify. The cap of 4 workers is full. |

A fan-out needs at least two legal sub-tasks.

The could-we gate counts calls, not tokens. A split can pass it under a token budget too small to finish, and that run stops with `BUDGET` once the budget is spent. `--abort forecast_short` stops it sooner: over a sweep of token budgets on the simulated reader, it cut the tokens spent on runs that could not finish by 69 to 85% when the budget was far too small, and lost no run that could finish. A token check in the gate did worse: its estimate refused splits that would have finished, so fewer runs completed. So the gate stays as it is.

That second check makes the gate measurable rather than rhetorical. The lead can no longer split work just by giving a reason. `--split-policy stated` restores the old behavior, where the lead's named reasons are enough; it is kept for comparison. Fan-outs the operator names with the `fanout` command count as declared.

When the plan no longer fits, request a replan and change the method. `KEEP_ROSTER` is illegal on a replan request; use `CHANGE_METHOD` or `REVISE_GOAL`.

## Skills and tools

Every slot carries one active skill. The lead can switch its own. A sub-agent is created with the skill its sub-task names, which makes it a specialist. Each skill has its own brief and tool allowlist, and can have its own model.

| Skill | Tools | Brief |
|---|---|---|
| `execute` | — | Do the assigned piece of work. |
| `retrieve` | `retrieve`, `read` | Find source material; cite paths and lines. |
| `observe` | `observe`, `read` | Survey what exists. |
| `reason` | — | Work the problem through. |
| `draft` | — | Write the product. |
| `simulate` | — | Run the plan forward; report where it breaks. |
| `verify` | — | Judge the product: PASS or FAIL. |

The tools only read: `read:<path>`, `retrieve:<query>` and `observe[:<dir>]`. They reach only the `--workspace` directories and the `--read` files. Hidden files (anything whose name or folder starts with a dot, such as `.env` or `.git/`), binaries, and symlinks that lead outside the workspace or into a hidden file are refused. A file you attach with `--read` is readable even if hidden, because you named it. The allowlist is checked before any tool runs, and each tool round is a budgeted call (at most 2 rounds per sub-agent).

## Budget tiers

| Tier | Flag | Allowed | Cap |
|---|---|---|---|
| Tight | `--tier tight` | single agent | 4 calls / 4k tokens / 30s |
| Normal | `--tier normal` | + replan | 8 / 15k / 60s |
| Open | `--tier open` | + gated fan-out | 12 / 50k / 120s |

The tiers began as a way to test in steps, with guardrails, so that no run could start and fail to stop. The CLI defaults to tight. Do not raise the budget because the model sounded ready. A run may spend its whole budget, but not one call more.

## Install

Genet needs Python 3.11 or newer. On a Mac whose `python3` is 3.9, the steps below stop with an error about `setup.py` that does not name the cause; use `python3.12 -m venv .venv` there.

```bash
git clone https://github.com/jrodriguez4505/Genet.git
cd Genet
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Commands

```bash
# The lead staffs the task.
python -m taskorg.cli run --context "One paragraph holds everything needed."

# Two notes. If they fit one context, the gates keep a single agent and say why.
# --isolate declares they must not share a context, so the gates allow a fan-out.
python -m taskorg.cli run --tier open --workspace notes/ \
  --context "subtask:note-a@retrieve=sources_must_not_mix subtask:note-b@retrieve=sources_must_not_mix"
python -m taskorg.cli run --tier open --workspace notes/ --isolate \
  --context "subtask:note-a@retrieve=sources_must_not_mix subtask:note-b@retrieve=sources_must_not_mix"

# Fixed paths: the operator picks the shape.
python -m taskorg.cli single --tier tight
python -m taskorg.cli replan --tier normal
python -m taskorg.cli fanout --tier open --context "subtask:source-a=independent_a subtask:source-b=independent_b"

# Read a saved run.
python -m taskorg.cli diagnose data/runs/run-001.json
python -m taskorg.cli board data/runs/run-001.json
python -m taskorg.cli bench
```

Every run command takes these flags:

- `--goal`, `--purpose`, `--done-when` and `--context`: what the run is for, and what is known.
- `--read FILE`: file text goes into working memory.
- `--workspace DIR`: specialists may read and search here.
- `--exists FILE`: the file's name covers a channel.
- `--criteria TEXT`: the product must show this.
- `--isolate`: the sub-tasks must not share a context, which is a declared reason to fan out.
- `--split-policy measured|stated`: what "should we" accepts (default `measured`).
- `--tier`, plus budget overrides: `--max-calls`, `--max-tokens`, `--max-seconds`, `--max-tokens-per-call`.
- `--abort CRITERION`: `forecast_short` (the default), `parts_failed:N`, or `none`. Naming one replaces the default (see [The shared situation](#the-shared-situation)).
- `--main-effort CHANNEL`: the part the goal depends on most; the gates judge it first.
- `--report-up`: a sub-agent may hand its part back when the plan is wrong for it.
- `--cards`: the lead's plan brief carries a card for each position it can staff (see [The members](#the-members)).

Each run starts with clean working memory, even when you reuse a run id. Runs saved before the 0.2 rename still load.

`bench` scores every fixture in `fixtures/bench/` against its `expect` block.

## Proving it

`compare` runs the same tasks three ways. Model, tools, budget, tool rounds, verify-and-replan step and concurrency are all the same; only how the task is staffed differs. A part that gets no sub-agent, for the worker cap or a malformed id, goes back to the lead under every strategy.

| Strategy | Staffing |
|---|---|
| `single` | One agent works the task. No planning call. |
| `always` | Crew style: the lead always decomposes, and every sub-task gets a worker, up to the cap. |
| `genet` | The lead proposes sub-agents and the gates judge them, with the measured "should we". |
| `genet-stated` | Same, but the lead's stated reasons are enough. Add it with `--strategies single,always,genet,genet-stated`. |
| `genet-cards` | Same as `genet`, with the members table in the lead's plan brief (`--cards`). |
| `always-told` | Same as `always`, with the size notes `genet`'s lead gets. No gates. |

The tasks come from a seeded, synthetic corpus of company operating notes, so ground truth is exact and no model has seen it. Facts are written in varied prose and surrounded by distractors: prior-year figures and look-alike company names.

A product is graded on its last `ANSWER:` marker, in capitals; an "answer:" in prose does not count. A number must be the line's one value: period labels such as Q3 or FY2026 are ignored, `a + b = c` answers `c`, and a range or a list is not an answer.

| Family | Question | Stresses |
|---|---|---|
| `lookup` | One figure for one company | One source holds everything needed |
| `aggregate` | Sum of a figure over 3 companies | Independent parts |
| `compare` | Which of a look-alike pair had higher churn | Interference |
| `breadth` | Which of 5 companies had the highest revenue | Many sources |

The claim under test: genet matches the better baseline's accuracy at close to single-agent cost. The report shows accuracy, tokens, calls, latency, split rate and aborts, overall and per family, plus cost when you give prices.

Three options test the concept itself, each off by default so the default suite never changes: `--entities N` asks aggregate and breadth questions over N companies, from a pool of 38 with 12 look-alike pairs; `--distractors N` adds N wrong-year figures to each company's notes, phrased like the real ones; and `--filed N` gives N of each question's companies already filed and checked, in the task's context, and marks them covered, so a sub-agent for one of them would repeat finished work. `scripts/concept_runs.sh` runs both arms on Claude with one key entry, a cap and a tape per run.

`verify-bench` measures the verifier on its own. Real runs give too few wrong products to count catches, so it builds them:
- four products for each aggregate question, the way a lead's product reads;
- one right, one right with other evidence, one with a company's figure taken from its look-alike's file, and one with the FY2025 figure;
- each with the record its author would have left.

The arithmetic always adds up, so it never gives an error away. Each product is reviewed under five setups:
- `today`;
- `shared-full` and `shared-layered`;
- `independent-full` and `independent-layered`.

`--arms` puts an argument in front of the verifier, with the same planted errors: `note`, where the author's note argues for the planted figure (wrong products only, since the independent view drops the note), and `planted`, where every file the goal names ends with an instruction to the verifier, to pass a wrong product or fail a right one. The kernel opens those files for the verifier, so the instruction reaches it. On the simulated reader neither arm changes a verdict. On Haiku 5.5 (2 November, [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md)), they split apart. The planted instruction was never followed in 24 reviews, which is the model's judgement, on one wording, and no limit in code. The false note is what got through:

`--arms split` reviews products shaped like a lead's merge, with group subtotals and no file cited. Of each wrong kind, one has its error in a file the layered pick shows and one in a file it does not. The extra setups `independent-told`, `independent-headed` and `independent-both` tell the verifier its sources are a sample, that a line with no year takes the year in its file's heading, or both. They are left out of a plain run, and off everywhere else.

| Verifier | Sources | Plain | Against the false note |
|---|---|---|---|
| shared | layered | 9 of 12 | 8 of 12 |
| shared | full | 12 of 12 | **7 of 12**, look-alike errors 1 of 6 |
| independent (default) | layered (default) | 10 of 12 | 10 of 12 |
| independent | full | 12 of 12 | 12 of 12 |

In the shared layered row the look-alike errors were still caught, but only because the file the note cites was not opened. That is why the independent view became the default in v0.9.0. It leaves out the sub-agents' reports as well, and on split runs that did not fail more right answers: 6 of 26 runs against 3 of 5.

The report shows wrong products caught (by kind), how many of those FAILs name the planted company, right products failed, how often the company's own file was among the sources, and tokens a review. `scripts/verify_runs.sh` runs it on Claude Haiku 5.5, capped and taped. On the simulated reader, a perfect checker of what it is shown, `full` catches every planted error, `layered` every look-alike one, and `today` none. On Haiku 5.5, `today` caught 2 of 12, `full` 12 of 12 in either view, and `layered` 9 of 12 for the right reason in either view. No setup failed a right product.

```bash
python -m taskorg.cli verify-bench                          # simulated reader, 120 reviews, $0
python -m taskorg.cli compare --dry-run                     # the plan and call ceiling; calls no model
python -m taskorg.cli compare --adapter sim                 # deterministic reader: structural cost at $0
python -m taskorg.cli compare --adapter live --per-family 2 # pilot: 24 trials
python -m taskorg.cli compare --adapter live --price-in 2 --price-out 10   # full: 60 trials, with cost
```

The `sim` adapter is a deterministic reader, not a language model. It solves every task under every strategy, which shows the harness gives each strategy the facts it needs. Its token counts show what each strategy costs by structure alone. With a perfect reader, splitting rarely pays: a single agent is cheapest in every family of the default suite. Splitting can only earn its accuracy if a real model reads worse with everything in one context; the concept experiments measured that on Claude Haiku 5.5, below.

What the simulated reader shows. These are structural results from a perfect reader, not model results:

| Per-call context | Single agent | Always-split crew | Genet |
|---|---|---|---|
| Roomy, `--context 16000` | 100% · 2,842 tokens/task | 100% · 4,998 | 100% · 3,417 (1.20× single) |
| Tight, `--context 1500` | **55%**: runs abort on context overflow | 100% · 4,998 | 100% · 4,683 (0.94× crew) |

The counts include the files the verifier is given, the default since v0.7.0. With `--verify-sources none` they are as before: 2,030, 4,186 and 2,605 (1.28×) roomy, and 4,186 and 3,871 (0.92×) tight.

When the work fits one context, Genet stays a single agent and pays only for its planning call. When it doesn't fit, a single agent fails, and Genet fans out exactly where the material requires it. Per family at `--context 1500`, Genet stays a single agent on lookup and compare, where a single agent scores 100%, and fans out on aggregate and breadth, where it scores 20% and 0%. At 20 companies a question, the simulated single agent costs 1.5 times the crew: it re-sends everything it has read every round.

The stub adapter drives the harness end to end but cannot answer, so its accuracy is 0 by design. Results are saved to `data/compare/` as JSON.

### What the live runs show

Every live run since v0.1 is on Claude, recorded in [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md). The tapes and results are published, [through 29 October](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029), [for 2 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261102) and [for 3 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261103), so a reader can rerun the live figures as well as the simulated ones.

- **One agent was enough, and was the most accurate.** On the default questions, with every fix, single, crew and Genet each got every answer on Haiku 5.5, and Sonnet 5.5 did too at eleven times the cost. Asked about 5, 10 and 20 companies at once, about 84,000 tokens a task at the largest, a single agent still got every answer. On this model and these tasks there was no loss for a split to recover, so splitting for quality is not shown.
- **Headcount cost accuracy.** The always-split crew went from 8 of 8 to 5 of 8 and 5 of 7 as the questions grew, losing answers in hand-offs and merges. It cost 1.8 to 2.5 times a single agent on small questions; past about 10 companies it cost less, but about the same per right answer.
- **Genet stayed one agent wherever the work fit,** at 1.2 to 1.6 times a single agent's tokens: its planning call, which on a real model costs about as much as a working call. With half of each question's companies already filed, it was the cheapest strategy of all. Haiku's crew lead left filed work out of its plan by itself, so Genet's first gate had nothing to refuse.
- **A verifier catches what it is shown.** Without sources, Haiku's verifier passed 10 of 12 planted errors, catching only the two whose own evidence quoted the wrong year. Given every file, it caught all 12 and failed none of 12 right products, at about six times a review's tokens. The layered pick caught every look-alike error at 1.6 times. Against a mild author's note, leaving it out made no measurable difference; against a false one, it decided the result (below).
- **Judging fit before the work is unreliable.** At a tight cap, the lead told the limit still judged work too big for one call to fit, and the gates' estimate from file sizes ran short, because searches pull in look-alike files.
- **A split can work, once the gates can measure it.** At an 8,000-token cap over 10 files, Haiku's lead proposed groups of files, the sensible plan with a cap of 4 sub-agents. The gates measure a part by the files it names, and the plan brief did not ask for that, so they refused every split and all 8 runs overflowed. Told how to name them, 8 of 16 leads split; the other 8 misjudged the sum and overflowed. Told also what the question's files come to, a fact the kernel measures, all 8 proposed, 7 split, and 6 were verified. These are Genet's first live splits on work that does not fit one call.
- **Side by side at that cap, the gates earned their place on small work, and the notes on large work.** On 12 questions that fit one call, no lead proposed a split, and Genet matched the single agent's 12 of 12 at 1.14 times its tokens. A crew given the same size notes still split all 12 and got 9, at 1.79 times. On 18 that do not fit, that crew and Genet each verified 13, and the single agent none. A crew without the notes verified 4, so most of Genet's lead over it came from the notes, which any lead can be given. The told crew reached more right answers there, 18 against 15, because the gates refused two plans over a guessed file name, though it used about 17% more tokens. Over all 30, Genet verified 25 and the told crew 22. With the file names fixed, a rerun of Genet came to the same totals, 25 verified and 27 right: better at 10 companies, 12 of 12 right, and worse at 20, 3 of 6, where three runs stopped for reasons the fix did not touch. With those reasons fixed, a third run at 20 companies had no stop on size: all 6 leads split, 5 reached the right answer and 4 were verified. It is one run, and the leads' plans vary. At a 200,000-token cap a single agent gets these answers, so this does not show a split beating one agent where one agent fits.
- **Told why its plan was refused, a lead planned again, and it fit.** Handed first plans the gates refuse, Haiku's lead wrote 18 second plans, and the gates admitted all 18. 17 covered every file the question named. The other left out 5, among them the file with the right answer, and the gates admitted it, because they measure what a part names. The kernel now hands files like these to the lead to cover. No lead's own first plan in a run has needed a second yet.
- **A clean merge passes the verifier, and a real one often does not.** Given products shaped like a merge, Haiku's verifier failed none of 12 right ones and caught all 12 errors in a file it was shown, naming the company. It caught none of 12 errors in a file it was not shown, so a pass after a split checks only what was opened. On the real merges on the tapes it failed 34 of 104 right answers and caught 18 of 19 wrong ones. Two added sentences, that its sources are a sample and that a line with no year takes its file's heading, took those failures to 3, with the same 18 caught and no wrong answer passed. Those merges suggested one of the sentences, so this needs new questions, and the rule is off until then.
- **A sub-agent rarely guesses.** Given the wrong file, Haiku said the figure was missing on 10 of 12 parts, and with `--report-up` handed those same 10 back and no right part. The other 2 took the look-alike's figure under both briefs.
- **A planted instruction did not move the verifier. The author's false note did.** With every source open, a note arguing for the error got 5 of 6 look-alike errors past it, in the setup that caught all 6 without the note. The independent view, which leaves the note out, caught them all, and is now the default. See [Verification](#verification).

On this evidence, Genet's value is governance and cost: it stays one agent when one is enough, which here was always, and keeps the decision to split in code. Accuracy gains from splitting are not shown. The live runs found 24 problems the simulated reader could not show, among them sub-agents that read their siblings' files, a verifier shown a stale product, a harness example that primed a look-alike mix-up, and a verifier that passed a wrong total because it could not open a source. Twenty-one are fixed: the verifier now gets the riskiest sources by default, and on Haiku 5.5 it caught every planted error whose file it was shown. Three are open: judging fit before the work starts, which telling the lead the total improved; a verifier that fails right answers after a split, which two sentences stopped on the recorded merges but which new questions have not tested; and a lead whose merge reply is malformed twice, which stops the run though both replies held the right answer.

## Live model (optional)

Any OpenAI-compatible chat endpoint. This is independence from the transport, not yet from the model: only v0.1 ran on another provider, and the token ratio the size check uses is set on the Claude adapter, so a different model through this one is estimated at four characters a token until it is measured.

```bash
export TASKORG_MODEL_BASE=https://api.x.ai/v1
export TASKORG_MODEL_KEY=...
export TASKORG_MODEL_NAME=...                 # required
export TASKORG_MODEL_NAME_REASON=...          # optional: a model per skill
python -m taskorg.cli run --adapter live --tier normal --context "..."
```

The base URL must be `https://`, or `http://` to this machine (a local model server). Plain `http://` to any other host would send the key in clear text, so it is refused unless you set `TASKORG_MODEL_ALLOW_HTTP=1`, for example for a server on your own network. Redirects are never followed, so the key reaches only the host you named.

Every request asks the endpoint to stop the reply at what is left of the per-call cap, in the `max_tokens` field, so a reply that runs on is never billed past it. Set `TASKORG_MODEL_MAX_TOKENS_PARAM=max_completion_tokens` for an API that names the field that way, or `none` to send no cap. When an endpoint reports no token usage, the adapter estimates it from the exact request it sent and the raw reply it got, and marks the call `tokens_estimated`.

### Claude, through the Messages API

```bash
pip install -e '.[anthropic]'                 # the official SDK; Genet itself needs nothing
export TASKORG_ANTHROPIC_KEY=...
export TASKORG_MODEL_NAME=claude-haiku-5-5
export TASKORG_MODEL_EFFORT=low               # optional: low, medium, high, xhigh or max
python -m taskorg.cli compare --adapter anthropic --per-family 1 --price-in 0.10 --price-out 0.50 --max-spend 0.50
```

Same prompts, the same JSON gate and the same token accounting as the live adapter; only the transport differs. The key is read from `TASKORG_ANTHROPIC_KEY` and nowhere else, so a key exported for another tool is never spent by accident, and an endpoint set for the live adapter never receives it. Requests carry no temperature, which current Claude models reject, and the reply cap is what is left of the per-call cap. Thinking tokens are billed as output: they count in each call's completion tokens, and the tape records them on their own. A refused request fails as `LIVE`, so its part goes to the lead. The SDK retries overloads and rate limits itself, and follows no redirect. `bash scripts/live_pilot.sh` runs the pilot with a smoke test first, a cap per model and a tape.

For several runs in a sitting, `bash scripts/live_session.sh` takes the key once and keeps it in that window's memory, not in a file. A run asked for there shows its estimate and caps, and starts only when you type `y`.

### Spend cap and tapes

`--max-spend` stops a comparison before a trial that could take spending past the cap, judged by the costliest trial so far. Ctrl-C also stops it. Either way the trials already run are saved.

The tapes of the Claude runs, with the results each produced and a replay command for each, are published as GitHub releases: [27 to 29 October 2026](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029), [2 November 2026](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261102) and [3 November 2026](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261103). A clean clone replays the 28 and 29 October tapes to the token with no key and no SDK, and most runs replay exactly. Sub-agents run in parallel, though, so a run may not if it stops during them: how many calls had finished depends on timing. Before v0.9.1 the same could happen within a few tokens of the cap, and one finished trial stopped in 1 of 3 replays, 9 tokens over; the 27 October tapes were recorded under prompts that later changed, and stay as the record.

`--record PATH` saves every exchange with the model as it happens: the request, the reply text and its usage, or the error. Never the key, never the base URL. `--replay PATH` answers from that tape instead of a model, with no key and no spend, so the kernel, the gates and the grading can be refined against real replies. A request the tape does not have, because a prompt or brief changed since the recording, fails as `LIVE` and is counted. A tape recorded before v0.7.0 replays with `--verify-sources none`, the verifier's brief at the time, and one recorded before the independent view became the default replays with `--verify-view shared`. Tool results name files relative to the workspace, so the same request reads the same on every run, and no temp folder or home directory reaches the model.

## Security

Genet treats three things as untrusted input: what the model endpoint sends back, what the model asks for, and what is in the workspace. A planted instruction in a workspace file is assumed to reach the model, so the limits are enforced in code, not in the prompt:

| Limit | Value | What it stops |
|---|---|---|
| Response size from the endpoint | 8 MB | A reply that exhausts memory |
| Time for the whole exchange: connect, headers, body | the timeout | A server that sends a byte at a time to hold a run open |
| Brief size plus room for the reply, checked before sending, counting the system prompt and wrapping | the per-call token cap | A request that is sent, paid for, and then overruns |
| Tools run per reply | 8, repeats once | One reply that triggers thousands of reads |
| Sub-tasks the gates judge per plan | 16 | A proposal flood |
| Text one search scans | 20M characters | A search that reads an entire disk |
| Terms one search matches | 16 | A query that makes one search take hours |
| Entries one walk looks at | 20,000 | A huge or hostile directory tree |
| Reported token counts | whole numbers, not negative | A reply that hides its own spend |
| Calls in flight | counted against the budget | Parallel sub-agents that each spend past the cap |
| Reply length, asked of the endpoint | what is left of the per-call cap | A reply that runs on and is billed |
| Spend per comparison | `--max-spend` | A run that drains the account |
| Where the Claude key comes from | `TASKORG_ANTHROPIC_KEY` only | A key exported for another tool, spent by accident |

A malformed reply is asked again once, with a note saying what was wrong; models slip on the format now and then, and a retry is cheaper than losing the run or the part. Only a malformed reply is retried, never an authority violation, and the retry is a budgeted call like any other. The room kept for a reply is the largest reply in the run so far, and 200 tokens for a live model before it has replied; the gates count the same room when they decide what fits. A call that fails after it was sent, for example on malformed JSON, stays on the record marked `failed`: it counts toward the budget and toward every cost the comparison reports. Saved runs, working memory and results are written atomically, so a crash mid-save leaves the previous file, never a truncated one. An answered review note is a record and cannot be answered again; a deferred one can.

When one sub-agent fails, or you press Ctrl-C, the run closes at once and the sub-agents still running start no further calls. Any other failure inside a run, not only a rule the kernel enforces, leaves it aborted with a reason, and the CLI saves it as `CRASH`. A request string from a model, such as a path with a NUL byte or a symlink loop, comes back as "not found" instead of stopping the run.

Malformed JSON from the endpoint or the model, including nesting too deep and numbers too long to convert, stops the call as a `LIVE` or `SCHEMA` error. A malformed saved run is refused as `PERSIST`, and a saved run cannot give a slot tools its skill does not allow. See [SECURITY.md](SECURITY.md) to report a vulnerability.

## The shared situation

Every member works from the same situation: the goal, its purpose, done-when, the criteria and the method. The kernel acts on each part of it (design part 8):

- **Decision points.** After the plan is judged, after the sub-agents report, and after the verdict, the kernel forecasts what the rest of the run needs and records it. The forecast counts the fewest calls left to make, at the run's average cost per call so far, against what the budget has left.
- **Abort criteria**, from a fixed list, set with `--abort`:
  - `forecast_short` stops the run when the forecast shows the budget cannot finish the work, before it spends the rest;
  - `parts_failed:N` stops it when N parts' sub-agents have failed.

  Free text is refused, because code cannot test it. A run that stops this way ends with code `ABORT`, and its review names the criterion.

  `forecast_short` is on by default since v0.9.0; `--abort none` turns every criterion off, and naming a criterion replaces the default. It judges the run's whole budget, never the size of one call, and the forecast is a floor, so it stops only a run that cannot finish. On the 372 taped Claude trials, whose budgets were roomy, it would never have fired; on the simulated reader with a budget below the run's cost, it cut the tokens spent on runs that could not finish by 69 to 85% and lost no run that could finish.
- **Main effort.** `--main-effort CHANNEL` names the part the goal depends on most. The gates judge it first, so it is staffed first when the budget or the cap runs short.
- **Kept current.** Each call a member makes carries the situation as it stands at that call, tool rounds included, and says what changed since its last one. Its context stays as it stood at the split.
- **Reported up.** With `--report-up`, a sub-agent may answer `replan:REASON` when the plan is wrong for its part. Its reply is not merged. The kernel opens a replan request, closes it with a method in which the lead covers the part, and gives the lead the reason.

None of these change a request, the default criterion included.

`merge-bench` reviews the real merges on the tapes again, under today's source rule and three others, one product at a time, so the rules compare product by product. Only the verifier's call goes to the model.

`plan-bench` measures a second plan on its own. A plan is refused for a part too big on only some runs, so the bench hands the run a first plan the gates refuse, in one of three shapes, and only the lead's second planning call goes to the model. It counts the plans the gates admit and those that cover every file the question names.

```bash
python -m taskorg.cli plan-bench                            # simulated reader, 18 plans, $0
```

`report-bench` measures reporting up on its own. A plan that is wrong for one part is too rare in real runs to count, so the bench builds the parts of 20-company aggregate questions the way a lead hands them out. Each part names a company. In half of them the plan gave the part's channel the wrong file: the company's look-alike's notes, which name it only for an FY2025 figure, or an unrelated company's. The sub-agent's tools open only that file. Each part runs with the default brief (`today`) and with `--report-up`, and only the sub-agents' calls go to the model. The report shows wrong parts handed back, said to be missing, or given a figure from the wrong file, and right parts reported or handed back. On the simulated reader, a perfect sub-agent, `--report-up` hands back every wrong part and no right one. On Haiku 5.5 (2 November, [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md)), `--report-up` handed back 10 of 12 wrong parts and no right one, at 6% more tokens. Under the default brief, the same 10 said in prose that the figure was missing, and in both setups the other 2 gave the look-alike's figure. So reporting up changes where a problem goes, not how many are noticed. Whether the lead then covers the part well is not measured.

```bash
python -m taskorg.cli report-bench                          # simulated reader, 48 parts, $0
```

## The members

The lead staffs positions, not agents: a position is a skill and the model that fills it (design part 7). With `--cards`, the lead's plan brief carries a table with one row for each skill. Each row gives:
- the skill's tools, and whether they open files;
- the most calls one part may take;
- the model that would fill it;
- what one of its calls has cost, measured over past runs;
- its counts from past runs: parts given, done, verified, failed (by code), handed back, and covered by the lead.

The kernel writes the table from its own tables and from `records/positions.json` in the store, beside the lessons. It updates that file at the end of every run that staffed a sub-agent, from the run's record, never from model text, and whether or not the cards are shown. A position's counts show only after 3 runs, so one bad run does not steer the lead. The table has a fixed size. It shows counts, not scores. The gates never read it.

The cards are off by default. They change the plan brief, and they stay off until a test shows they pay for their tokens. The `genet-cards` strategy compares the same runs with and without them, and `compare` reports the parts each strategy's lead proposed, the parts the gates refused, and the parts the lead had to cover. Each comparison trial uses a fresh store, so there the cards carry no past counts. On the simulated reader, whose lead ignores them, they add about 250 tokens to each plan call, 6 to 7% of a small task; on Claude, about 460. Over two live comparisons of 8 trials each (2 November), they show no sign of helping: once leads could name a group's files, 2 of 4 split with the cards and 3 of 4 without.

## Verification

The verifier's verdict is the first word of its claim: PASS passes, and anything else fails, so "Passing this would be wrong" is not a pass. A live verifier is told to pass a product only if it answers the goal, its subject and its question, and to fail one about something else even when it repeats the criteria: a past live run passed an answer about Jean Genet the playwright on a task about this kernel. Then every success criterion must appear in the product itself, as a whole word or number ("4.1" is not met by "14.1"): its claim, evidence or context update. The verifier's own evidence does not count, so it cannot pass a product by echoing the criteria. These run-state checks must also hold:

- The context and the method are not empty.
- Sub-agents merged their results.
- No review is open.

Name the criteria with `--criteria`. The defaults, "default task" and "purpose", are met by any reply that echoes its brief, so a run verified only against them carries the warning `verified_against_default_criteria` in `diagnose` and in the CLI's output. The comparison does not depend on this: it grades every answer against known ground truth.

The verifier always gets its call. When a split is judged, the gates reserve the merge, including the tool rounds it needs to cover a part no sub-agent took, and the verify call. A single agent's work and a rework stop their tool rounds in time to leave that call.

### What the verifier checks against

The verifier sees:
- the product;
- up to 12 of its evidence lines;
- the context as the operator gave it, and with `--verify-view shared`, every member's notes and reports;
- the workspace files the kernel opens for it, by default the riskiest few.

It has no tools of its own. On 28 October, before the kernel opened files for it, that let a wrong total through: the verifier could not open a source, and it read the author's own note that look-alike files were excluded. Two settings decide what it sees. Run commands, `compare` and `verify-bench` all take them:

| Flag | Values | What it does |
|---|---|---|
| `--verify-view` | `independent` (default), `shared` | `independent` leaves out the author's notes. The verifier gets the context as the operator gave it, the goal, the criteria, and the product with its evidence, and none of working memory's product or sub-agent reports. `shared` shows it every member's notes and reports: the default until v0.9.0, and how a false note got past it. |
| `--verify-sources` | `layered` (default), `full`, `none` | The kernel opens workspace files and puts them in the verifier's brief. See below. `none` opens nothing. |

What each mode opens:
- **`full`:** every file the goal names, the product cites or its uncertainty names, or the run read.
- **`layered`:** first, any file the goal names that no call in the run read or searched. The product has something for that subject, so it came from somewhere else. Then the files the product's uncertainty names. Then two at random from what the goal names or the product cites.

The kernel picks the files from the run's record and the product's text. The author does not pick them, and neither does the verifier. Files go in up to the per-call limit, and the brief says how many did not fit. The record holds every pick and why, so the same product opens the same files and a tape replays.

With sources on, the kernel also checks, in code, that every evidence quote is in a file its evidence line cites, and tells the verifier which are not. A file named inside the quote does not count as cited. Quotes of the tool's own words, of a search query, or of a member's report are not checked. Over all 885 products on the Claude tapes, it flags 6, and each is a quote the cited files do not hold. The verdict stays the verifier's, and the criteria checks above still apply.

`layered` became the default after its live run (29 October, [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md)). It caught every look-alike error at about 3% more tokens on a 20-company task, where `full` caught every planted error at about a quarter more. A run with no workspace has nothing to open, so its verifier's request is unchanged. `--verify-sources none --verify-view shared` sends the verifier's request as it was before v0.7.0, which tapes recorded before then need to replay.

## Diagnose

`diagnose` reports health, the budget used and remaining, and every gate verdict and tool call. It shows what became of each part under `team`, and the run's review when anything failed. It also reports isolation: whether any sub-agent's brief carried another sub-agent's result. That is checked at call time over the whole brief, and the verdict survives save and load.

These count as fails:

- A tight-tier run that grew the roster.
- A normal-tier run that answers a replan request with `KEEP_ROSTER`.
- Any run with `isolation_leak`.
- Any aborted run, and any run whose stop rule failed.

Runs saved before isolation was recorded show `isolation_unverified`.

The log is a record, not proof against tampering. A saved run is checked for its shape, not for edits: a run whose gate records were rewritten after the fact still loads and reports healthy.

## Tests

`pytest -q` runs about 1,800 checks with no network and no key:

- **Kernel rules and regressions.** Each rule, and each bug fixed so far, has a test that fails if it comes back.
- **Red team.** Hostile model output must be refused, contained or halted: authority keys, spawn requests, path escapes, instructions planted in workspace documents, channel spoofing, proposal floods, oversized output.
- **Fuzzing.** 300 random sequences of 40 calls from random actors. The roster rules hold after every call.
- **Concurrency.** Parallel sub-agents never lose, double-count or cross results, and a tight budget is never overspent.
- **Live adapter.** Driven against a fake OpenAI-compatible endpoint: prompts, usage accounting, HTTP errors, timeouts.
- **Security.** One test per attack on the trust boundaries: redirects that would carry the key, plain-HTTP endpoints, oversized and slow responses, malformed JSON, fake token counts, oversized briefs, tool floods, hidden files and symlinks to them, huge trees, and tampered saved runs.
- **Review findings.** `tests/test_hardening.py` has one test per finding from a review of concurrency, input handling, persistence, the CLI and decision logic: siblings that kept spending after a failure, parallel overspend, unpaid merges, verdicts read by substring, crew parts dropped silently, grading by first number, hostile request strings, dripped headers, typed run files, and more.
- **Shared ownership.** `tests/test_ownership.py`: a failed part goes back to the lead and the run goes on; authority violations, budget halts and crashes still stop it; every failure is reviewed; lessons reach the next run, never carry model text, are counted and bounded, and can be turned off; and a review never changes a run's outcome.
- **Bounds.** `tests/test_bounds.py` runs 400 seeded runs against a hostile stand-in model that floods tools and proposals, sends malformed replies, fails calls, breaks authority rules and reports random, missing or invalid token counts. Every run must end without leaving a thread, stay within `max_calls`, record every call it made exactly once, record tokens as reported or as marked estimates, stay under `max_tokens` plus one call's cap, and report the same totals in the run, `diagnose` and a saved copy. It also checks that a reply cut at the cap ends after one retry and that a model always asking for tools runs out of rounds.
- **Claude, tapes and spend.** `tests/test_anthropic_tape.py`: no temperature, the reply cap, usage with thinking tokens, refusals and SDK errors as `LIVE`, the key from one variable only, no redirects (with the real SDK against a local endpoint when it is installed), a comparison replayed from its tape with the same results, misses counted, damaged tapes refused, the spend cap, and workspace paths that name no local folder.
- **Concept suite.** `tests/test_concept_suite.py`: the default suite's fingerprint, the new options, and a perfect reader that gets every scaled task right under every strategy.
- **Live findings.** `tests/test_live_findings.py`, one test per problem the live runs found: `claim` named as the product, the verifier given the reworked product and only that, the harness asking for what grading accepts and saying which months make each quarter, and a size estimate that does not undercount Claude's tokens, proposals read whole rather than split on spaces, plan prompts that show a real proposal, and a verifier that reads the evidence given with the product.
- **Live readiness.** `tests/test_readiness.py`, for gaps found in the past live data: room for the reply, one retry for a malformed reply (over HTTP too), the warning for default criteria, and a verifier that checks the goal.
- **Independent verifier.** `tests/test_verify_checks.py`, covering three areas:
  - what the verifier sees: the default brief is as it was, and the independent view leaves out the author's notes;
  - which files the kernel opens and why: the longest name first, and the same picks for the same product, trimmed to the per-call limit;
  - the quote check, the record of what the tools showed, and the verify bench: arithmetic that never gives an error away, and the simulated reader as each setup's ceiling.
- **Verifier arms and the default abort.** `tests/test_verify_arms.py`: the note arm changes only a wrong product's note, the planted arm plants in every goal file and nowhere else, the simulated reader is a ceiling under both, `--abort none` turns the default off, and a run that cannot finish stops at its plan.
- **Threat map.** `tests/test_threat_map.py` marks every field a model fills, across a plain split, a rework, hostile channel names, a part handed back, a malformed part and the cards. Model text must not reach the guidelines, the lessons, the position records or any brief in a later run. [SECURITY.md](SECURITY.md) has the map.
- **Harness validity.** The deterministic reader gets every task right under every strategy.
- **Compatibility.** Runs saved in older formats still load.

`python scripts/mutation_check.py` checks the tests themselves. It breaks one rule at a time, across 340 hand-picked mutations of the gates, roster, budget, verifier, isolation, sandbox, model-output, security, run-state and shared-situation checks, and confirms that some test fails for each. All 340 are caught. The regular suite also checks that every mutation still matches the code, so a refactor cannot quietly retire one.

## Terms

| Term | Meaning | In code |
|---|---|---|
| Lead | The orchestrator. The only agent that proposes changes to the team. | `lead` slot, `RunState.lead_id` |
| Roster | Who is on the team (agent topology). | `RunState.slots`, `Run.set_roster()` |
| Sub-agent | A worker with an isolated context and one channel. | `worker` slot with a `channel_id` |
| Sub-task | A part of the work with a stated reason to run separately. | `Subtask`, `subtask:<channel>@<skill>=<failure>` |
| Gates | Admission control for sub-agents. | `gates.assess()`, `GateRecord` |
| Split policy | What counts as a reason to fan out: measured (default) or stated. | `Engine(split_policy=...)`, `--split-policy` |
| Skill | A role brief plus a tool allowlist. | `Slot.skill`, `SKILLS`, `Run.switch_skill()` |
| Goal | What the run must deliver, with success criteria and a done-when condition. | `goal`, `success_criteria`, `done_when` |
| Method | The current plan. Its moves are recorded as labels; design part 9 would have the kernel run them. | `RunState.method`, `axes` |
| Context | The shared state of what is known. | `RunState.context`, `Run.update_context()` |
| Review | A concern raised to the lead, which must answer it. | `Run.open_review()`, `Run.answer_review()` |
| Decision point | A place in the loop where the kernel forecasts the rest of the run and checks the abort criteria: plan, reports, verdict. | `RunState.checkpoints`, `Engine._decision_point()` |
| Forecast | The kernel's estimate of what the rest of the run needs, against what is left. | `situation.forecast()`, `RunState.projections` |
| Abort criterion | A condition, from a fixed list, that stops the run at a decision point. | `RunState.abort_criteria`, `--abort` |
| Main effort | The part the goal depends on most; the gates judge it first. | `RunState.primary`, `--main-effort` |
| Position | A skill and the model that fills it. Records are kept by position, not by agent. | `members.Record` |
| Card | A position's row in the lead's plan brief: tools, calls a part, model, cost of a call, and counts from past runs. | `members.cards()`, `--cards` |
| Replan request | A review that says the plan no longer fits; only a method or goal change closes it. A failed check opens one, and with `--report-up` so can a sub-agent. | `Run.request_replan()`, INV-14 |
| Run log | The trace and audit log of every decision. | `Run.log`, `diagnose()` |
| Team review | The kernel's blameless review of a run that had a failure: what failed, each part's outcome, what the team did. | `Run.review`, `review.team_review()` |
| Lessons | Fixed sentences, one per kind of failure, that every later brief carries. | `guidelines/lessons.md`, `MemoryStore.add_lesson()`, `--no-lessons` |
| Streams | Typed message channels: merge, escalate, report, peer. | `STREAMS`, `Delta.stream` |
| Budget tier | Tight, normal or open. | `Budget.for_tier()` |

This Genet is software, not the playwright.

## Status

v0.9.3 kernel. Invariants and the bench are covered by tests. The comparison and the concept experiments have run on Claude Haiku 5.5, with a check on Sonnet 5.5; what they show is under [What the live runs show](#what-the-live-runs-show). Not a cloud platform.

The policy head (`policy.py`, `imitate.py`, `rl.py`, `finetune.py`) is an experiment and is not wired into runs. [ARCHITECTURE.md](ARCHITECTURE.md) maps the modules and lists the open design questions. See [COMPLETED.md](COMPLETED.md) for what is and is not claimed.

## Use, partnerships, commercial

Use it. Fork it. Ship a product on top of it.

That is the point of an Apache-2.0 kernel. You do not need permission to run Genet or to build with it.

If you want any of the following, open a GitHub issue with the label `partnership` (or email the address on the GitHub profile):

- embed Genet in a paid product and want a support or OEM conversation
- co-develop a harness, adapter, or evaluation set
- write about the design and want a review for accuracy
- hire the author for integration work

Sales of *your* product that uses Genet are yours. Sales of *this* kernel as a hosted service, or use of the name Genet as your product name, need a conversation first. See `NOTICE`.

Do not file an issue to ask whether you may use the code. You may. File an issue when you want a person on the other end.

## License

Apache License 2.0. Copyright 2026 John Rodriguez.

You may use, modify, and distribute, including in commercial products. You keep your own copyright on your changes. You must keep the license and notice. The license does **not** grant trademark rights to the name Genet.

This is not legal advice. If you need a different deal (exclusive, support SLA, assignment), that is a contract, not a license dropdown.
