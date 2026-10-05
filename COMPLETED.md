# Genet — completed work

Apache-2.0. Public repo: https://github.com/jrodriguez4505/Genet · Website: https://jrodriguez4505.github.io/Genet/

## v0.3 — October 2026

- **Measured "should we".** A fan-out of the lead's proposals needs one of two reasons:
  - The operator declared isolation (`--isolate`).
  - The sub-tasks' material doesn't fit in one call, estimated from the sizes of the workspace files they cover. The room in one call is the per-call limit less what the lead's planning call cost, brief and reply. A file several sub-tasks need counts once, and a split that leaves one sub-agent carrying all of the material is refused.

  Material that can't be measured doesn't count as a reason. Every gate record names its basis: `declared`, `measured` or `stated`. `--split-policy stated` keeps the old behavior for comparison, and `compare` gains a `genet-stated` strategy.
- **What the simulated reader shows.** Genet matches the best accuracy in both regimes:
  - **Roomy context (16k):** Genet stays a single agent at 1.19× its cost; it was 2.5× before this change.
  - **Tight context (1.5k):** a single agent aborts on overflow, scoring 55%, and Genet fans out at 0.91× the cost of a crew. Per family, it splits only where a single agent fails (aggregate, breadth) and stays single where one succeeds (lookup, compare).
- **Mutation testing.** `scripts/mutation_check.py` breaks rules one at a time. The first pass, over 57 rules, found 4 that no test protected:
  - the gate record's own order check
  - the reviewer's skill ban
  - sub-agents working from the split-time context
  - the replan tier check

  Each now has a test. Five more mutations cover the material rules, for 62, all caught. A fast test in the regular suite fails when a mutation no longer matches the code, and the runner itself now fails on one instead of skipping it.
- **Split basis in diagnostics.** `diagnose` reports `split_basis` for the run, and each gate interaction keeps its basis.
- **A sim fix.** The deterministic reader read a file once per mention, so each sub-agent read its file three times. That inflated every sub-agent's cost in earlier sim results. The figures above are after the fix.

## v0.2 — October 2026

### Lead-driven staffing

- **The lead staffs the task.** `Engine.run_task` / `taskorg run`: the lead reads the context and proposes sub-agents as `subtask:<channel>@<skill>=<named_failure>`. The kernel judges every proposal; the lead never writes the roster.
- **Real gates.** `gates.assess` checks:
  - world coverage (exact file name or channel)
  - a staffed or repeated channel
  - verification already belonging to the verifier
  - a named failure
  - a known skill and a usable channel id
  - the budget tier
  - budget affordability, counting each sub-agent's tool rounds
  - the worker cap
  - a single open sub-task being the lead's job

  Every verdict is logged as a full gate record.
- **Specialists.** Each skill has a brief, a tool allowlist and an optional model (`TASKORG_MODEL_NAME_<SKILL>`). Sub-agents are created with the skill their sub-task names. A single agent switches to the skill the work needs.
- **Sandboxed tools.** `read`, `retrieve` and `observe` reach only the `--workspace` directories and the `--read` files, and they only read. The allowlist is checked before anything runs. Each round is a budgeted call; at most 2 rounds per sub-agent.
- **Sub-agents work at the same time.** Threads with locked run accounting and per-thread usage in the live adapter. Results are accepted in sub-task order, so the run log is deterministic.
- **Replan on a failed check.** If the verifier fails the product in the normal or open tier, the lead requests a replan, changes the method and reworks once.
- **Comparison harness.** `taskorg compare` runs a single agent vs an always-split crew vs genet on a seeded synthetic suite (lookup, aggregate, compare, breadth). Everything but how the task is staffed is held equal. It reports accuracy, tokens, calls, latency, split rate and cost. It is validated offline with an oracle model and a deterministic reader; **no live results yet**.
- **Sub-agents and the cap.** Sub-tasks refused for capacity, or because the proposal was malformed, no longer drop. The lead covers them while merging, using its search tools.
- **Deterministic reader (`--adapter sim`).** It solves every suite task under every strategy, which proves the harness gives each strategy the facts it needs, and it compares structural cost at $0. With a perfect reader, a single agent is cheapest in every family. Splitting can only pay where a real model reads worse in one context.
- **Sub-agent notes.** Each sub-agent gets the lead's note from its sub-task, not only its channel name. Before this, a crew's assignments never reached its workers.
- **New test suites.**
  - **Red team:** hostile model output must be refused, contained or halted.
  - **Invariant fuzzing:** 300 random sequences of 40 calls each.
  - **Concurrency stress.**
  - **Live adapter** against a fake OpenAI-compatible endpoint.
  - **Compatibility:** saved runs in older formats.
- **Found by the fuzzer, and fixed:**
  - An unknown slot raised a raw `KeyError`.
  - A completed or aborted run still accepted reviews, skill changes and updates. Closed runs are now read-only (`CLOSED`).
  - Reusing a note id silently overwrote an open replan request, which could then be answered with `KEEP_ROSTER`. Note ids are now single-use.
- **Diagrams.** `docs/diagrams/build.py` renders three explainer figures, in light and dark for the README and inline for the Pages site:
  - three ways to staff a task
  - the gate funnel
  - control plane vs model plane
