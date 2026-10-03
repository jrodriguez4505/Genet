# Live test log — 1 September 2026

Model: `grok-4.20-0309-non-reasoning`. Operator machine. Adapter `live`.

These runs used v0.1. The commands below use the current names: `single` was `run`, `fanout` was `split`, `replan` was `adapt`, and `--tier tight|normal|open` was `--pace crawl|walk|run`. Behavior has also changed since: a single open sub-task is now the lead's job and no longer gets its own worker.

## Offline same day

- `pytest -q` → 121 passed in 12.65s
- `python3 -m taskorg.cli policy-rl --episodes 40` → stub and learned `illegal_rate: 0`, `mean_workers: 0`, `PROPOSE_CHANNEL: 0`

## Two-file folder

World: `$HOME/genet-job/note-a.txt` filed, `note-b.txt` open.

| Id | Setup | Status | Workers | Split | Spend |
|---|---|---|---|---|---|
| job-notes-1 | `fanout`; the default `--axes` still had an invalid axis | halt METHOD | 0 | — | 0 calls |
| job-notes-2 | `fanout`, `--exists` A, `--read` B, `--axes sequential,fan_in` | complete | 1 (`note-b`) | true | 3 calls / 2379 tok / 6.9s |
| job-notes-3 | `fanout`, `--exists` A and B | complete | 0 | false | 2 calls / 1396 tok / 3.9s |

- **job-notes-2:** only the open sub-task got a worker. Isolation and authority flags were empty; health ok.
- **job-notes-3:** open tier (fan-out allowed), yet `decide()` still refused. Verifier 1.0; `could_this_have_been_one: true`.

## Replan and budget cap

| Id | Setup | Status | Workers | Spend |
|---|---|---|---|---|
| job-adapt-1 | `replan --tier normal`; the first outline no longer fit | complete | 0 | 2 calls / 1506 tok / 4.1s |
| job-leash-1 | `single --tier tight --max-calls 1` | abort BUDGET | 0 | 1 call / 688 tok / 2.5s |

- **job-adapt-1:** the method became "start from definitions, not from jargon". Roster unchanged; verifier 1.0; health ok.
- **job-leash-1:** `BUDGET: max_calls 1 reached`, flagged `budget_halt`. Health degraded, which is expected on an abort. Roster unchanged.

## Keep locally (do not commit)

`job-notes-2.json`, `job-notes-3.json`, `job-adapt-1.json`, `job-leash-1.json`.
