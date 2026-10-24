# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through **Report a vulnerability** on this repository's Security tab. Include what you found, how to reproduce it, and what it affects.

## What Genet treats as untrusted

- **The model endpoint's reply.** Its size, its timing, its JSON and its token counts.
- **Model output.** Tool requests, sub-task proposals and artifact fields. A model can be steered by text it reads, so a request from a model is never trusted because it looks reasonable.
- **The workspace.** Files can carry planted instructions. Tools only read, only inside the declared roots, never hidden files, and never through a symlink that leads outside or into a hidden file.
- **Saved runs.** A file loaded with `replan`, `diagnose` or `replay` may come from someone else.

The limits that enforce this are listed in the README under Security. They are enforced in code, and each has a test in `tests/test_security.py` and a mutation in `scripts/mutation_check.py`.

## What it does not cover

- Genet sends the brief, including workspace text a tool returned, to the model endpoint you configure. Point it only at a provider you trust with that text.
- Saved runs in `data/` hold briefs and tool results, so treat them like the workspace they came from.
- The API key is read from `TASKORG_MODEL_KEY`. Keep it out of files the workspace can see.