- **Native bench.** `taskorg bench` scores every fixture's `expect` block and no longer needs pytest. Four lead-driven fixtures were added.

### Vocabulary

The code and docs now use common agent-industry terms throughout. This is a breaking change for anyone importing `taskorg`; saved runs in the old formats still load.

| Area | Changes |
|---|---|
| Core names | `Mission` is now `Run`. The shared state is `RunState`, the lead is `lead`, and a sub-task is `Subtask`. |
| Run state fields | `goal`, `context`, `done_when` |
| Skills | Each slot carries a `skill`, changed with `switch_skill`. |
| Reviews | `open_review`, `answer_review`, `request_replan` |
| Message streams | merge, escalate, report, peer |
| Budget tiers | tight, normal, open |
| CLI | `run`, `single`, `fanout`, `replan`, `--context`, `--tier` |

### Fixes from the review

- **Broken README commands.** The README's fan-out and replan commands failed with their own default axes. A run that died on an invariant was saved as `active`; it is now `abort`.
- **Sub-agent isolation leaked.** A sub-agent's brief carried the live context, which held another sub-agent's result. Sub-agents now get the context as it stood at the split. The isolation check covers the whole brief, and the verdict survives save and load; it used to read a field that saving drops.
- **The CLI loaded code from `~/src/ecphory/src` on every command.** That hook is removed.
- **A reused run id inherited the last run's working memory.** Each CLI run now starts clean, and run ids are checked before they become file names.
- **The verifier could pass an empty product by echoing the criteria.** Criteria must now show in the product.
- **"Already exists" used substring matching,** so channel `a` was blocked by any path containing an "a". It now matches exact names.
- **Roster changes:**
  - A refused change still logged a split.
  - A worker could be re-tasked to a new channel without gates.
  - Duplicate slot ids were accepted.
- **Gate checking order:** `GateRecord.assert_legal` checked "should we" before "can someone else".
- **A budget off-by-one:** a run that used exactly its call budget was aborted, and its last call discarded.
- **Tool violations were reported as `BUDGET`.**
- **Policy JSON:** a confidence of 0 became 0.5, and bad JSON escaped as a raw error.
- **Live adapter:**
  - An empty `TASKORG_MODEL_NAME` was sent as `""`.
  - Read timeouts and HTTP error bodies escaped as raw tracebacks.
  - The lead and verifier were told they were workers.
- **Tests that could not fail:** `or True` and similar assertions now actually assert.

## v0.1 — 1 September 2026

A small multi-agent runtime. A run starts as one lead. Skills sit latent, and the context turns a skill on. A second worker is legal only after three gates, in order: can someone else → should we → could we. Models fill a structured artifact. They do not rewrite the roster.

| Piece | Job |
|---|---|
| Run / run state | Shared state |
| Engine | Inspect → skill → gates → maybe a worker → verify → close |
| Gates + world | Covered work refuses a new agent |
| Budget tiers | Tight: no fan-out. Normal: replan only. Open: may fan out. |
| Live adapter | Chat completions → artifact JSON only |
| Verifier | Named criteria plus run-state checks |
| CLI | Single-agent, fan-out, replan, brief, board, diagnose, bench and policy commands |

### Policy sprints (experimental, not wired into runs)

- **N1:** a socket, an encoder, and `apply_decision`, which never grows the roster.
- **N2:** an imitation logistic head with gold accuracy 1.0 on the synthetic set. The set has 9 distinct states; training and "held-out" rows overlap; and the gold labels never include `PROPOSE_CHANNEL`. This shows the plumbing, not learning.
- **N3:** sparse RL with an illegal rate of 0 vs the stub. `apply_decision` cannot add workers and the head never proposes channels, so 0 holds by construction.
- **Fine-tune:** SFT JSONL plus a local head trained on the same synthetic corpus. No Grok weight job exists on the public xAI API.

### Live proof (operator key)

Model: `grok-4.20-non-reasoning`.

- **Tight tier:** stayed a single agent.
- **Normal tier:** changed the method, not the headcount.
- **Open tier:** fanned out to two isolated channels. Isolation was only checked on packets then; see v0.2.
- **"Exists" case:** skipped the file already on disk.
- **job-status-1e:** wrote a five-line status from an attached README, against two named criteria.

The v0.1 commands are in `docs/LIVE_TESTS.md`.

Live run logs stay local. They are not committed; `.gitignore` covers the run-output folders under `data/`.

## Not claimed

Not a product. Not a GAIA score. Not a fine-tuned Grok checkpoint. GAIA vs CrewAI stays closed until a shared harness exists (see `fixtures/bench/GAIA.md`).

## Size

Kernel: about 5,100 lines in `taskorg/`. Suite: about 620 checks (including 300 fuzz sequences), 9 bench fixtures, and 62 mutation checks.

## Run

```bash
pip install -e ".[dev]"
pytest -q
python -m taskorg.cli run --tier tight
python -m taskorg.cli bench
```

Live adapter: set `TASKORG_MODEL_BASE`, `TASKORG_MODEL_KEY` and `TASKORG_MODEL_NAME`, then pass `--adapter live`.
