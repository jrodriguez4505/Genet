# Architecture

This page is for someone reviewing Genet's design. It covers how a run moves through the code, what each module does, the decisions behind them, and the questions still open. Other documents cover the rest:
- the [README](README.md): use;
- [docs/TEAM_DESIGN.md](docs/TEAM_DESIGN.md): where the team goes next, and what became of Genet's first design;
- [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md): what the runs on Claude showed.

## Why it exists

Agent counts have become a headline number: products advertise hundreds of sub-agents on one task. A count says what was spent, not what was gained.

Genet starts from the other end. A task gets one agent by default, and a second only when code can show it does work the first could not. The claim is the best baseline's accuracy at close to a single agent's cost.

## The team it is built for

- The team is small, and the lead knows what each member can do.
- Members differ where it matters: in what they see, what they may open, and which model fills them.
- Everyone works from the same goal, purpose and done-when.
- Responsibility is shared. Decisions and the outcome are the lead's.
- Each member must do work the others could not.

Every agent is the same model and could hold any skill. So a member is a position, not a kind of agent: any agent can fill any position. Authority belongs to the position, and the kernel checks it. [docs/TEAM_DESIGN.md](docs/TEAM_DESIGN.md) works this out. So far, only its independent verifier is built.

## Two planes

Models only fill a fixed JSON artifact: `claim`, `evidence`, `uncertainty`, `channel_id`, `context_update`, `requests`. Any other key is refused.

Code decides everything else: who is on the team, which tools run, and what is spent. Each decision goes on the run's log. To the kernel, a model's reply is untrusted input.

## How a run moves through the code

`taskorg run --tier open --workspace DIR "goal"`, in outline:

1. **Set up** (`cli.py`, `factory.py`, `budget.py`). The CLI builds two objects:
   - a `Run`: state, log and rules;
   - an `Engine`: the loop, with a budget tier, a model adapter, a sandboxed `Toolbox` and a `MemoryStore`.

   The run state holds the shared situation (design part 8): the decision points the kernel checks at, its forecasts, and the operator's abort criteria and main effort. `axes` records the method's moves as labels until design part 9.
2. **Plan** (`Engine._propose` in `loop.py`). The lead's call carries:
   - the context;
   - the guidelines and lessons from the store;
   - a SIZE note on what one call holds, and, when they do not fit, what the files the goal names come to and how to name a group of files;
   - the plan brief;
   - with `--cards`, a table with a card for each position the lead can staff (design part 7, `members.py`): tools, calls a part, model, the cost of a call, and counts from past runs.

   The lead replies with proposals in `requests`, as `subtask:<channel>@<skill>=<named_failure>`. `subtasks.py` reads them, and at most 16 are considered.
3. **Judge** (`assess` in `gates.py`, called from `Engine._assess`). The main effort, if the operator named one, is judged first. Each proposal passes three gates in order, and each gate fails closed:
   - **Can someone else:** refused if already covered, already staffed, a repeat, or verification.
   - **Should we:** needs a named failure plus a measured reason. The reason is either declared isolation, or material that does not fit in one call. `Toolbox.material` measures the material from file sizes. A part must fit a sub-agent's own call: `Engine._part_overhead` counts its brief, what reading adds to its files, and the room its reply needs.
   - **Could we:** needs a known skill and a usable channel, a tier that allows a split, a budget for the sub-agents plus merge and verify, and room under the cap of 4.

   Every proposal gets a `GateRecord`, legal or not. A plan refused because a part is too big gets one more planning call, told what was measured (`Engine._second_plan`), when a split could still be paid for. The first plan stays on the record and leaves the shared context. Files the goal names that no part names go to the lead in the merge (`Engine._left_out`).
4. **Staff and work** (`Engine._staff`, `_run_workers`, `_act`).
   - With two or more legal sub-tasks:
     - `Run.set_roster` adds one sub-agent per gate record (INV-1, INV-8).
     - Sub-agents run in parallel. Each gets a brief scoped to its own channel (`MemoryStore.scoped_brief`, INV-6) and a toolbox open only at its files (`Toolbox.scoped`).
     - Tool requests are checked against the skill's allowlist and run read-only (`tools.py`), at most 2 rounds each.
     - With `--report-up`, a sub-agent may hand its part back (`replan:REASON`). The kernel opens a replan request and closes it with a method in which the lead covers the part (`Engine._reports`).
     - The lead merges. It covers the parts the should-we or could-we gate refused, any proposed past the cap of 16, and any whose sub-agent failed or handed it back (`_cover`).
   - With fewer than two, the lead works alone and switches to the skill the work needs (`Run.switch_skill`, INV-11).
