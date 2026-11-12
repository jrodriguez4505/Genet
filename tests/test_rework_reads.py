"""A rework that may read (--rework-reads). After a merge the lead holds no tool that reads, so a product the verifier
failed for a figure not read could only be reworded. With the switch, the lead's rework takes the single agent's skill
and is told it may read. Off by default: every request stays as it was, so the tapes replay. And --then-live, armed by
the switch, so a replay pays only for the reworks it changes."""

import argparse
import json
from pathlib import Path

import pytest

from taskorg.adapters import TOOL_RESULTS, ModelAdapter
from taskorg.budget import Budget
from taskorg.cli import _add_run_args, _engine, main
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import GAP_ARM, KEEP_ARM, REWORK_ARM, REWORK_HEAD, REWORK_READS, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.tape import Continuing, LiveSpend, Player, Recorder, request_key
from taskorg.tools import Toolbox

FILING = "Mortgage and other indebtedness, net  234,272\nNote 7. Of the debt above, 212,700 falls due after one year.\n"
MERGED = "Undetermined: Broad Street's long-term portion is not confirmed. ANSWER: undetermined"
FAILED = "FAIL. The long-term portion was not read from Note 7, so the product rests on an estimate."
ANSWER = "Broad Street Realty, Inc.: Note 7 puts 212,700 due after one year. ANSWER: Broad Street Realty, Inc."


def _art(reply):
    if isinstance(reply, Artifact):
        return reply
    return Artifact(claim=reply, evidence=["e"], uncertainty="u", channel_id="", context_update="", requests=[])


def _reading(note, *requests):
    return Artifact(claim=note, evidence=[], uncertainty="u", channel_id="", context_update="", requests=list(requests))


class Scripted(ModelAdapter):
    """Replies in turn; keeps each brief."""

    name = "scripted"

    def __init__(self, *replies):
        self.replies, self.briefs = list(replies), []
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 10}

    def estimate_tokens(self, brief):
        return 10

    def act(self, brief):
        self.briefs.append(brief)
        return _art(self.replies.pop(0))


