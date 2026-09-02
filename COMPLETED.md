# Genet — completed work

1 September 2026. Apache-2.0. Public repo: https://github.com/jrodriguez4505/Genet

## What it is

A small multi-agent runtime. A run starts as one lead. Skills sit latent. Context turns a skill on. A second worker is legal only after three gates, in order: can-someone-else → should-we → could-we. Could-we is last. Models fill a structured artifact. They do not rewrite the roster.

A policy head may propose `HOLD / INSPECT / CHANGE_METHOD / PROPOSE_CHANNEL / STOP`. It cannot write Who.

Kernel: ~2,300 lines in `taskorg/`. Local suite: 121 tests at last count.

## The question

Are more agents the answer?

Most stacks treat headcount as capacity. Genet treats headcount as a cost and a failure mode. One worker with a shared picture and a stop rule is the default. A second body is allowed only when it is doing work that does not already exist.

That is quality of process over quantity of agents. It may also be more efficient and more effective. Efficiency is already visible in the live boards (zero workers when both files exist; one call then halt). Effectiveness versus other frameworks is not claimed yet.

## Benefit

Most stacks optimize headcount. Genet asks whether a second process is legal.

- Cost — one body is the default.
- Structure — isolation is checked; sibling channels do not see each other.
- World — `decide()` reads files and channels that already exist.
- Authority — a worker cannot seize the roster.
- Stop — calls, tokens, seconds are a leash.

## Kernel

| Piece | Job |
|---|---|
| Mission / picture | Shared board |
| Engine | Inspect → skill → gates → maybe a worker → verify → close |
| Gates + World | Covered work refuses a new body |
| Budget / pace | Crawl no split; walk adapt only; run may split |
| Live adapter | Chat completions → Artifact JSON only |
| Verifier | Named criteria plus world checks |
| CLI | `run split adapt brief board diagnose bench policy-*` |

## Policy sprints

- N1 socket + encoder + `apply_decision` never grows the roster
- N2 imitation logistic, gold accuracy 1.0 on the synthetic set
- N3 sparse RL, illegal rate 0 vs stub
- Fine-tune: SFT JSONL + local head. No Grok weight job exists on the public xAI API.

## Live proof (operator key)

Model used: `grok-4.20-0309-non-reasoning` (alias `grok-4.20-non-reasoning`).

Earlier: crawl stayed one body; walk changed method, not headcount; run split two isolated channels; exists skipped a file already on disk; job-status-1e wrote a five-line status from an attached README.

### 1 September 2026 — two-file folder

World: `$HOME/genet-job/note-a.txt` filed, `note-b.txt` open. Adapter `live`, pace `run`.

| Id | World | Status | Workers | Split | Tokens | Result |
|---|---|---|---|---|---|---|
| job-notes-1 | A filed, B open | halt HOW | 0 | — | 0 | Default `--axes` still had `back_to_front`. No model call. Reran with `sequential,fan_in`. |
| job-notes-2 | A filed, B open | complete | 1 (`note-b`) | true | 2379 / 3 calls / 6.9s | Only the open seam hired. Isolation clean. Authority clean. Health ok. |
| job-notes-3 | A and B both `--exists` | complete | 0 | false | 1396 / 2 calls / 3.9s | Split allowed by pace; `decide()` still refused. Verifier 1.0. `could_this_have_been_one: true`. |
| job-adapt-1 | walk; first outline dead | complete | 0 | false | 1506 / 2 calls / 4.1s | Method `start from definitions, not from jargon`. Roster unchanged. |
| job-leash-1 | crawl `--max-calls 1` | abort BUDGET | 0 | false | 688 / 1 call / 2.5s | `max_calls 1 reached`. `budget_halt`. Health degraded (expected). |

Hire only the open seam. Hire nobody when nothing is open. Change How, not Who. Stop after one call.

Offline same day: `pytest -q` → 121 passed. `policy-rl --episodes 40` → stub and learned `illegal_rate: 0`, `mean_workers: 0`, `PROPOSE_CHANNEL: 0`.

Live boards stay local. They are not committed.

## Not claimed

Not a product. Not a GAIA score. Not a fine-tuned Grok checkpoint. GAIA vs CrewAI stays closed until a shared harness exists.

## Run

```bash
pip install -e ".[dev]"
pytest -q
python -m taskorg.cli run --pace crawl
python -m taskorg.cli policy-sft --out data/policy/sft.jsonl
```

Live adapter: `TASKORG_MODEL_BASE`, `TASKORG_MODEL_KEY`, `TASKORG_MODEL_NAME`, `--adapter live`.
