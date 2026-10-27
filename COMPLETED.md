# Genet — completed work

Apache-2.0. Public repo: https://github.com/jrodriguez4505/Genet · Website: https://jrodriguez4505.github.io/Genet/

## v0.5.0 — October 2026: Claude, a spend cap, and tapes

**Claude through the Messages API.** `--adapter anthropic` uses the official SDK, an optional extra (`pip install -e '.[anthropic]'`); Genet itself still needs nothing. The prompts, the JSON gate and the token accounting are the live adapter's. The OpenAI-compatible adapter could not reach Claude: it sends `temperature: 0`, which current Claude models reject with a 400. The key is read from `TASKORG_ANTHROPIC_KEY` only, so a key exported for another tool is never spent and the live adapter's endpoint never receives it. Redirects are not followed. `TASKORG_MODEL_EFFORT` sets how much the model thinks; thinking tokens count as output and are recorded on their own. A refusal fails as `LIVE`, with its tokens counted.

**A spend cap.** `compare --max-spend` stops before a trial that could take spending past the cap, judged by the costliest trial so far. Ctrl-C stops a comparison too. Either way the trials already run are saved, with `stopped_after` in the results.

**Tapes.** `compare --record` saves every exchange as it happens, and `compare --replay` reruns a comparison from the tape with no key and no spend. Rehearsed through the real SDK against a local endpoint with 5% overload faults: 188 exchanges recorded, and the replay reproduced all 32 trials exactly. A request the tape does not have fails as `LIVE` and is counted.

**Tool results name files relative to the workspace.** They showed the absolute path, so a comparison's temp folder reached the model, and every run's requests differed, which kept a tape from replaying. A name that would read a different file back stays absolute.

- `scripts/live_pilot.sh`: the pilot on Claude, with a smoke test, a cap per model and a tape.
- `tests/test_anthropic_tape.py`, and 14 new mutations, for 161, all caught.

## v0.4.3 — October 2026: calls end, and every token is counted

**Calls cannot loop.** An audit of every loop in the kernel found three that are open-ended, each with a hard stop. Reading a reply ends at the size cap or the exchange's deadline. Walking a workspace ends at 20,000 entries. Waiting to admit a call near the budget re-checks the budget and the clock every second, and calls in flight always finish or time out. Everything else that calls a model runs a fixed number of times: tool rounds are counted, a retry happens at most once, a rework at most once.

**Tested against a hostile model.** `tests/test_bounds.py` runs 400 seeded runs, and 5,000 more were run outside the suite. A stand-in model floods tools and proposals, sends malformed replies, fails calls, breaks authority rules, fails verdicts, and reports token counts that are random, missing or not numbers. Budgets, strategies, entry points and parallelism are all random. Every run ended without leaving a thread, stayed within `max_calls`, and recorded every call it made exactly once. Tokens were recorded as reported or as marked estimates, spend stayed under `max_tokens` plus one call's cap, and the totals matched in the run, `diagnose` and a saved copy.

**Two token gaps, closed:**
- **An unreported reply was counted by its claim alone.** When an endpoint reported no usage, the kernel estimated the reply from its `claim` field. A reply of about 2,000 tokens was counted as 3. The kernel now counts everything the model wrote. The live adapter estimates from the exact request it sent and the raw reply it got, malformed or not, and marks those calls `tokens_estimated`.
- **Nothing stopped a reply that ran on.** No request carried a reply limit, so a runaway reply would be billed before the kernel could see it. Every live request now asks the endpoint to stop the reply at what is left of the per-call cap (`max_tokens`; `TASKORG_MODEL_MAX_TOKENS_PARAM` renames the field or turns it off). A reply cut off there ends after one retry.

**Sim figures, recounted.** Counting whole replies raises the simulated reader's token counts a little. Genet's planning reply, with its proposed sub-tasks, now counts in full. With a roomy context Genet costs 2,372 tokens a task against 1,952 for a single agent (1.22×, was 1.19×). With a tight context it costs 3,291 against 3,623 for the crew (0.91×, unchanged). Accuracy is unchanged everywhere.

