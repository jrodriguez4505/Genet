# Contributing

Start in the tight tier. Do not send a PR that adds a worker without a three-gate record.

```bash
pip install -e ".[dev]"
pytest -q
```

- Authority lives in `taskorg/run.py` and `taskorg/gates.py`, not in prompts.
- New behavior needs a test that fails closed, in `tests/`. If it changes how a run is staffed, it also needs a fixture with an `expect` block in `fixtures/bench/`. `python -m taskorg.cli bench` stays green.
- Tier tests stay green: the tight tier cannot fan out or replan.
- Tools only read, and only inside the operator's workspace. A new tool needs a sandbox test.
- The README's Terms table maps concepts to code names. Keep it current when you add either.
- The public name is Genet. The import remains `taskorg`.

- License is Apache-2.0. A patch is a contribution under that license.
- Partnerships and commercial questions: open a GitHub issue labeled `partnership`.
