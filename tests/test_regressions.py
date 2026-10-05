"""Regression tests for the October 2026 review. Each test failed before its fix."""

import inspect
import json
from pathlib import Path

import pytest

import taskorg.cli as cli_mod
from taskorg.adapters import StubAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.finetune import parse_action_json
from taskorg.gates import Subtask, World, decide
from taskorg.live import LiveAdapter
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, Slot
from taskorg.persist import load_run, save_run
from taskorg.policy import clamp


def _gates(channel: str) -> GateRecord:
    return GateRecord(False, True, "independent source", True, channel)


class SpyAdapter(StubAdapter):
    """Stub that remembers every brief and stamps worker deltas with a secret."""

    def __init__(self):
        self.briefs = []

    def act(self, brief):
        self.briefs.append(brief)
        art = super().act(brief)
        if brief.slot_function == "worker":
            art.context_update = f"SECRET-{brief.channel_id}"
        return art


# --- README commands work with their defaults ---


def test_cli_split_defaults_complete(tmp_path: Path, capsys):
    out = tmp_path / "fanout.json"
    rc = main([
        "fanout", "--tier", "open", "--store", str(tmp_path), "--out", str(out),
        "--context", "subtask:source-a=independent_a subtask:source-b=independent_b",
    ])
    assert rc == 0, capsys.readouterr().out
    assert load_run(out).status.value == "complete"


def test_cli_replan_defaults_complete(tmp_path: Path, capsys):
    out = tmp_path / "normal.json"
    rc = main(["replan", "--tier", "normal", "--store", str(tmp_path), "--out", str(out)])
    assert rc == 0, capsys.readouterr().out
    assert load_run(out).status.value == "complete"


def test_failed_run_is_saved_as_abort_not_active(tmp_path: Path, capsys):
    out = tmp_path / "bad.json"
    rc = main(["replan", "--tier", "normal", "--axes", "sideways", "--store", str(tmp_path), "--out", str(out)])
    assert rc == 1
    m = load_run(out)
    assert m.status.value == "abort"
    assert "unknown axis" in m.stop_reason


# --- Worker isolation ---


def test_worker_brief_never_carries_sibling_product(tmp_path: Path):
    spy = SpyAdapter()
    m = new_run("iso-1", "Answer two notes", "Do not mix", "Integrated")
    Engine(MemoryStore(tmp_path), adapter=spy, budget=Budget.for_tier("open")).run_fanout(
        m, context="two notes", subtasks=[Subtask("source-a", "x"), Subtask("source-b", "y")],
        axes=["fan_in"], operator_question="?",
    )
    b_brief = next(b for b in spy.briefs if b.channel_id == "source-b")
    assert "SECRET-source-a" not in b_brief.context
    assert "SECRET-source-a" not in b_brief.packet
    assert diagnose(m)["isolation"]["flags"] == []
    # The lead still integrates both.
    assert "SECRET-source-a" in m.state.context
    assert "SECRET-source-b" in m.state.context


def test_leak_through_context_is_flagged(tmp_path: Path):
    m = new_run("iso-2", "E", "P", "S")
    engine = Engine(MemoryStore(tmp_path), adapter=SpyAdapter(), budget=Budget.for_tier("open"))
    engine._arm(m)
    a = Slot(id="w-a", function="worker", channel_id="a")
    b = Slot(id="w-b", function="worker", channel_id="b")
    m.set_roster("lead-1", m.state.slots + [a], gates=_gates("a"))
    m.set_roster("lead-1", m.state.slots + [b], gates=_gates("b"))
    art = engine._act(m, engine._brief(m, "worker", slot=a), slot=a)
    art.channel_id = "a"
    m.accept_artifact(art)  # merges SECRET-a into the live context
    engine._act(m, engine._brief(m, "worker", slot=b), slot=b)  # live context, not the split-time snapshot
    assert "isolation_leak:a->b" in diagnose(m)["flags"]


def test_isolation_verdict_survives_disk(tmp_path: Path):
    m = new_run("iso-3", "E", "P", "S")
    m.calls = [
        {"function": "worker", "channel": "a", "heard_channels": []},
        {"function": "worker", "channel": "b", "heard_channels": ["a"]},
    ]
    path = save_run(m, tmp_path / "iso.json")
    assert "packet" not in json.loads(path.read_text())["calls"][0]
    assert "isolation_leak:a->b" in diagnose(load_run(path))["flags"]


