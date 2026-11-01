# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through **Report a vulnerability** on this repository's Security tab. Include what you found, how to reproduce it, and what it affects.

## What Genet treats as untrusted

- **The model endpoint's reply.** Its size, its timing over the whole exchange (connect, headers and body), its JSON and its token counts.
- **Model output.** Tool requests, sub-task proposals and artifact fields. A model can be steered by text it reads, so a request from a model is never trusted because it looks reasonable.
- **The workspace.** Files can carry planted instructions, and folders can be huge, unreadable or full of pipes. Tools only read, only inside the declared roots, never hidden files, and never through a symlink that leads outside or into a hidden file.
- **Saved runs.** A file loaded with `replan`, `diagnose` or `replay` may come from someone else.

The limits that enforce this are listed in the README under Security. They are enforced in code, and each has a test in `tests/test_security.py` and a mutation in `scripts/mutation_check.py`.

## What it does not cover

- Genet sends the brief, including workspace text a tool returned, to the model endpoint you configure. Point it only at a provider you trust with that text.
- Saved runs in `data/` hold briefs and tool results, so treat them like the workspace they came from.
- The API key is read from `TASKORG_MODEL_KEY`, and Claude's from `TASKORG_ANTHROPIC_KEY`. Keep them out of files the workspace can see.
- A model can be steered. A planted instruction in a workspace file can reach every member's brief, the verifier's included, because the kernel opens files for it. Code holds the team, the tools and the budget, and it holds the rule that a verdict's first word decides it. It cannot make a model's judgement sound. How often a planted instruction changes a verdict is not measured.
- A saved run is a record, not proof. It is checked for its shape, not for edits, so a run rewritten after the fact can load and report healthy.

## What model text can reach

`tests/test_threat_map.py` puts a marker in every field a model fills, then checks where it goes.

| Place | Model text | Why |
|---|---|---|
| The roster, the tools, the budget | Never directly | A proposal passes the gates. A tool request passes the skill's allowlist and runs read-only. A channel id must be short and plain. |
| The next member's brief in this run | Yes | The lead reads its members' reports, and the shared context carries notes. This is how the team works. |
| The run's log, and the run's saved file | Yes | The record says what each member said. |
| `episodic/` in the store | Yes | Written at the end of a run. No code reads it back. |
| `guidelines/` and lessons | Never | A lesson is one of the fixed sentences in `review.py`. |
| `records/positions.json` | Never | Counts from the run's record. A skill must be a known one, a failure code is checked against a pattern, and the model's name comes from settings. |
| Any brief in a later run | Never | Each run starts with clean working memory. |