5. **Verify** (`Engine._verify`, `_verifier_brief`, `checks.py`).
   - The kernel picks sources from the run's record (`checks.pick`; layered by default) and opens them into the verifier's brief.
   - It checks evidence quotes in code (`checks.misquoted`).
   - The verdict is the first word of the verifier's claim, and every criterion must appear in the product.
   - On a FAIL, if the tier and budget allow, the lead requests a replan (INV-14) and reworks once, told what the verifier said.
6. **Close** (`Engine._account`, `_close`, `review.py`, `persist.py`).
   - The operator's question is answered from the gate record, and the kernel raises its cues (`cues.py`).
   - If anything failed, the kernel writes a blameless review and adds a fixed lesson to the store.
   - If the run staffed sub-agents, the kernel adds each position's counts to `records/positions.json` in the store (`Engine._keep_records`, `members.from_run`). A damaged file never changes the outcome.
   - The run is saved and becomes read-only.

At three decision points (after the judge, after the reports, after the verdict), `Engine._decision_point` forecasts what the rest of the run needs (`situation.forecast`), checks the abort criteria (`forecast_short` by default; `--abort none` turns it off), and records both. A criterion that is met stops the run there, with code `ABORT`. Each call a member makes, tool rounds included, carries the situation as it stands at that call (`Engine._current`).

Every model call goes through `Engine._call`:
- `_admit` checks the budget before the call, counting calls in flight.
- `Run.assert_within_budget` checks it after.
- A malformed reply is asked again once. If it fails again, the part fails as `SCHEMA`.

## Modules

| Area | Module | What it does |
|---|---|---|
| Kernel rules | `run.py` | The run: state, log, and the rules every change must pass (roster, reviews, replans, streams, completion). |
| | `gates.py` | The three gates and the gate record. |
| | `models.py` | Data types (slot, artifact, gate record, run state), the skills and their tools, `MAX_WORKERS`. |
| | `schema.py` | Checks the artifact and run state against `schemas/`. |
| | `budget.py` | Tiers and caps: calls, tokens, seconds. |
| | `subtasks.py` | Reads the lead's proposals and the sub-tasks an operator names. |
| | `situation.py` | Decision points, the kernel's forecasts and the abort criteria (design part 8). |
| | `members.py` | Each position's record from past runs, and the cards in the lead's plan brief (design part 7). |
| | `cues.py` | Notes the kernel raises for the lead at close, such as a merge review when two channels reported. |
| | `errors.py`, `factory.py` | The rule error; building a new run. |
| The loop | `loop.py` | The `Engine`: briefs, budgeted calls, tool rounds, what the gates measure, staffing, merge, verify, close. The comparison's strategies subclass it. |
| | `skills.py` | Each skill's brief. |
| | `tools.py` | The read-only sandbox: `read`, `retrieve`, `observe`, scoped for each sub-agent. |
| | `checks.py` | What the verifier is shown: the sources the kernel picks, and the quote check. |
| | `memory_store.py`, `reads.py` | Working memory for each run, plus guidelines and lessons; files the operator attaches. |
| | `review.py` | The blameless review and its lessons. |
| Models | `adapters.py` | The adapter interface and a stub. |
| | `live.py` | An OpenAI-compatible HTTP adapter, with no SDK. |
| | `anthropic_live.py` | Claude through the Messages API, using the SDK (an optional install). |
| | `sim.py` | A deterministic reader for the synthetic suite, for tests and the sim figures. |
| | `tape.py` | Records every live exchange and replays it with no key and no spend. |
| Measurement | `compare.py` | A single agent, an always-split crew and Genet side by side, graded against ground truth. |
| | `suite.py` | The seeded synthetic task suite. |
| | `verify_bench.py` | The verifier on its own: planted errors under eight setups. |
| | `report_bench.py` | A sub-agent on its own: parts with a planted plan error, with `--report-up` and without. |
| | `plan_bench.py` | A lead's second plan on its own: first plans the gates refuse, and the lead's next. |
| | `merge_bench.py` | The verifier on the tapes' real merges, under each rule. |
| | `rework_bench.py` | A lead's rework on its own: the tapes' reworks asked again, with and without what the verifier said. |
| | `bench.py`, `diagnostics.py` | Fixtures scored on the run's graph; health and audit of a run. |
| Operator | `cli.py`, `persist.py`, `atomic.py` | Commands; saving and loading runs, older formats included; writes that land whole. |
| Experiment, not used in runs | `policy.py`, `imitate.py`, `rl.py`, `finetune.py` | A socket for a learned policy head that could propose in place of the lead, and experiments to train one. It has no path to the roster. |

## Rules in code

`run.py` raises `InvariantError` when a change breaks one of these. The numbers follow the code, and INV-7 is not used.