def _rework(tmp_path: Path, *replies, skill="reason", workspace=True, **engine):
    """A lead's merged product under the given skill, then the verifier, a rework and a second check, as scripted."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "broad-street-realty-inc.txt").write_text(FILING)
    adapter = Scripted(*replies)
    run = new_run("r", goal="Which company has the highest long-term borrowings?", purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    e = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, budget=Budget(max_calls=20, allow_adapt=True),
               toolbox=Toolbox(roots=[ws]) if workspace else None, **engine)
    e._arm(run)
    lead = run.state.lead_id
    run.switch_skill(lead, lead, skill, "merge sub-agent results")
    product = e._act(run, e._brief(run, "lead", extra="MERGE.", mode="integrate"))
    run.accept_artifact(product)
    try:
        product, verified = e._verify(run, product, adapt=True)
    except InvariantError as err:
        product, verified = None, err.code
    return adapter, run, product, verified


def _reworks(adapter):
    return [b for b in adapter.briefs if b.mode == "rework"]


def test_it_is_off_by_default_and_the_rework_brief_is_as_before(tmp_path: Path):
    assert Engine(MemoryStore(tmp_path / "e")).rework_reads is False
    adapter, run, product, verified = _rework(tmp_path, MERGED, FAILED, MERGED, FAILED)
    assert verified == "VERIFY"
    (rework,) = _reworks(adapter)
    # The words the tapes hold, byte for byte: no sentence between the misses and the last product.
    assert f"{REWORK_HEAD}It said: {FAILED} Misses: claim is not PASS. Last product: {MERGED}" in rework.packet
    assert REWORK_ARM not in rework.packet and rework.skill == "reason" and "read" not in (rework.tools or [])
    assert not any(e.event == "switch_skill" and "rework" in e.detail["brief"] for e in run.log)


def test_on_a_rework_after_a_merge_reads_what_the_verifier_named(tmp_path: Path):
    adapter, run, product, verified = _rework(
        tmp_path, MERGED, FAILED, _reading("reading Note 7", "read:broad-street-realty-inc.txt"), ANSWER, "PASS. Fine.",
        rework_reads=True)
    assert verified is True and product.claim == ANSWER
    first, second = _reworks(adapter)
    assert f"Misses: claim is not PASS.{REWORK_READS} Last product: {MERGED}" in first.packet
    assert first.skill == "retrieve" and {"retrieve", "read"} <= set(first.tools)
    # The read ran, and the rework's next call had what it returned.
    assert TOOL_RESULTS in second.packet and "212,700 falls due after one year" in second.packet
    switched = [e.detail for e in run.log if e.event == "switch_skill" and e.detail["brief"].startswith("rework")]
    assert switched == [{"slot": run.state.lead_id, "skill": "retrieve", "brief": "rework: read what the verifier named",
                         "tools": ["retrieve", "read"]}]
    assert any(e.event == "tool" for e in run.log)


def test_on_the_rework_may_still_fail_and_stop_the_run(tmp_path: Path):
    *_, verified = _rework(tmp_path, MERGED, FAILED, MERGED, FAILED, rework_reads=True)
    assert verified == "VERIFY"


def test_its_reads_leave_room_for_the_check(tmp_path: Path):
    """The rework keeps a call for the check after it: rounds stop in time however often it asks to read."""
    again = [_reading("still reading", "read:broad-street-realty-inc.txt") for _ in range(40)]
    adapter, run, product, verified = _rework(tmp_path, MERGED, FAILED, *again, rework_reads=True)
    assert len(run.calls) <= 20 and adapter.briefs[-1].mode == "verify"


def test_a_lead_that_already_reads_is_left_as_it_is(tmp_path: Path):
    """A single agent, or a lead that covered a part, reworks with the tools it has, and the brief is as before."""
    adapter, run, *_ = _rework(tmp_path, MERGED, FAILED, MERGED, FAILED, skill="retrieve", rework_reads=True)
    (rework,) = _reworks(adapter)
    assert REWORK_ARM not in rework.packet and rework.skill == "retrieve"
    assert not any(e.event == "switch_skill" and "rework" in e.detail["brief"] for e in run.log)


def test_without_a_workspace_there_is_nothing_to_read(tmp_path: Path):
    adapter, run, *_ = _rework(tmp_path, MERGED, FAILED, MERGED, FAILED, workspace=False, rework_reads=True)
    (rework,) = _reworks(adapter)
    assert REWORK_ARM not in rework.packet and rework.skill == "reason"


def test_the_arm_is_the_start_of_the_sentence_and_no_other_switch_has_it():
    assert REWORK_READS.startswith(f" {REWORK_ARM}:") and REWORK_ARM not in GAP_ARM


# --- the switch from the command line ---


def test_run_commands_take_the_switch(tmp_path: Path):
    p = argparse.ArgumentParser()
    _add_run_args(p, id="r", goal="g", purpose="p", done_when="d", context="c")
    for argv, want in ((["--workspace", str(tmp_path)], False), (["--workspace", str(tmp_path), "--rework-reads"], True)):
        assert _engine(p.parse_args(argv), MemoryStore(tmp_path / "s")).rework_reads is want


def test_compare_puts_the_switch_on_the_record(tmp_path: Path, capsys):
    base = ["compare", "--dry-run", "--per-family", "1", "--families", "lookup"]
    assert main(base) == 0 and json.loads(capsys.readouterr().out)["rework_reads"] is False
    assert main(base + ["--rework-reads"]) == 0 and json.loads(capsys.readouterr().out)["rework_reads"] is True


def test_then_live_takes_one_switch_to_arm_it(tmp_path: Path, monkeypatch, capsys):
    tape = tmp_path / "t.jsonl"
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "claude-haiku-5-5", "effort": "low",
                                "compare": {}}) + "\n")
    base = ["compare", "--adapter", "anthropic", "--replay", str(tape), "--record", str(tmp_path / "l.jsonl"),
            "--then-live", "--out", str(tmp_path / "o.json"), "--per-family", "1", "--families", "lookup"]
    for extra in ([], ["--gap-check", "--rework-reads"], ["--rework-reads", "--rework-keeps"], ["--rework-keeps", "--fixed-quotes"]):
        assert main(base + extra) != 0
        assert "one of --gap-check, --rework-reads, --rework-keeps, --fixed-quotes or --marked-review" in capsys.readouterr().out
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "claude-sonnet-5-5")
    monkeypatch.setenv("TASKORG_MODEL_EFFORT", "low")
    # Past the switch check, to the next: the tape's model is not the environment's.
    assert main(base + ["--rework-reads"]) != 0 and "model and effort" in capsys.readouterr().out
    assert not (tmp_path / "l.jsonl").exists() and not (tmp_path / "o.json").exists()


class Endpoint:
    max_reply_param = None

    def __init__(self):
        self.sent, self.last_usage = [], {}

    def _post(self, payload):
        self.sent.append(payload)
        self.last_usage = {"prompt_tokens": 1_000, "completion_tokens": 100}
        return "live reply"


def _payload(text):
    return {"system": "s", "messages": [{"role": "user", "content": text}]}


def test_a_replay_goes_live_at_a_rework_that_may_read_and_not_before(tmp_path: Path):
    recorded = _payload("recorded request")
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m"}) + "\n" + json.dumps(
        {"key": request_key(recorded, None), "request": recorded, "reply": "recorded reply",
         "usage": {"prompt_tokens": 5, "completion_tokens": 5}, "error": None}) + "\n")
    spend = LiveSpend()
    tape = Continuing(Player(path), Recorder(tmp_path / "live.jsonl", {"adapter": "anthropic"}), REWORK_ARM, spend)
    adapter = Endpoint()
    assert tape.exchange(adapter, recorded) == "recorded reply" and adapter.sent == []
    with pytest.raises(InvariantError, match="replay"):  # off the tape for another reason: nothing is spent
        Continuing(Player(path), Recorder(tmp_path / "x.jsonl", {}), REWORK_ARM, LiveSpend()).exchange(
            adapter, _payload(f"{REWORK_HEAD}It said: {FAILED} Misses: none named. Last product: x"))
    armed = _payload(f"{REWORK_HEAD}It said: {FAILED} Misses: none named.{REWORK_READS} Last product: x")
    assert tape.exchange(adapter, armed) == "live reply" and tape.armed and spend.calls == 1


def test_compare_hands_the_switch_to_every_trial(tmp_path: Path, monkeypatch):
    seen = []
    first = Engine.__init__

    def spy(self, *a, **k):
        seen.append(k.get("rework_reads"))
        first(self, *a, **k)

    monkeypatch.setattr(Engine, "__init__", spy)
    base = ["compare", "--per-family", "1", "--families", "lookup", "--strategies", "single,genet"]
    assert main(base + ["--out", str(tmp_path / "off.json")]) == 0 and seen and set(seen) == {False}
    seen.clear()
    assert main(base + ["--out", str(tmp_path / "on.json"), "--rework-reads"]) == 0 and seen and set(seen) == {True}


class _Haiku:
    """What then-live asks of the live adapter before any call: who it is, and its tape header."""

    name, model, effort, models, round_reply_tokens, tape = "anthropic", "claude-haiku-5-5", "low", {}, 0, None

    def tape_header(self):
        return {"adapter": self.name, "model": self.model, "effort": self.effort}


@pytest.mark.parametrize("switch,arm", [("gap_check", GAP_ARM), ("rework_reads", REWORK_ARM), ("rework_keeps", KEEP_ARM)])
def test_then_live_arms_on_the_words_of_the_switch_it_measures(tmp_path: Path, monkeypatch, switch, arm):
    from taskorg import cli

    tape = tmp_path / "t.jsonl"
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "claude-haiku-5-5", "effort": "low",
                                "compare": {}}) + "\n")
    monkeypatch.setattr(cli, "pick_adapter", lambda name: _Haiku())
    args = argparse.Namespace(replay=str(tape), record=str(tmp_path / "l.jsonl"), adapter="anthropic",
                              gap_check=switch == "gap_check", rework_reads=switch == "rework_reads",
                              rework_keeps=switch == "rework_keeps")
    factory, _, recorder = cli._continuing_source(args, {}, "compare", "COMPARE")
    try:
        assert factory().tape.arm == arm
    finally:
        recorder.close()
