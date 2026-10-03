# Genet — completed work

Apache-2.0. Public repo: https://github.com/jrodriguez4505/Genet

## v0.2 — October 2026

### The platoon model in code

- **The lead organizes the team.** `Engine.run_mission` / `taskorg mission`: the lead reads the situation and proposes elements as `seam:<channel>@<qual>=<named_failure>`. The kernel judges every proposal; the lead never writes the roster.
- **Real gates.** `gates.assess` checks:
  - world coverage (exact file name or channel)
  - a staffed or repeated channel
  - verification already belonging to the verifier
  - a named failure
  - a known specialty and a usable channel id
  - the pace
  - budget affordability, counting each element's tool rounds
  - the worker cap
  - a single open part being the lead's job

  Every verdict is logged as a full gate record.
- **Specialists.** Each qualification has a role brief, a tool allowlist, and an optional model (`TASKORG_MODEL_NAME_<QUAL>`). Elements are created with the qualification their seam names. The lead cross-trains when one body does a specialist's job.
- **Sandboxed tools.** `read`, `retrieve` and `observe` cover the `--workspace` directories and the `--read` files only, and they only read. The allowlist is checked before anything runs. Each round is a budgeted call; at most 2 rounds per element.
- **Elements work at the same time.** Threads with locked board accounting and per-thread usage in the live adapter. Results are accepted in seam order, so the board is deterministic.
- **Adapting on contact.** If the verifier fails the product at walk or run, the lead reports the plan wrong, changes the method and reworks once.
- **Comparison harness.** `taskorg compare` runs single agent vs always-split crew vs genet on a seeded synthetic suite (lookup, aggregate, compare, breadth). Everything but the task organization is held equal. It reports accuracy, tokens, calls, latency, split rate and cost. It has been validated offline with an oracle model; **no live results yet**.
- **Elements and the cap.** Parts refused for capacity or a malformed proposal no longer drop: the lead covers them while regrouping, with its search tools.
- **Deterministic reader (`--adapter sim`).** Solves every suite task under every strategy, which proves the harness gives each strategy the facts it needs. It also gives a structural cost comparison at $0. With a perfect reader, one agent is cheapest in every family; splitting can only pay where a real model reads worse in one context.
- **Element notes.** Each sub-agent now gets the lead's note from its seam, not only its channel name. Before this, a crew's assignments never reached its workers.
- **New test suites.**
  - **Red team:** hostile model output must be refused, contained or halted.
  - **Invariant fuzzing:** 300 random sequences of 40 calls each.
  - **Concurrency stress.**
  - **Live adapter** against a fake OpenAI-compatible endpoint.
- **Found by the fuzzer, and fixed:**
  - An unknown slot raised a raw `KeyError`.
  - A completed or aborted board still accepted notes, skill changes and deltas. Closed boards are now read-only (`CLOSED`).
  - Reusing a note id silently overwrote an open plan-wrong report, which could then be answered with `KEEP_ROSTER`. Note ids are now single-use.
- **Diagrams.** `docs/diagrams/build.py` renders three explainer figures in light and dark for the README and inline for the Pages site:
  - three ways to staff a task
  - the gate funnel
  - control plane vs model plane
- **Native bench.** `taskorg bench` scores every fixture's `expect` block. It no longer needs pytest. Four mission fixtures were added.

### Fixes from the review

- The README's `split` and `adapt` failed with their own default axes. A run that died on an invariant was saved as `active`; it is now `abort`.
- **Element isolation leaked.** An element's brief carried the living picture, which held a sibling's product. Elements now get the picture as it stood at the split. The isolation check covers the whole brief, and the verdict survives save and load (it used to read a field that saving drops).
- **The CLI loaded code from `~/src/ecphory/src` on every command.** That hook is removed.
- **A reused mission id inherited the last run's working memory.** Each CLI run now starts clean. Mission ids are checked before they become file names.
- **The verifier could pass an empty product by echoing the criteria.** Criteria must now show in the product.
- **"Already exists" used substring matching,** so channel `a` was blocked by any path containing an "a". It now matches exact names.
- **`write_who` problems:**
  - A refused change still logged a `split`.
  - A worker could be re-tasked to a new channel without gates.
  - Duplicate slot ids were accepted.
- **Gate checking order:** `GateRecord.assert_legal` checked "should we" before "can someone else".
- **A budget off-by-one:** a run that used exactly its call budget was aborted and its last call discarded.
- **Tool violations were reported as `BUDGET`.**
- **Policy JSON:** a confidence of 0 became 0.5, and bad JSON escaped as a raw error.
- **Live adapter:**
  - An empty `TASKORG_MODEL_NAME` was sent as `""`.
  - Read timeouts and HTTP error bodies escaped as raw tracebacks.
  - The lead and verifier were told they were Workers.
- **Tests that could not fail:** `or True` and similar assertions now actually assert.

## v0.1 — 1 September 2026

A small multi-agent runtime. A run starts as one lead. Skills sit latent. Context turns a skill on. A second worker is legal only after three gates, in order: can-someone-else → should-we → could-we. Models fill a structured artifact. They do not rewrite the roster.

| Piece | Job |
|---|---|
| Mission / picture | Shared board |
| Engine | Inspect → skill → gates → maybe a worker → verify → close |
| Gates + World | Covered work refuses a new body |
| Budget / pace | Crawl no split; walk adapt only; run may split |
| Live adapter | Chat completions → Artifact JSON only |
| Verifier | Named criteria plus world checks |
| CLI | `run split adapt brief board diagnose bench policy-*` |

### Policy sprints (experimental, not wired into missions)

- **N1:** socket, encoder, and `apply_decision`, which never grows the roster.
- **N2:** an imitation logistic head with gold accuracy 1.0 on the synthetic set. The set has 9 distinct states; training and "held-out" rows overlap; and the gold labels never include `PROPOSE_CHANNEL`. This shows the plumbing, not learning.
- **N3:** sparse RL with an illegal rate of 0 vs the stub. `apply_decision` cannot add workers and the head never proposes channels, so 0 holds by construction.
- **Fine-tune:** SFT JSONL plus a local head trained on the same synthetic corpus. No Grok weight job exists on the public xAI API.

### Live proof (operator key)

`grok-4.20-non-reasoning`. Crawl stayed one body. Walk changed method, not headcount. Run split two isolated channels; isolation was checked on packets only then, see v0.2. Exists skipped the file already on disk. Job-status-1e wrote a five-line status from an attached README with criteria `live proof` / `one body`.

Live boards stay local. They are not committed; `.gitignore` covers `data/`.

## Not claimed

Not a product. Not a GAIA score. Not a fine-tuned Grok checkpoint. GAIA vs CrewAI stays closed until a shared harness exists (see `fixtures/bench/GAIA.md`).

## Size

Kernel: about 4,900 lines in `taskorg/`. Suite: 519 checks (219 tests plus 300 fuzz sequences), and 9 bench fixtures.

## Run

```bash
pip install -e ".[dev]"
pytest -q
python -m taskorg.cli mission --pace crawl
python -m taskorg.cli bench
```

Live adapter: `TASKORG_MODEL_BASE`, `TASKORG_MODEL_KEY`, `TASKORG_MODEL_NAME`, `--adapter live`.
