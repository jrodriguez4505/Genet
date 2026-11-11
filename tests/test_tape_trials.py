"""A tape marks each exchange with the trial that sent it, and a replay serves each trial the replies its own run got.

Two trials may send the same request, as two strategies that work alike do, and the model answers each in its own way.
A tape from before the marks served identical requests in the order they were recorded: exact for the whole run, its
strategies in their order, but one strategy replayed alone could be served another's reply. On the head-to-head's
HotpotQA tape, Genet replayed alone came out 5 tokens off on one trial; replayed with all three strategies, 60 of 60 were
as they ran."""

from __future__ import annotations

import json
import types

import pytest

from taskorg import compare, tape
from taskorg.anthropic_live import AnthropicAdapter
from taskorg.cli import main
from taskorg.compare import SingleAgent, run_comparison
from taskorg.errors import InvariantError
from taskorg.suite import build_suite

from test_anthropic_tape import MODEL, Client, _sim_answer

SUITE = dict(seed=7, per_family=1, families=("lookup", "breadth"))


@pytest.fixture
def twin(monkeypatch):
    """A second strategy that sends exactly what single sends, as genet-reads does where one agent's pages fit."""
    monkeypatch.setitem(compare.STRATEGIES, "single-too", SingleAgent)


def _counting():
    """The simulated reader, with usage that differs on every call: the same request answered twice is told apart."""
    n = [0]

    def answer(kw):
        n[0] += 1
        msg = _sim_answer(kw)
        msg.usage = types.SimpleNamespace(**(vars(msg.usage) | {"input_tokens": msg.usage.input_tokens + n[0]}))
        return msg

    return answer


def _record(path, strategies):
    client = Client(_counting())
    rec = tape.Recorder(path, AnthropicAdapter("", MODEL, effort="low", client=client).tape_header())

    def live():
        a = AnthropicAdapter("", MODEL, effort="low", client=client)
        a.tape = rec
        return a

    results = run_comparison(build_suite(**SUITE), live, strategies=strategies)
    rec.close()
    return results


def _same(r):
    return (r.task_id, r.strategy, r.answer, r.correct, r.calls, r.tokens, r.workers, r.status, r.code)


def _replay(path, strategies):
    player = tape.Player(path)
    return run_comparison(build_suite(**SUITE), lambda: tape.replay_adapter(player), strategies=strategies), player


def _unmarked(path, to):
    lines = path.read_text().splitlines()
    to.write_text("\n".join([lines[0]] + [json.dumps({k: v for k, v in json.loads(ln).items() if k != "trial"})
                                          for ln in lines[1:]]) + "\n")
    return to


def test_every_exchange_is_marked_with_the_trial_that_sent_it(tmp_path, twin):
    results = _record(tmp_path / "t.jsonl", ("single", "single-too"))
    entries = [json.loads(ln) for ln in (tmp_path / "t.jsonl").read_text().splitlines()[1:]]
    trials = {f"{r.strategy}-{r.task_id}-r{r.repeat}" for r in results}
    assert entries and {e["trial"] for e in entries} == trials


def test_one_strategy_replayed_alone_is_as_it_ran(tmp_path, twin):
    recorded = _record(tmp_path / "t.jsonl", ("single", "single-too"))
    # The two strategies send the same requests, so a shared request has two recorded replies.
    keys = [json.loads(ln)["key"] for ln in (tmp_path / "t.jsonl").read_text().splitlines()[1:]]
    assert len(set(keys)) < len(keys)
    for strategy in ("single-too", "single"):
        replayed, player = _replay(tmp_path / "t.jsonl", (strategy,))
        assert [_same(r) for r in replayed] == [_same(r) for r in recorded if r.strategy == strategy]
        assert player.misses == 0 and player.marked
    # The same tape without its marks: single-too alone is served single's replies, and its tokens come out wrong.
    replayed, player = _replay(_unmarked(tmp_path / "t.jsonl", tmp_path / "old.jsonl"), ("single-too",))
    assert not player.marked and player.misses == 0
    assert [_same(r) for r in replayed] != [_same(r) for r in recorded if r.strategy == "single-too"]
    # Whole, its strategies in their order, an unmarked tape is still exact.
    whole, _ = _replay(tmp_path / "old.jsonl", ("single", "single-too"))
    assert [_same(r) for r in whole] == [_same(r) for r in recorded]


