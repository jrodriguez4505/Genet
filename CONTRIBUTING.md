# Contributing

Do not send a PR that adds a worker without a three-gate record.

```bash
pip install -e ".[dev]"
pytest -q
```

- Authority lives in `taskorg/mission.py` and `taskorg/gates.py`, not in prompts.
- New behavior needs a fixture that fails closed.
- Budget tests stay green: crawl cannot split or adapt.
- Public name is Genet. Import remains `taskorg`.
- License is Apache-2.0. A patch is a contribution under that license.
- Partnerships and commercial questions: GitHub issue labeled `partnership`.
