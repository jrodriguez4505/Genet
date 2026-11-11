"""The split rule is the default since 11 November 2026: compare's genet, and run's --split-policy, split under "reads".
Where Genet split on Loong, over two draws of the 54 questions, right rose from 16 to 24 (+8 / -0, p 0.008), wrong from
24 to 26, and it finished 31% sooner (docs/LIVE_TESTS.md). genet-measured is genet as it was before. The rule acts only
on paged reads, so only a paged run names its policy; a paged tape from before names none, and its genet replays under
"measured", as it ran, with the run's config saying so."""

from __future__ import annotations

import argparse
import json
import re

from taskorg import cli
from taskorg.anthropic_live import AnthropicAdapter
from taskorg.cli import _genet_split, main

from test_anthropic_tape import MODEL, Client, _msg, _sim_answer
from test_rework_reads import _Haiku

# Four notes grown to 30,000 characters, read 8,000 at a time, at a 40,000-token call: the notes whole do not fit the
# gates' share of a call, so "measured" plans, but a page of each does, so the rule works alone.
PAGED = ["--seed", "113", "--per-family", "1", "--families", "aggregate", "--entities", "4", "--pad-notes", "30000",
         "--page-chars", "8000", "--context", "40000", "--max-calls", "40"]


def test_a_paged_run_names_the_policy_and_an_unpaged_one_does_not(capsys):
    assert main(["compare", "--dry-run", *PAGED]) == 0
    assert json.loads(capsys.readouterr().out)["genet_split"] == "reads"
    assert main(["compare", "--dry-run", "--seed", "113", "--per-family", "1", "--families", "aggregate"]) == 0
    assert "genet_split" not in json.loads(capsys.readouterr().out)


def test_a_paged_tape_from_before_replays_its_genet_under_measured(capsys):
    config = {"genet_split": "reads"}
    _genet_split({"strategies": ["genet"], "page_chars": 8000}, config)
    assert config["genet_split"] == "measured" and "split under the measured policy" in capsys.readouterr().err
    for recorded in ({"genet_split": "reads"}, {}):  # a tape that names the rule, or one with no compare settings
        config = {"genet_split": "reads"}
        _genet_split(recorded, config)
        assert config == {"genet_split": "reads"} and capsys.readouterr().err == ""
    unpaged: dict = {}
    _genet_split({"strategies": ["genet"]}, unpaged)
    assert unpaged == {}


def _planner(kw):
    """The simulated reader, except that asked for a plan it proposes one part for each company's note the question
    names, as a lead does with notes too big for one call."""
    u = json.loads(kw["messages"][0]["content"])
    if u["function"] != "lead" or u["mode"] != "plan":
        return _sim_answer(kw)
    names = re.split(r", | and ", u["goal"].rsplit(" of ", 1)[1].rstrip("?"))  # "... of A, B, C and D?"
    notes = [re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-") + ".md" for n in names]
    parts = [f"subtask:{n[:-3]}@retrieve=report the figure the goal asks for from {n}" for n in notes]
    reply = json.loads(_sim_answer(kw).content[-1].text)
    text = json.dumps(reply | {"claim": "Plan: one part a note.", "requests": parts})
    return _msg(text, {"input_tokens": 100, "output_tokens": 50})


def _row(r):
    return (r["task_id"], r["strategy"], r["answer"], r["status"], r["calls"], r["tokens"], r["workers"])


def test_a_paged_tape_recorded_before_the_default_changed_replays_as_it_ran(tmp_path, monkeypatch, capsys):
    client = Client(_planner)
    monkeypatch.setattr(cli, "pick_adapter", lambda name: AnthropicAdapter("", MODEL, effort="low", client=client))
    tape = tmp_path / "t.jsonl"
    # Recorded as genet ran before 11 November, under the header such a tape has: no policy named.
    with monkeypatch.context() as m:
        m.setattr(cli, "SPLIT_DEFAULT", "measured")
        assert main(["compare", "--adapter", "anthropic", "--record", str(tape), "--strategies", "genet", *PAGED,
                     "--out", str(tmp_path / "was.json")]) == 0
    lines = tape.read_text().splitlines()
    head = json.loads(lines[0])
    assert head["compare"].pop("genet_split") == "measured"
    tape.write_text("\n".join([json.dumps(head)] + lines[1:]) + "\n")
    was = json.loads((tmp_path / "was.json").read_text())["results"]
    assert was and all(r["workers"] > 0 for r in was)  # "measured" split each question
    capsys.readouterr()

    assert main(["compare", "--replay", str(tape), "--strategies", "genet", *PAGED, "--out", str(tmp_path / "again.json")]) == 0
    out = capsys.readouterr()
    assert "split under the measured policy" in out.err and ", 0 requests the tape does not have" in out.out
    again = json.loads((tmp_path / "again.json").read_text())
    assert again["config"]["genet_split"] == "measured"
    assert [_row(r) for r in again["results"]] == [_row(r) for r in was]

    # The same question under today's genet: the rule, with no planning call and no split.
    assert main(["compare", "--adapter", "anthropic", "--strategies", "genet", *PAGED, "--out", str(tmp_path / "now.json")]) == 0
    now = json.loads((tmp_path / "now.json").read_text())
    assert now["config"]["genet_split"] == "reads" and all(r["workers"] == 0 for r in now["results"])


def test_a_replay_that_goes_live_keeps_the_tapes_policy_and_records_it(tmp_path, monkeypatch, capsys):
    # The replay up to the rework must send what the tape has, so its genet plans as it did; the live tape says so.
    tape = tmp_path / "t.jsonl"
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "claude-haiku-5-5", "effort": "low",
                                "compare": {"strategies": ["genet"], "page_chars": 16000}}) + "\n")
    monkeypatch.setattr(cli, "pick_adapter", lambda name: _Haiku())
    args = argparse.Namespace(replay=str(tape), record=str(tmp_path / "l.jsonl"), adapter="anthropic",
                              gap_check=False, rework_reads=False, rework_keeps=True)
    config = {"genet_split": "reads"}
    _, _, recorder = cli._continuing_source(args, config, "compare", "COMPARE")
    recorder.close()
    assert config["genet_split"] == "measured" and "split under the measured policy" in capsys.readouterr().err
    assert json.loads((tmp_path / "l.jsonl").read_text().splitlines()[0])["compare"]["genet_split"] == "measured"