def _tape(tmp_path, *entries):
    path = tmp_path / "t.jsonl"
    rows = [{"tape": 1, "adapter": "anthropic", "model": "m"}]
    for trial, reply in entries:
        rows.append({"key": "a" * 64, **({"trial": trial} if trial else {}), "request": {}, "reply": reply,
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "error": None})
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return tape.Player(path)


def test_a_trial_gets_its_own_replies_in_order_and_others_get_the_tapes_order(tmp_path):
    player = _tape(tmp_path, ("A", "a1"), ("B", "b1"), ("A", "a2"))
    assert [player.take("a" * 64, "B")["reply"], player.take("a" * 64, "A")["reply"],
            player.take("a" * 64, "A")["reply"], player.take("a" * 64, "A")["reply"]] == ["b1", "a1", "a2", "a2"]
    # A trial the tape never marked, or no trial at all, is served in the tape's order, as before the marks.
    assert [player.take("a" * 64, "C")["reply"], player.take("a" * 64)["reply"]] == ["a1", "b1"]
    old = _tape(tmp_path, (None, "x1"), (None, "x2"))
    assert not old.marked and [old.take("a" * 64, "A")["reply"], old.take("a" * 64, "B")["reply"]] == ["x1", "x2"]


def test_a_replay_that_goes_live_serves_each_trial_its_own_replies_first(tmp_path, monkeypatch):
    player = _tape(tmp_path, ("A", "a1"), ("B", "b1"))
    monkeypatch.setattr(tape, "request_key", lambda payload, cap: "a" * 64)
    cont = tape.Continuing(player, tape.Recorder(tmp_path / "live.jsonl", {"adapter": "anthropic"}), "ARM", tape.LiveSpend())
    adapter = types.SimpleNamespace(max_reply_param=None, trial="B", last_usage={})
    assert cont.exchange(adapter, {"system": "s"}) == "b1" and not cont.armed


def test_a_trial_mark_that_is_not_a_name_is_a_damaged_tape(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m"}) + "\n" + json.dumps(
        {"key": "a" * 64, "trial": 7, "request": {}, "reply": "r", "usage": {}, "error": None}) + "\n")
    with pytest.raises(InvariantError, match="not a recorded exchange"):
        tape.Player(path)


def test_replaying_some_of_an_unmarked_tapes_strategies_says_what_that_costs(tmp_path, twin, capsys):
    _record(tmp_path / "t.jsonl", ("single", "single-too"))
    # The compare header a run writes: the replay compares its settings with the tape's.
    settings = {"strategies": ["single", "single-too"], "families": list(SUITE["families"]), "per_family": 1, "seed": 7}
    for name, path in (("marked", tmp_path / "t.jsonl"), ("old", _unmarked(tmp_path / "t.jsonl", tmp_path / "old.jsonl"))):
        lines = path.read_text().splitlines()
        lines[0] = json.dumps(json.loads(lines[0]) | {"compare": settings})
        path.write_text("\n".join(lines) + "\n")
        base = ["compare", "--replay", str(path), "--seed", "7", "--per-family", "1", "--families", "lookup,breadth"]
        assert main(base + ["--strategies", "single-too", "--out", str(tmp_path / f"{name}-part.json")]) == 0
        err = capsys.readouterr().err
        assert ("does not mark which trial sent each request" in err) is (name == "old")
        assert "different strategies" not in err
        assert main(base + ["--strategies", "single,single-too", "--out", str(tmp_path / f"{name}-whole.json")]) == 0
        assert "does not mark" not in capsys.readouterr().err
