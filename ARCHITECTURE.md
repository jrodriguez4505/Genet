# Architecture

This page is for someone reviewing Genet's design. It covers how a run moves through the code, what each module does, the decisions behind them, and the questions still open. Other documents cover the rest:
- the [README](README.md): use;
- [docs/TEAM_DESIGN.md](docs/TEAM_DESIGN.md): where the team goes next;
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
2. **Plan** (`Engine._propose` in `loop.py`). The lead's call carries:
   - the context;
   - the guidelines and lessons from the store;
   - a SIZE note on what one call holds;
   - the plan brief.

   The lead replies with proposals in `requests`, as `subtask:<channel>@<skill>=<named_failure>`. `subtasks.py` reads them, and at most 16 are considered.
3. **Judge** (`assess` in `gates.py`, called from `Engine._assess`). Each proposal passes three gates in order, and each gate fails closed:
   - **Can someone else:** refused if already covered, already staffed, a repeat, or verification.
   - **Should we:** needs a named failure plus a measured reason. The reason is either declared isolation, or material that does not fit in one call. `Toolbox.material` measures the material from file sizes.
   - **Could we:** needs a known skill and a usable channel, a tier that allows a split, a budget for the sub-agents plus merge and verify, and room under the cap of 4.

   Every proposal gets a `GateRecord`, legal or not.
4. **Staff and work** (`Engine._staff`, `_run_workers`, `_act`).
   - With two or more legal sub-tasks:
     - `Run.set_roster` adds one sub-agent per gate record (INV-1, INV-8).
     - Sub-agents run in parallel. Each gets a brief scoped to its own channel (`MemoryStore.scoped_brief`, INV-6) and a toolbox open only at its files (`Toolbox.scoped`).
     - Tool requests are checked against the skill's allowlist and run read-only (`tools.py`), at most 2 rounds each.
     - The lead merges. It covers the parts the should-we or could-we gate refused, any proposed past the cap of 16, and any whose sub-agent failed (`_cover`).
   - With fewer than two, the lead works alone and switches to the skill the work needs (`Run.switch_skill`, INV-11).
5. **Verify** (`Engine._verify`, `_verifier_brief`, `checks.py`).
   - The kernel picks sources from the run's record (`checks.pick`; layered by default) and opens them into the verifier's brief.
   - It checks evidence quotes in code (`checks.misquoted`).
   - The verdict is the first word of the verifier's claim, and every criterion must appear in the product.
   - On a FAIL, if the tier and budget allow, the lead requests a replan (INV-14) and reworks once.
6. **Close** (`Engine._account`, `_close`, `review.py`, `persist.py`).
   - The operator's question is answered from the gate record, and the kernel raises its cues (`cues.py`).
   - If anything failed, the kernel writes a blameless review and adds a fixed lesson to the store.
   - The run is saved and becomes read-only.

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
| | `verify_bench.py` | The verifier on its own: planted errors under five setups. |
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
| One agent by default. Each added agent is a cost. | Others measured large token multiples for multi-agent gains, and losses on sequential work (sources in the design's related work). On Claude Haiku 5.5, a single agent got every answer up to 20 companies a question. |
| A reason to split is measured, not stated. | A lead can always give a reason. `--split-policy stated` keeps the old rule for comparison, and on Haiku it was the weakest strategy. |
| Models fill a fixed artifact, and authority stays in code. | No prompt can change the team. Red-team tests and the mutation check hold this. |
| One owner, a shared outcome. | A failed part goes back to the lead, and the run goes on. The review and the lessons come from the record, never from model text. |
| Hard budgets. | A run may spend its whole budget, but not one call more. Merge and verify are reserved before a split. |
| Read-only tools in a sandbox. | Workspace only. Hidden files, binaries and symlinks out of the workspace are refused. |
| The kernel picks the verifier's sources. | Neither the author nor the verifier chooses them. In the live bench, the sources decided the catch. |
| Every figure can be rerun. | A deterministic reader and tapes let every result replay with no key and no spend. |

## How it is tested

- 1,490 tests, with no network and no key: rules, red team, fuzzing, concurrency, security, bounds and live findings.
- `scripts/mutation_check.py` breaks 206 rules one at a time, and a test catches each.
- The runs on Claude are taped, so each can be replayed.

## Open questions for a reviewer

1. **Is admission control the right place for the staffing decision?** The alternatives are learning the staffing offline, as BAMAS does, or leaving it to the lead's judgment. Genet decides each proposal at runtime, in code.
2. **Should the should-we gate count cost?** It counts two reasons: declared isolation, and material that does not fit. At 20 companies a single agent costs 1.5 times the crew in the sim, because re-sent tool results grow each round. Genet still stays single.
3. **Fit judged before the work is unreliable on a real model.** Is re-planning on a measured overflow (design part 4) the answer, or a better estimate in the gate?
4. **Nesting** (design part 3): the same gates at every level, depth 2, and at most 4 direct reports a lead, with a budget reserved from the parent's. Are 4 and 2 the right limits?
5. **The lead knowing its members** (design part 7): a record of each position, kept by the kernel, in the lead's plan brief. Does a track record belong in the brief, in the gates, or nowhere?
6. **`loop.py` is 944 lines.** The `Engine` holds briefs, calls, staffing, merge and verify. Where would you split it?
7. **Hand-offs lose information.** The always-split crew lost answers as the work grew. What would show where?

## Not built yet

These are the remaining parts of [docs/TEAM_DESIGN.md](docs/TEAM_DESIGN.md):
- nesting (part 3);
- succession, with re-planning on a measured overflow (part 4);
- members that differ by model (part 6), waiting on a go-ahead for spend;
- a lead that knows its members (part 7).

The README's "workers that spawn workers" refusal stays until nesting is built.