def test_old_board_without_evidence_is_unverified(tmp_path: Path):
    m = new_run("iso-4", "E", "P", "S")
    m.calls = [{"function": "worker", "channel": "a"}, {"function": "worker", "channel": "b"}]
    assert "isolation_unverified" in diagnose(m)["flags"]


# --- No hidden code loading ---


def test_cli_does_not_touch_sys_path():
    src = inspect.getsource(cli_mod)
    assert "sys.path" not in src
    assert "ecphory" not in src


# --- Working memory starts clean ---


def test_reused_run_id_starts_clean(tmp_path: Path, capsys):
    store = MemoryStore(tmp_path)
    store.remember_working("single-001", "channel:source-a", "OLD RUN PRODUCT")
    rc = main(["single", "--id", "single-001", "--store", str(tmp_path), "--out", str(tmp_path / "so.json"), "--context", "enough"])
    assert rc == 0
    assert "channel:source-a" not in store.working_facts("single-001")


def test_unsafe_run_id_refused(tmp_path: Path):
    with pytest.raises(InvariantError) as e:
        MemoryStore(tmp_path).remember_working("../escape", "k", "v")
    assert e.value.code == "STORE"


def test_cli_keeps_operator_guidelines(tmp_path: Path, capsys):
    store = MemoryStore(tmp_path)
    store.write_guidelines("standing", "operator guidelines")
    main(["single", "--store", str(tmp_path), "--out", str(tmp_path / "so.json"), "--context", "enough"])
    assert store.read_guidelines("standing").strip() == "operator guidelines"


# --- World matching ---


def test_world_file_must_name_the_channel():
    assert decide([Subtask("a", "need")], world=World(existing_files=["data/report.md"])) is not None
    assert decide([Subtask("a", "need")], world=World(existing_files=["out/a.md"])) is None


# --- set_roster ---


def test_refused_write_who_leaves_no_split_event():
    m = new_run("ww-1", "E", "P", "S")
    no_head = [s for s in m.state.slots if s.function != "lead"]
    with pytest.raises(InvariantError) as e:
        m.set_roster("lead-1", no_head + [Slot(id="w-c", function="worker", channel_id="c")], gates=_gates("c"))
    assert e.value.code == "ROSTER"
    assert not any(ev.event == "split" for ev in m.log)


def test_retasking_a_worker_needs_gates():
    m = new_run("ww-2", "E", "P", "S")
    m.set_roster("lead-1", m.state.slots + [Slot(id="w-a", function="worker", channel_id="a")], gates=_gates("a"))
    moved = [s for s in m.state.slots if s.id != "w-a"] + [Slot(id="w-a", function="worker", channel_id="other")]
    with pytest.raises(InvariantError) as e:
        m.set_roster("lead-1", moved)
    assert e.value.code == "INV-8"
    assert m.state.slot("w-a").channel_id == "a"


def test_duplicate_slot_ids_refused():
    m = new_run("ww-3", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        m.set_roster("lead-1", m.state.slots + [Slot(id="memory-1", function="memory")])
    assert e.value.code == "ROSTER"


# --- Codes and budgets ---


class SpawnAsker(StubAdapter):
    def act(self, brief):
        art = super().act(brief)
        art.requests = ["spawn:another-worker"]
        return art


def test_tool_violation_reports_tools_code(tmp_path: Path):
    m = new_run("tc-1", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=SpawnAsker()).run_single(m, context="x", operator_question="?")
    assert e.value.code == "TOOLS"
    assert m.status.value == "abort"
    assert len(m.calls) == 1  # the offending call is on the record


def test_run_may_spend_its_whole_call_budget(tmp_path: Path):
    m = new_run("bc-1", "E", "P", "S")
    Engine(MemoryStore(tmp_path), budget=Budget(max_calls=2)).run_single(m, context="l", operator_question="?")
    assert m.status.value == "complete"
    assert len(m.calls) == 2


def test_run_may_not_exceed_its_call_budget(tmp_path: Path):
    m = new_run("bc-2", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), budget=Budget(max_calls=1)).run_single(m, context="l", operator_question="?")
    assert e.value.code == "BUDGET"
    assert len(m.calls) == 1


