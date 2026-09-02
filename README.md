# Genet

[Apache-2.0](LICENSE) · Python 3.11+ · kernel, not a cloud

One organism. Many stems.

A small multi-agent runtime. Authority lives in the graph, not in the prompt.

The question is not how many agents you can run. It is whether a second one is doing new work.

Most stacks treat headcount as capacity. Genet treats it as a cost. Default is one lead. A second worker is a gated exception. Quality of process over quantity of agents — possibly more efficient, and possibly more effective. That last part stays a claim until a stranger’s job says so.

This Genet is software, not the playwright.

## What it refuses

- Org-chart roleplay as architecture
- Workers that spawn workers
- `could we` as the first question
- Staying on a dead plan because the team looks aligned
- Unbounded loops

## Structure

| Piece | Job |
|---|---|
| Roster | Lead builds the team. Only the lead changes the roster. |
| Goal | Effect and done-state. |
| Memory | Cues and working facts. Not a stuffed context window. |
| Context | Shared board. Isolated worker packets. |
| Review | Heard and answered. Cannot take over the roster. |
| Method | Activate a skill on an existing slot. Add a worker only after three gates. |

Gates, in order, fail closed: **can someone else → should we → could we.**

When the plan is wrong: report it and change the method. `KEEP_ROSTER` is illegal on that note. Use `CHANGE_METHOD` or `REVISE_GOAL`.

## Budgets

| Profile | CLI flag | Allowed | Cap |
|---|---|---|---|
| Tight | `--pace crawl` | `run` only | 4 calls / 4k tokens / 30s |
| Normal | `--pace walk` | `run` + `adapt` | 8 / 15k / 60s |
| Open | `--pace run` | + gated `split` | 12 / 50k / 120s |

CLI defaults to crawl. Do not open the budget because the model sounded ready.

## Install

```bash
git clone <this-repo>
cd taskorg
pip install -e ".[dev]"
pytest -q
```

## Commands

```bash
python -m taskorg.cli run --pace crawl --out data/missions/crawl.json
python -m taskorg.cli adapt --pace walk --out data/missions/walk.json
python -m taskorg.cli split --pace run \
  --look "seam:source-a=independent_a seam:source-b=independent_b" \
  --out data/missions/fanout.json
python -m taskorg.cli diagnose data/missions/crawl.json
python -m taskorg.cli board data/missions/crawl.json
python -m taskorg.cli bench
```

Flags: `--exists` (world already has the file), `--read` (file text into the brief), `--criteria` (verifier tokens).

Live model (optional):

```bash
export TASKORG_MODEL_BASE=https://api.x.ai/v1
export TASKORG_MODEL_KEY=
export TASKORG_MODEL_NAME=
python -m taskorg.cli run --adapter live --pace crawl
```

## Nets

- element — isolated worker deltas merge into shared context
- up — review notes
- out — report to the operator
- adjacent — peer graph; contexts do not merge

## Diagnose

`health`, budget remaining, `isolation` (did B’s brief contain `channel:A`), `could_this_have_been_one`.

A tight run that grew the roster is a fail. A normal run that answers a dead plan with `KEEP_ROSTER` is a fail. An open run with `isolation_leak` is a fail.

## Status

v0.1 kernel. Invariants covered by tests. Not a cloud platform.

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
