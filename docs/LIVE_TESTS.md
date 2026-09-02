# Live test log — 1 September 2026

Model: `grok-4.20-0309-non-reasoning`. Operator machine. Adapter `live`.

## Offline same day

- `pytest -q` → 121 passed in 12.65s
- `python3 -m taskorg.cli policy-rl --episodes 40` → stub and learned `illegal_rate: 0`, `mean_workers: 0`, `PROPOSE_CHANNEL: 0`

## Two-file folder

World: `$HOME/genet-job/note-a.txt` filed, `note-b.txt` open.

| Id | Setup | Status | Workers | Split | Spend |
|---|---|---|---|---|---|
| job-notes-1 | default `--axes` still had `back_to_front` | halt HOW | 0 | — | 0 calls |
| job-notes-2 | `--exists` A, `--read` B, `--axes sequential,fan_in` | complete | 1 (`note-b`) | true | 3 calls / 2379 tok / 6.9s |
| job-notes-3 | `--exists` A and B | complete | 0 | false | 2 calls / 1396 tok / 3.9s |

job-notes-2: only the open seam hired. Isolation and authority flags empty. Health ok.

job-notes-3: pace was `run` (split allowed). `decide()` still refused. Verifier 1.0. `could_this_have_been_one: true`.

## Adapt and leash

| Id | Setup | Status | Workers | Spend |
|---|---|---|---|---|
| job-adapt-1 | `adapt --pace walk`; first outline dead | complete | 0 | 2 calls / 1506 tok / 4.1s |
| job-leash-1 | `run --pace crawl --max-calls 1` | abort BUDGET | 0 | 1 call / 688 tok / 2.5s |

job-adapt-1: method `start from definitions, not from jargon`. Roster unchanged. Verifier 1.0. Health ok.

job-leash-1: `BUDGET: max_calls 1 reached`. Flag `budget_halt`. Health degraded (expected on abort). Roster unchanged.

## Keep locally (do not commit)

`job-notes-2.json`, `job-notes-3.json`, `job-adapt-1.json`, `job-leash-1.json`.