def test_aborted_run_cannot_complete():
    m = new_run("bc-3", "E", "P", "S")
    with pytest.raises(InvariantError):
        m.halt("operator kill switch")
    with pytest.raises(InvariantError):
        m.complete()
    assert m.status.value == "abort"


# --- Why notes ---


def test_defer_without_reason_leaves_note_untouched():
    m = new_run("wn-1", "E", "P", "S")
    m.open_review("later?", "n1")
    with pytest.raises(InvariantError) as e:
        m.answer_review("lead-1", "n1", "DEFER", "")
    assert e.value.code == "INV-4"
    assert m.notes["n1"].response is None
    assert m.notes["n1"].status.value == "open"


def test_unknown_note_is_an_invariant_error():
    m = new_run("wn-2", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        m.answer_review("lead-1", "nope", "KEEP_ROSTER", "x")
    assert e.value.code == "REVIEW"


# --- Policy parsing ---


def test_zero_confidence_stays_zero_and_holds():
    dec = parse_action_json('{"action":"PROPOSE_CHANNEL","confidence":0,"channel_id":"x","named_failure":"y"}')
    assert dec.confidence == 0.0
    assert clamp(dec).action == "HOLD"


def test_bad_policy_json_is_schema():
    with pytest.raises(InvariantError) as e:
        parse_action_json('{"action": HOLD}')
    assert e.value.code == "SCHEMA"


# --- Live adapter configuration ---


def test_live_needs_a_model_name(monkeypatch):
    monkeypatch.setenv("TASKORG_MODEL_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("TASKORG_MODEL_KEY", "test-key")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "")
    with pytest.raises(InvariantError) as e:
        LiveAdapter.from_env()
    assert e.value.code == "LIVE"


def test_live_bad_timeout_is_live_error(monkeypatch):
    monkeypatch.setenv("TASKORG_MODEL_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("TASKORG_MODEL_KEY", "test-key")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "some-model")
    monkeypatch.setenv("TASKORG_MODEL_TIMEOUT", "soon")
    with pytest.raises(InvariantError) as e:
        LiveAdapter.from_env()
    assert e.value.code == "LIVE"


# --- Gaps found by mutation testing: each rule below had no test that would fail without it ---


def test_gate_record_enforces_its_own_order():
    out_of_order = GateRecord(False, True, "x", True, "a", ("could_we", "should_we", "can_someone_else"))
    with pytest.raises(InvariantError) as e:
        out_of_order.assert_legal()
    assert e.value.code == "INV-9"


def test_reviewer_cannot_take_a_skill():
    m = new_run("mt-1", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        m.switch_skill("lead-1", "reviewer-1", "draft", "x")
    assert e.value.code == "INV-11"


class LateWriter(StubAdapter):
    """While the first sub-agent works, something updates the live context."""

    def __init__(self, run):
        self.run, self.briefs = run, []

    def act(self, brief):
        self.briefs.append(brief)
        if brief.slot_function == "worker" and brief.channel_id == "source-a":
            self.run.state.context += " | LATE-UPDATE"
        return super().act(brief)


def test_sub_agents_work_from_the_split_time_context(tmp_path: Path):
    m = new_run("mt-2", "E", "P", "S")
    spy = LateWriter(m)
    Engine(MemoryStore(tmp_path), adapter=spy, budget=Budget.for_tier("open"), parallel=False).run_fanout(
        m, context="two sources", subtasks=[Subtask("source-a", "x"), Subtask("source-b", "y")],
        axes=["fan_in"], operator_question="?",
    )
    b_brief = next(b for b in spy.briefs if b.channel_id == "source-b")
    assert "LATE-UPDATE" not in b_brief.context


def test_replan_needs_the_tier_not_just_the_budget(tmp_path: Path):
    from taskorg.live import ScriptedLive

    reply = lambda claim: json.dumps({"claim": claim, "evidence": [], "uncertainty": "", "channel_id": "x", "context_update": "", "requests": []})
    m = new_run("mt-3", "E", "P", "S")
    roomy_but_no_replan = Budget(max_calls=20, max_tokens=50_000, allow_split=False, allow_adapt=False, tier="tight")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=ScriptedLive([reply("Read: one agent."), reply("a draft"), reply("FAIL"), reply("unused")]),
               budget=roomy_but_no_replan).run_task(m, context="one source")
    assert "replan" not in m.notes
