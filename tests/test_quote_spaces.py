"""The kernel's quote check reads zero-width characters as space (11 November 2026). Loong's 2024 filings put a
zero-width space after many figures ("0.19​  $  (0.02)​"). A model's quote leaves it out, so a quote that is in
the file was flagged as not in it, and the verifier was told so: 31 of 190 flags on the Loong tapes were false for that
alone, and two of the seven right products the verifier failed under the split rule had only such flags
(docs/LIVE_TESTS.md). A benchmark run names the check; a benchmark tape from before names nothing, and replays under
the check as it was."""

from __future__ import annotations

import json

from taskorg import checks, compare
from taskorg.budget import Budget
from taskorg.cli import _as_recorded, main
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.tools import Toolbox

# A line of Dawson Geophysical's Q1 2024 10-Q, as the filing holds it.
LINE = ("Basic income (loss) per share of common stock" + " " * 60 + "​  $" + " " * 16 + "0.19​  $"
        + " " * 14 + "(0.02)​\n")
QUOTE = 'dawson.txt:1065: "Basic income (loss) per share of common stock $ 0.19 $ (0.02)"'


def _product(*evidence):
    return Artifact(claim="Basic EPS was $0.19. ANSWER: $0.19", evidence=list(evidence), uncertainty="none",
                    channel_id="lead-merge", context_update="")


def _toolbox(tmp_path):
    (tmp_path / "dawson.txt").write_text("FORM 10-Q\n\n" + LINE)
    return Toolbox(roots=[tmp_path])


def test_a_quote_that_leaves_out_zero_width_spaces_is_in_the_file(tmp_path):
    tb = _toolbox(tmp_path)
    names = tb.shown_files()
    assert checks.misquoted(tb, _product(QUOTE), names) == []
    # The check as it was: flagged.
    assert checks.misquoted(tb, _product(QUOTE), names, zero_width=False) == [f"dawson.txt: {QUOTE}"]
    # A wrong figure is still flagged, and so is a reworded table.
    wrong = QUOTE.replace("0.19", "0.91")
    table = 'dawson.txt: "Basic income (loss) per share of common stock | 0.19 | (0.02)"'
    assert checks.misquoted(tb, _product(wrong, table), names) == [f"dawson.txt: {wrong}", f"dawson.txt: {table}"]
    # Every zero-width character a filing may carry, and a quote that carries one itself.
    for zw in "‌‍⁠﻿":
        (tmp_path / "dawson.txt").write_text(LINE.replace("​", zw))
        assert checks.misquoted(tb, _product(QUOTE), names) == []
    assert checks.misquoted(tb, _product(QUOTE.replace("0.19 ", "0.19​ ")), names) == []


def _brief(tmp_path, **engine):
    tb = _toolbox(tmp_path)
    e = Engine(MemoryStore(tmp_path / "s"), toolbox=tb, budget=Budget(max_tokens_per_call=100_000), **engine)
    run = new_run("r", goal="What was Dawson's basic EPS in Q1 2024? dawson.txt", purpose="p", done_when="ANSWER")
    return e._verifier_brief(run, _product(QUOTE)).packet


def test_the_verifier_is_told_only_of_quotes_the_file_does_not_hold(tmp_path):
    assert Engine(MemoryStore(tmp_path / "e")).quote_spaces is True
    assert "KERNEL CHECK" not in _brief(tmp_path)
    assert f"KERNEL CHECK: these evidence quotes are not in the files they cite:\n- dawson.txt: {QUOTE}" in _brief(
        tmp_path, quote_spaces=False)


def _hotpot(tmp_path):
    rows = [{"id": "5a0000000", "type": "bridge", "question": "Q?", "answer": "rehearsal",
             "context": {"title": ["Ta", "Tb"], "sentences": [["One."], ["Two."]]}}]
    path = tmp_path / "hotpot.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_a_benchmark_run_names_the_check_and_hands_it_to_every_trial(tmp_path, monkeypatch, capsys):
    seen = []
    trial = compare.run_trial

    def spy(*a, **k):
        seen.append((k.get("verify") or {}).get("quote_spaces"))
        return trial(*a, **k)

    monkeypatch.setattr(compare, "run_trial", spy)
    out = tmp_path / "r.json"
    assert main(["compare", "--adapter", "stub", "--benchmark", "hotpot", "--questions", str(_hotpot(tmp_path)),
                 "--strategies", "single,genet", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["config"]["quote_spaces"] is True and seen == [True, True]
    # Generated notes hold no zero-width spaces: their runs, and tapes, read as before.
    capsys.readouterr()
    assert main(["compare", "--adapter", "stub", "--dry-run", "--per-family", "1"]) == 0
    assert "quote_spaces" not in json.loads(capsys.readouterr().out)


def test_a_benchmark_tape_from_before_replays_under_the_check_as_it_was(capsys):
    config = {"quote_spaces": True}
    _as_recorded({"benchmark": "loong", "page_chars": 16000}, config)
    assert config["quote_spaces"] is False and "quote check read zero-width characters as text" in capsys.readouterr().err
    # Both settings at once, as a paged Loong tape from before names neither.
    config = {"quote_spaces": True, "genet_split": "reads"}
    _as_recorded({"benchmark": "loong", "page_chars": 16000}, config)
    assert config == {"quote_spaces": False, "genet_split": "measured"}
    config = {"quote_spaces": True, "genet_split": "reads"}
    _as_recorded({"benchmark": "loong", "quote_spaces": True, "genet_split": "reads"}, config)
    assert config == {"quote_spaces": True, "genet_split": "reads"}