- 8 new mutations, for 147, all caught.

## v0.4.2 — October 2026: ready for a live run

Four gaps, found in the past live data and in a rehearsal of the live path against a stand-in endpoint on this machine:

- **Room for the reply.** The size check before a call counted the brief but not the reply. In the rehearsal, one call's prompt fit and its reply then overran the cap after it was paid for. The check now keeps room for the reply: the largest reply in the run so far, and 200 tokens for a live model before its first reply. That is the top of the 109 to 205 tokens per reply on record. The gates count the same room when they judge what fits, so they never keep work in a call the size check would refuse. Rehearsed at a 1,500-token cap, no call was paid for and then overran. The stub and sim figures are unchanged.
- **One retry for a malformed reply.** A reply that is not the artifact schema is asked again once, with a note saying what was wrong. The retry is a budgeted call, and the failed first one stays on the record. Authority violations, transport failures and budget halts are never retried. A recovered retry still gets a team review and leaves its lesson. Under injected faults on every call (5%, large context), Genet went from 87% to 100% and a single agent from 82% to 98%.
- **Default criteria are flagged.** Every past live run used default criteria ("default task" and "purpose", or the older default pair), which any reply that echoes its brief meets. A run verified only against them now carries `verified_against_default_criteria` in `diagnose` and a warning in the CLI's output. Health is not changed.
- **The verifier checks the goal.** A past live run passed an answer about Jean Genet the playwright on a task about this kernel. The live verifier is now told to pass a product only if it answers the goal, its subject and its question, and to fail one about something else even when it repeats the criteria. Whether a model follows that is for the live pilot to show.
- `tests/test_readiness.py`, and 9 new mutations, for 139, all caught.

## v0.4.1 — October 2026: findings from the past live data and longer tests

- **The oldest review answers are translated.** Real pre-0.2 runs answered reviews with `HOLD_ORG` and `CHANGE_HOW`, which the loader kept as they were, so `policy-replay` read a method change as a hold. They now load as `KEEP_ROSTER` and `CHANGE_METHOD`, in notes and in the log, whatever the file's format.
- **Failed parts are recorded in sub-task order.** A part whose sub-agent failed was logged from that sub-agent's thread, so the record's order depended on timing, and one test failed now and then. Failures are now recorded with the other results, in sub-task order, so the board stays deterministic.
- One new mutation, for 130.

## v0.4.0 — October 2026: shared ownership

The lead makes every decision; the outcome is the team's. Two pieces:

- **A failed part goes back to the team.**
  - A sub-agent whose reply is malformed (`SCHEMA`) or whose call to the model fails (`LIVE`) no longer ends the run. Its part is recorded as `part_failed`.
  - The other sub-agents' results are merged, and the lead covers the failed part in the merge, the same way it covers a part the gates refused. This works in `run_task` and in `fanout`, and the operator's answer says which parts the lead covered.
  - An authority violation (`TOOLS`, `ROSTER`, `INV-*`), a budget halt and a crash still stop the run at once.
  - When several sub-agents stop, the error raised is the one that caused it, not a sibling's "run already abort".
- **A blameless review after every failure, and lessons for the next run.**
  - When a run had any failure, even one the team recovered from, the kernel writes `Run.review`. It holds what failed, what became of each part, what the team did and the outcome, and it is the last entry on the record.
  - The review is built from the record (event codes, criteria misses, part statuses), never from model text.
  - Each kind of failure maps to one fixed lesson, which is added to `guidelines/lessons.md`. Every later brief carries it. Repeats are counted, at most 10 lessons are kept, and `--no-lessons` (`Engine(lessons=False)`) turns lessons off.
  - An operator's Ctrl-C is not a team failure, and writing a review can never change a run's outcome.
