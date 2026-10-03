# Genet

[Apache-2.0](LICENSE) · Python 3.11+ · kernel, not a cloud

One organism. Many stems.

**The question is not how many agents you can run. It is whether a second one is doing new work.**

Genet is a small multi-agent runtime. Most stacks treat headcount as capacity; Genet treats it as a cost. A task starts with one lead agent (the orchestrator). The lead may propose sub-agents, each with the specialty its sub-task needs, and policy gates in code decide whether any of them run. Default is one agent. Authority lives in the graph, not in the prompt.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/patterns-dark.svg">
  <img alt="Three ways to staff the same task: a single agent; an always-split crew that pays for a planner, workers and a merge every time; and Genet, where policy gates decide whether a fan-out happens at all." src="docs/img/patterns-light.svg" width="100%">
</picture>

*Same task, three ways to staff it. A crew fans out on every task. Genet's lead proposes, and the gates decide whether a fan-out happens at all.*

The design comes from a SEAL platoon: small, cross-trained, with specialists among them. The commander owns the task organization. Intent stays fixed while the method changes. The platoon splits into elements only when the situation has separate objectives, then regroups.

Quality of process over quantity of agents: possibly more efficient, and possibly more effective. That stays a claim until measured. `taskorg compare` exists to measure it (see [Proving it](#proving-it)).

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

Models only fill a fixed JSON artifact: `claim`, `evidence`, `uncertainty`, `channel_id`, `delta_to_picture`, `requests`. Any other key is rejected. The lead proposes sub-agents as `requests` entries like `seam:<channel>@<qual>=<named_failure>`. It cannot write the roster.

A mission runs in four steps:

1. **Look and propose.** The lead reads the situation and proposes sub-tasks, or none.
2. **Judge.** The gates decide. Two or more legal sub-tasks run as parallel sub-agents, each blind to the others, and the lead merges their results. Otherwise one agent does the work, switching to whatever specialty the job needs.
3. **Verify.** If the product fails and the pace allows, the lead reports the plan wrong, changes the method and reworks once.
4. **Answer from the record.** The operator's question is answered from the gate record, and the mission closes. A closed board is read-only.

## Gates

Every proposed sub-task goes through three gates in order, and they fail closed: **can someone else → should we → could we.** In industry terms this is admission control for sub-agents. Each proposal gets a full gate record on the board, legal or not.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/gates-dark.svg">
  <img alt="Five proposed sub-tasks pass three gates in order: two are refused because the work is already covered, one because it names no failure and goes back to the lead, and two clear all three gates to run as parallel sub-agents." src="docs/img/gates-light.svg" width="100%">
</picture>

*Refused work is either already covered or goes back to the lead; it is never silently dropped.*

| Gate | Refuses an element when |
|---|---|
| Can someone else | A file or channel in the world already covers it, the channel is already staffed, it repeats another proposal, or it is verification (the verifier's job). A single open part is the lead's job, not a new body. |
| Should we | It names no failure: what goes wrong if one body does it. |
| Could we | Its specialty is unknown, or its channel id is unusable or reserved. The pace does not allow a split. The budget cannot pay for the elements plus integrate and verify. The cap of 4 workers is full. |

A split needs at least two legal elements.

When the plan is wrong, report it and change the method. `KEEP_ROSTER` is illegal on that note; use `CHANGE_METHOD` or `REVISE_GOAL`.

## Specialists and tools

Every slot carries one active qualification. The lead can switch its own (cross-training). An element is created with the qualification its seam names (a specialist). Each qualification has its own role brief and tool allowlist, and can have its own model.

| Qualification | Tools | Role |
|---|---|---|
| `execute` | — | Do the assigned piece of work. |
| `retrieve` | `retrieve`, `read` | Find source material; cite paths and lines. |
| `observe` | `observe`, `read` | Survey what exists. |
| `reason` | — | Work the problem through. |
| `draft` | — | Write the product. |
| `simulate` | — | Run the plan forward; report where it breaks. |
| `verify` | — | Judge the product: PASS or FAIL. |

The tools only read: `read:<path>`, `retrieve:<query>` and `observe[:<dir>]`. They reach only the `--workspace` directories and the `--read` files. Hidden files, binaries and symlinks that lead outside are refused. The allowlist is checked before any tool runs, and each tool round is a budgeted call (at most 2 rounds per element).

## Pace

| Pace | Flag | Allowed | Cap |
|---|---|---|---|
| Crawl | `--pace crawl` | one body | 4 calls / 4k tokens / 30s |
| Walk | `--pace walk` | + change method | 8 / 15k / 60s |
| Run | `--pace run` | + gated elements | 12 / 50k / 120s |

The CLI defaults to crawl. Do not open the budget because the model sounded ready. A run may spend its whole budget, but not one call more.

## Install

```bash
git clone https://github.com/jrodriguez4505/Genet.git
cd Genet
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Commands

```bash
# The lead organizes the team.
python -m taskorg.cli mission --look "One paragraph is the whole picture."
python -m taskorg.cli mission --pace run --workspace notes/ \
  --look "seam:note-a@retrieve=sources_must_not_mix seam:note-b@retrieve=sources_must_not_mix"

# Drills: the operator picks the path.
python -m taskorg.cli run --pace crawl
python -m taskorg.cli adapt --pace walk
python -m taskorg.cli split --pace run --look "seam:source-a=independent_a seam:source-b=independent_b"

# Read the board.
python -m taskorg.cli diagnose data/missions/ms-001.json
python -m taskorg.cli board data/missions/ms-001.json
python -m taskorg.cli bench
```

Every mission command takes these flags:

- `--read FILE`: file text goes into working memory.
- `--workspace DIR`: specialists may read and search here.
- `--exists FILE`: the file's name covers a channel.
- `--criteria TEXT`: the product must show this.
- `--pace`, plus budget overrides: `--max-calls`, `--max-tokens`, `--max-seconds`, `--max-tokens-per-call`.

Each run starts with clean working memory, even when you reuse a mission id.

`bench` scores every fixture in `fixtures/bench/` against its `expect` block.

## Proving it

`compare` runs the same tasks three ways. Model, tools, budget, tool rounds, verify-and-adapt step and concurrency are all the same; only the task organization differs.

| Strategy | Organization |
|---|---|
| `single` | One agent works the task. No planning call. |
| `always` | Crew style: the lead always decomposes, and every subtask gets a worker. |
| `genet` | The lead proposes elements and the gates judge them. |

The tasks come from a seeded, synthetic corpus of company operating notes, so ground truth is exact and no model has seen it. Facts are written in varied prose and surrounded by distractors: prior-year figures and look-alike company names.

| Family | Question | Stresses |
|---|---|---|
| `lookup` | One figure for one company | One source is the whole picture |
| `aggregate` | Sum of a figure over 3 companies | Independent parts |
| `compare` | Which of a look-alike pair had higher churn | Interference |
| `breadth` | Which of 5 companies had the highest revenue | Many sources |

The claim under test: genet matches the better baseline's accuracy at close to single-agent cost. The report shows accuracy, tokens, calls, latency, split rate and aborts, overall and per family, plus cost when you give prices.

```bash
python -m taskorg.cli compare --dry-run                     # the plan and call ceiling; calls no model
python -m taskorg.cli compare --adapter sim                 # deterministic reader: structural cost at $0
python -m taskorg.cli compare --adapter live --per-family 2 # pilot: 24 trials
python -m taskorg.cli compare --adapter live --price-in 2 --price-out 10   # full: 60 trials, with cost
```

The `sim` adapter is a deterministic reader, not a language model. It solves every task under every strategy, which shows the harness gives each strategy the facts it needs. Its token counts show what each strategy costs by structure alone. With a perfect reader, splitting never pays: one agent is cheapest in every family. Splitting can only earn its cost if a real model reads worse with everything in one context. The live run is what measures that.

The stub adapter drives the harness end to end but cannot answer, so its accuracy is 0 by design. Results are saved to `data/compare/` as JSON. No live results are published yet.

## Live model (optional)

Any OpenAI-compatible chat endpoint:

```bash
export TASKORG_MODEL_BASE=https://api.x.ai/v1
export TASKORG_MODEL_KEY=...
export TASKORG_MODEL_NAME=...                 # required
export TASKORG_MODEL_NAME_REASON=...          # optional: a model per qualification
python -m taskorg.cli mission --adapter live --pace walk --look "..."
```

## Verification

The verifier's claim must start with PASS. Then every success criterion must appear in the product itself: its claim, evidence or delta. The verifier's own evidence does not count, so it cannot pass a product by echoing the criteria. The world checks must also hold: Where and How are not empty, elements posted their deltas, and no review note is open.

## Diagnose

`diagnose` reports health, the budget used and remaining, and every gate verdict and tool call. It also reports isolation: whether any element's brief carried a sibling's product. That is checked at call time over the whole brief, and the verdict survives save and load.

These count as fails:

- A crawl run that grew the roster.
- A walk run that answers a dead plan with `KEEP_ROSTER`.
- Any run with `isolation_leak`.

Boards saved before isolation was recorded show `isolation_unverified`.

## Tests

`pytest -q` runs about 500 checks with no network and no key:

- **Kernel rules and regressions.** Each rule, and each bug fixed so far, has a test that fails if it comes back.
- **Red team.** Hostile model output must be refused, contained or halted: authority keys, spawn requests, path escapes, instructions planted in workspace documents, channel spoofing, seam floods, oversized output.
- **Fuzzing.** 300 random sequences of 40 calls from random actors. The roster rules hold after every call.
- **Concurrency.** Parallel sub-agents never lose, double-count or cross results, and a tight budget is never overspent.
- **Live adapter.** Driven against a fake OpenAI-compatible endpoint: prompts, usage accounting, HTTP errors, timeouts.
- **Harness validity.** The deterministic reader gets every task right under every strategy.

## Glossary

The code keeps its original names. This maps them to the platoon and to common agent-industry terms:

| Platoon | Genet | Industry term | In code |
|---|---|---|---|
| Commander | Lead | Orchestrator | `head` slot, `who_head_id` |
| Task organization | Roster | Agent topology | Who: `picture.slots`, `write_who()` |
| Element / fire team | Element | Sub-agent | `worker` slot with a `channel_id` |
| Separate objective | Seam | Sub-task with a reason to isolate | `Seam`, `seam:<channel>@<qual>=<failure>` |
| Go / no-go criteria | Gates | Admission control, guardrail | `gates.assess()`, `GateRecord` |
| Qualification | Qualification | Role and tool profile | `skill`, `QUALS`, `slide()` |
| Commander's intent | Intent | Goal and success criteria | What and Why: `effect`, `purpose`, `end_state` |
| Scheme of maneuver | Method | Plan, strategy | How: `picture.method`, `axes` |
| Situation | Picture | Shared context, state | Where: `current_picture`, `update_context()` |
| Speaking up | Review note | Escalation, feedback | Why: `submit_why()`, `respond_why()` |
| "This plan is dead" | Plan-wrong report | Replan trigger | `report_plan_wrong()`, INV-14 |
| After-action record | Board | Trace, audit log | `Mission.log`, `diagnose()` |
| Comms nets | Nets | Message channels | `element`, `up`, `out`, `adjacent` |
| Crawl, walk, run | Pace | Budget tier | `Budget.for_pace()` |

This Genet is software, not the playwright.

## Status

v0.2 kernel. Invariants and the bench are covered by tests. The comparison harness exists; live results do not yet. Not a cloud platform.

The policy head (`policy.py`, `imitate.py`, `rl.py`, `finetune.py`) is an experiment and is not wired into missions. See [COMPLETED.md](COMPLETED.md) for what is and is not claimed.

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