| Rule | What it holds |
|---|---|
| INV-1 | Only the lead, or a logged human override, changes the roster. |
| INV-2 | Sub-agents have no way to add sub-agents. |
| INV-3 | Only the lead answers a review. |
| INV-4 | A deferral needs a reason, and a run cannot complete with a review open. |
| INV-5 | Nothing passes or completes with a failed stop rule. |
| INV-6, INV-12 | A sub-agent's brief carries the guidelines and its own channel, never a sibling's packet or unscoped history. |
| INV-8 | A split needs a named failure, and one roster change adds one sub-agent with its gate record. |
| INV-9 | The gates are recorded in order. Could-we is never first. |
| INV-10 | Updating the context does not start a sub-agent, and an exploratory sub-agent is refused when the context is enough. |
| INV-11 | Switching skill changes the brief and the tools, not the agent. |
| INV-13 | Only the lead opens a stream, and only a known one. |
| INV-14 | A replan request closes only with a new method or goal, and the run cannot complete until it does. |

## Decisions, and why

| Decision | Why |
|---|---|
| One agent by default. Each added agent is a cost. | Others measured large token multiples for multi-agent gains, and losses on sequential work (sources in the design's related work). On Claude Haiku 5.5, at a 200,000-token cap, a single agent got every answer up to 20 companies a question. |
| A reason to split is measured, not stated. | A lead can always give a reason. `--split-policy stated` keeps the old rule for comparison, and on Haiku it was the weakest strategy. |
| Models fill a fixed artifact, and authority stays in code. | No prompt can change the team. Red-team tests and the mutation check hold this. |
| One owner, a shared outcome. | A failed part goes back to the lead, and the run goes on. The review and the lessons come from the record, never from model text. |
| Hard budgets. | A run may spend its whole budget, but not one call more. Merge and verify are reserved before a split. The tiers began as a way to test in steps, so that no run could start and fail to stop. |
| No memory system of Genet's own. | Today's store is plain files. When a part needs more, an off-the-shelf or model-provider memory goes behind `MemoryStore`, and the kernel still decides what is written. |
| Read-only tools in a sandbox. | Workspace only. Hidden files, binaries and symlinks out of the workspace are refused. |
| The verifier does not see the author's notes. | With every source open, a false note got 5 of 6 look-alike errors past a verifier that saw it, and none past one that did not. A planted instruction in a file moved it not at all, so a member's note is the stronger lever. |
| The kernel picks the verifier's sources. | Neither the author nor the verifier chooses them. In the live bench, the sources decided the catch. |
| Records are kept by position, and shown as counts after 3 runs. | Agents are copies of one model, so a record of an agent would describe nothing. A score would judge for the lead, and one bad run should not steer it. The gates do not read the record. |
| Every figure can be rerun. | A deterministic reader and tapes let every result replay with no key and no spend. On a clean clone with no key and no SDK, the 28 and 29 October tapes reproduce every trial and review to the token. The tapes are published as releases, [through 29 October](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029) [for 2 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261102) and [for 3 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261103), with a replay command for each. |
| `forecast_short` is on by default. | It judges the whole budget with a floor forecast, so it stops only a run that cannot finish. It never fired on 372 taped trials, and on the simulated reader it cut what a run that cannot finish spends by 69 to 85%. |

## How it is tested

- 2,000 tests, with no network and no key: rules, red team, fuzzing, concurrency, security, bounds and live findings.
- `scripts/mutation_check.py` breaks 423 rules one at a time, and a test catches each.
- The runs on Claude are taped, so each can be replayed.

## Open questions for a reviewer

1. **Is admission control the right place for the staffing decision?** The alternatives are learning the staffing offline, as BAMAS does, or leaving it to the lead's judgment. Genet decides each proposal at runtime, in code.
2. **Should the should-we gate count cost?** It counts two reasons: declared isolation, and material that does not fit. At 20 companies a single agent costs 1.5 times the crew in the sim, because re-sent tool results grow each round. Genet still stays single.
3. **Fit judged before the work is unreliable on a real model.** Is re-planning on a measured overflow (design part 4) the answer, or a better estimate in the gate? On the tapes, re-planning reaches more: of the 9 tight-cap failures left once sub-agents were scoped, a better estimate could reach 3, and in 5 the lead never proposed a split for the gate to judge (`docs/LIVE_TESTS.md`). At a 200,000-token cap nothing overflowed, so neither has been needed at a real context size. On 2 November, at an 8,000-token cap, a lead told how to name a group's files split on 8 of 16 trials, and told also what the goal's files come to, on 23 of 26, with no lead proposing a split on the 12 questions that fit. The gates admitted every part of every plan that named its files, and 30 of 31 split runs reached the right answer. A lead that still misjudges, or guesses a file's name, overflows, so re-planning is what would rescue it. A better estimate is not: a scoped sub-agent's largest call ran at most 1.29 times today's estimate, so the 1.7 factor measured on unscoped searches would refuse work that fits.
4. **Nesting** (design part 3): the same gates at every level, depth 2, and at most 4 direct reports a lead, with a budget reserved from the parent's. Are 4 and 2 the right limits?
5. **The lead knowing its members** (design part 7, built with `--cards`): a record of each position, kept by the kernel, in the lead's plan brief. Does a track record belong in the brief, in the gates, or nowhere? Two live tests show no sign the cards help, at about 460 tokens a plan call, though past counts have not been tried.
6. **`loop.py` is about 1,200 lines.** The `Engine` holds briefs, calls, staffing, merge and verify. Where would you split it?
7. **Hand-offs lose information.** The always-split crew lost answers as the work grew. What would show where?
8. **A reviewer of purpose** (design part 10) adds a call before the work, to check the plan against the purpose. Is that worth it, or is checking the product afterwards enough?
9. **Sequential work** (design part 9). The gate would refuse to split a chain of parts unless a link does not fit. Is a dependency the lead declares enough to find chains, or should the kernel find them?

10. **What should the verifier be shown of a split's work?** The independent view is the default, because with every source open a false note got 5 of 6 look-alike errors past the shared view and none past it. It also leaves out the sub-agents' reports, and under either view the layered pick opens 2 of the files after a split, so a pass checks little: in the built products, errors in a file not shown got through 12 times in 12.

11. **Should the gates count what a split leaves for the lead?** They admit up to 4 sub-agents and hand the rest to the lead. A lead that plans one part per file at 20 companies then cannot fit the other 16 in its merge call. Haiku grouped its files and got by, but nothing makes a lead do that.

12. **Should the room a sub-agent keeps be measured for each model?** A sub-agent's call now keeps 1,500 tokens for its reply, or its own largest so far, and no longer counts the lead's plan reply. The figure comes from Haiku 5.5, whose replies after reading had a 90th percentile of 1,352 to 1,609 at every cap. On the 3 November run 5 of 24 such replies passed 1,500, with the largest at 1,841, and none was cut off, because no call came near the cap. Sonnet 5.5's ran far lower, with a 90th percentile of 614, and nothing has measured another model.
13. **Does a second plan hold up in a run?** On a bench, Haiku's lead, handed first plans the gates refuse, wrote 18 second plans, and the gates admitted all 18. The bench stops at the plan, and no lead's own first plan in a run has needed a second yet.
14. **What should a malformed merge do?** A lead's merge reply was malformed twice, and the run stopped, though both replies held the right answer. One closed a list with `}` and the other wrote `\$`. On the tapes of 2 and 3 November 8 of 1,428 replies were not JSON as sent, and this stopped 2 of 284 trials. Accepting the common slips, or asking the API for structured output, would each change what a reply may be, so neither is built.
15. **Is a verifier that passes what it cannot check what you would want after a split?** Since v0.10.0 it is told that its files are a sample, and that a line with no year takes its file's heading. On real merges from five seeds no tape had used, that took right answers failed from 69 of 220 to 6, and wrong answers caught from 36 of 39 to 37, clearing a bar written before the run. A pass still checks only the files opened: an error in a file not shown got through under every rule. On files built so that a heading does not hold for every line, the sentence lost no catch: 24 of 24 wrong products against 23 of 24 without it, on one seed.
16. **What should keep a lead's own reads from overflowing its next call?** On those seeds at 20 companies, Genet stopped on size 7 times in 30, and the told crew 2. Each of Genet's stops came on the lead's own call, after a part the gates refused, a part a sub-agent failed or handed back, or with no sub-agent at all. Since v0.11.0 a round stops when what it returned would not fit the next call, and tells the lead how many requests did not run. Replayed on those tapes, all 9 stops of the crew and Genet now send a further call that fits. No live run yet shows whether those calls reach right answers.
17. **Should a run that finds no figure count as complete?** Five of 450 trials finished saying a figure was not in a file that holds it, each on a line right after a sentence about another year or company. The verifier caught some of these and passed others. No trial finished with a wrong figure. A missing answer is more honest than a wrong one, but the run still reports it as complete. Told why the verifier failed its product, leads put right 11 of 22 wrong products, and of the 11 still wrong 10 decline or leave out a company. `--author-rule headed` is built for that, and is off until a whole run measures it.

## Not built yet

These are the remaining parts of [docs/TEAM_DESIGN.md](docs/TEAM_DESIGN.md), in its order:
- a reviewer of purpose (part 10);
- a method made of moves the kernel runs (part 9);
- nesting (part 3), with peer teams (part 11);
- succession, with re-planning on a measured overflow (part 4);
- members that differ by model (part 6), waiting on a go-ahead for spend.

Later, if needed: a learned staffing model, trained on part 7's records.

The README's "workers that spawn workers" refusal stays until nesting is built.