- `diagnose` reports `team` (each part's outcome) and `review`, and the CLI prints the review with the run.
- Comparison trials each use a fresh store, so no lesson carries between strategies. The published figures are unchanged.
- `tests/test_ownership.py`, and 11 new mutations, for 129, all caught.

## v0.3.3 — October 2026: four follow-ups

The four items v0.3.2 left open, each with a test and a mutation:

- **Failed calls are counted.** A call that fails after it was sent stays on the record, marked `failed` with its error code. It counts toward the budget, toward `diagnose`'s `failed_calls`, and toward the calls, tokens and cost a comparison reports. It uses the endpoint's token counts when the endpoint sent them, and the brief's estimate otherwise. Before this, a failed trial looked free.
- **Saves are atomic.** Saved runs, working memory, episodes, guidelines, comparison results and policy files go to a temporary file that replaces the old one in a single step, keeping its permissions. A crash mid-save leaves the previous file. Damaged working memory is a `STORE` error, not a traceback.
- **An answered review note stays answered.** Answering a closed note again is refused, so a record cannot be rewritten or used to change the method after the fact. A deferred note can still be answered.
- **The size check counts what is sent.** An adapter now estimates its own request, and the live adapter counts its system prompt and JSON wrapping, so an oversized request is refused before it is sent rather than after. The stub and simulated adapters are unchanged, and so are the published figures.

## v0.3.2 — October 2026: review findings

A review in four parallel parts: concurrency and run state, input handling, persistence and the CLI, and decision logic with the comparison harness. Each finding was reproduced on v0.3.1 before it was fixed, and each fix has a test in `tests/test_hardening.py`.

**Concurrency and run state**
- When one sub-agent failed, its siblings kept calling the model for every remaining tool round (9 extra calls in the repro), and Ctrl-C could not stop them. The board now closes at once; no call starts after a failure.
- Parallel sub-agents each passed the pre-call budget check before any of them was recorded, so they overspent by one call each. Calls in flight now count; parallel spend matches sequential.
- An exception other than a kernel rule left the run active and unsaved. Every failure now aborts the run with a reason, and the CLI saves it as `CRASH`.
- A completed run could be aborted, a halt overwrote the first reason, a refused human override was still logged, and a roster change could halt a run that had spent its budget legally. All fixed.
- A reused engine shared one budget clock between runs. Each run gets its own.

**Budgets and decisions**
- The gates reserved 2 calls after a split, but a merge that covers a left-over part reads first, so an admitted split could run out before the verifier. The merge's tool rounds are now reserved, and work, merge and rework stop their tool rounds in time to leave the verifier its call.
- The verdict was read by prefix and substring: "PASS: nothing failed" failed and "Passing this would be wrong" passed. It is now the leading word.
- Success criteria matched as substrings: "4.1" was met by "14.1". They now match whole words and numbers.
- The measured gate counted whole files, but a read returns at most 4,000 characters, so it split work that fit. It now counts what one read returns, and refuses a split that leaves any sub-agent over the room in one call.
- Duplicate proposals got no gate record, and `fanout` silently dropped parts refused for the cap or a bad skill and claimed a fan-out that did not happen. All fixed.

**Comparison harness**
- The crew baseline dropped parts past the worker cap or with a bad id, while genet's lead covered them: same plan, crew 0/5, genet 5/5. Both now hand such parts to the lead.
- Grading took the first number on a line ("Q3" read as 3) and any "answer:" in prose. It now reads the capitalized `ANSWER:` marker and requires one value.
- "Best baseline" could name genet-stated, a genet variant, depending on argument order. It now names single or always.
- The published simulated-reader figures are unchanged.

**Input handling**
- A model's request with a NUL byte, a lone surrogate, an over-long name or a symlink loop, or a workspace folder without permission, crashed the kernel. These are now "not found" or skipped.
- One folder with 200,000 files took 64 s and 351 MB of memory across a plan; the walk now stops at its cap mid-folder (4.7 s, 60 MB).
- Partial search matches were all kept before trimming (about 1 GB in one repro); only the best 20 are kept now. Search terms are capped at 16.
- A server could hold a call open by dripping headers or an error body; one deadline now covers the whole exchange. A stalled error body, a non-object `usage`, a non-string `claim`, an out-of-range timeout or a malformed base URL are clean `LIVE` or `SCHEMA` errors.
- A snippet could drop the matched figure when lower-casing changed a line's length.

**Persistence, CLI and diagnostics**
- A setup error, such as a missing live configuration, overwrote `--out` with an empty run. Setup now happens before anything is written, and the default `--out` follows `--id`.
- Wrongly typed fields in a run file crashed read commands later; they are refused as `PERSIST` at load. Old log vocabulary is upgraded, and a loaded run keeps its elapsed time and its world.
- Aborted runs and failed stop rules reported `health: ok`; they are `degraded` now. The authority-language check is no longer evaded by quoting the rule first.
- Missing files and directories, `nan` budgets, zero or negative counts, blank criteria and run ids ending in a newline are clean errors. `bench` fails when it checked nothing, `policy-replay` reads runs through `load_run`, and the policy flags take effect.
- 36 new mutations, for 113.
- Left open, fixed in v0.3.3: failed calls missing from cost reports, non-atomic saves, re-answerable review notes, and a size estimate that left out the system prompt.

## v0.3.1 — October 2026: security hardening

A review for the class of bug behind the October 2026 PHP flaws: untrusted input that exhausts memory, escapes a sandbox or slips past parsing. Each fix has a test that fails on the code before it.

- **The API key stays with the host you named.** Redirects are refused, and the key is never copied onto a redirected request. The base URL must be `https://`, or `http://` to this machine; `TASKORG_MODEL_ALLOW_HTTP=1` allows plain HTTP elsewhere.
- **The endpoint's reply is bounded.** At most 8 MB, read within the timeout. Malformed JSON, nesting too deep and over-long numbers are clean `LIVE` or `SCHEMA` errors, not crashes. An error body is read only as far as the message needs.
- **Token counts are checked.** A reported count that is negative, fractional or not a number is ignored, and the kernel's estimate stands, so a reply cannot spend negative tokens past the budget.
- **An oversized brief is never sent.** Its size is checked against the per-call cap before the call. Before this, one reply asking for the same file 2,000 times produced an 8 MB brief that was sent before the cap stopped the run.
- **One reply does a bounded amount of work.** At most 8 tools a round (repeats count once) and 16 sub-task proposals judged per plan.
- **Hidden files stay hidden.** `read` and `observe` could reach `.env` and `.git/`, and search could reach a hidden file through a symlink. Now no tool reaches a path with a dot-named part below a workspace root.
- **The workspace walk is bounded.** It no longer lists a whole tree before applying its cap, it prunes hidden and tool folders as it goes, and one search scans at most 20M characters. The scan for file names in a sub-task note is linear; a long note used to take seconds to minutes.
- **Saved runs are untrusted.** A malformed file is a `PERSIST` error, and a saved slot cannot hold tools its skill does not allow.
- **Repository.** No secrets in any commit, no key files ever committed, and the site loads no scripts or third-party resources. Added `SECURITY.md`.
- 15 new mutations, for 77, all caught.

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

Kernel: about 6,100 lines in `taskorg/`. Suite: about 1,320 checks (including 300 fuzz sequences and 400 hostile-model runs), 9 bench fixtures, and 147 mutation checks.

## Run

```bash
pip install -e ".[dev]"
pytest -q
python -m taskorg.cli run --tier tight
python -m taskorg.cli bench
```

Live adapter: set `TASKORG_MODEL_BASE`, `TASKORG_MODEL_KEY` and `TASKORG_MODEL_NAME`, then pass `--adapter live`.
