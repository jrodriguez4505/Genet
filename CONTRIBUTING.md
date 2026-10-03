# Contributing

Crawl first. Do not send a PR that adds a Worker without a three-gate record.

```bash
pip install -e ".[dev]"
pytest -q
```

- Authority lives in `taskorg/mission.py` and `taskorg/gates.py`, not in prompts.
- New behavior needs a fixture that fails closed, in `tests/` and, when it is a mission shape, in `fixtures/bench/` with an `expect` block. `python -m taskorg.cli bench` stays green.
- Pace tests stay green: crawl cannot split or adapt.
- Tools only read, and only inside the operator's workspace. A new tool needs a sandbox test.
- The README glossary maps platoon terms to code names. Keep it current when you add either.
- Public name is Genet. Import remains `taskorg`.

- License is Apache-2.0. A patch is a contribution under that license.
- Partnerships and commercial questions: GitHub issue labeled `partnership`.
