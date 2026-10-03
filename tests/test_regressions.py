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
from taskorg.factory import element_at_rest
from taskorg.finetune import parse_action_json
from taskorg.gates import Seam, World, decide
from taskorg.live import LiveAdapter
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, Slot
from taskorg.persist import load_mission, save_mission
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
            art.delta_to_picture = f"SECRET-{brief.channel_id}"
        return art


# --- README commands work with their defaults ---


def test_cli_split_defaults_complete(tmp_path: Path, capsys):
    out = tmp_path / "fanout.json"
    rc = main([
        "split", "--pace", "run", "--store", str(tmp_path), "--out", str(out),
        "--look", "seam:source-a=independent_a seam:source-b=independent_b",
    ])
    assert rc == 0, capsys.readouterr().out
    assert load_mission(out).status.value == "complete"


def test_cli_adapt_defaults_complete(tmp_path: Path, capsys):
    out = tmp_path / "walk.json"
    rc = main(["adapt", "--pace", "walk", "--store", str(tmp_path), "--out", str(out)])
    assert rc == 0, capsys.readouterr().out
    assert load_mission(out).status.value == "complete"


def test_failed_run_is_saved_as_abort_not_active(tmp_path: Path, capsys):
    out = tmp_path / "bad.json"
    rc = main(["adapt", "--pace", "walk", "--axes", "sideways", "--store", str(tmp_path), "--out", str(out)])
    assert rc == 1
    m = load_mission(out)
    assert m.status.value == "abort"
    assert "unknown axis" in m.stop_reason


# --- Worker isolation ---


def test_worker_brief_never_carries_sibling_product(tmp_path: Path):
    spy = SpyAdapter()
    m = element_at_rest("iso-1", "Answer two notes", "Do not mix", "Integrated")
    Engine(MemoryStore(tmp_path), adapter=spy, budget=Budget.for_pace("run")).run_multi_axis(
        m, look_update="two notes", seams=[Seam("source-a", "x"), Seam("source-b", "y")],
        axes=["fan_in"], operator_why="?",
    )
    b_brief = next(b for b in spy.briefs if b.channel_id == "source-b")
    assert "SECRET-source-a" not in b_brief.picture
    assert "SECRET-source-a" not in b_brief.packet
    assert diagnose(m)["isolation"]["flags"] == []
    # The lead still integrates both.
    assert "SECRET-source-a" in m.picture.current_picture
    assert "SECRET-source-b" in m.picture.current_picture


def test_leak_through_picture_is_flagged(tmp_path: Path):
    m = element_at_rest("iso-2", "E", "P", "S")
    engine = Engine(MemoryStore(tmp_path), adapter=SpyAdapter(), budget=Budget.for_pace("run"))
    engine._arm(m)
    a = Slot(id="w-a", function="worker", channel_id="a")
    b = Slot(id="w-b", function="worker", channel_id="b")
    m.write_who("head-1", m.picture.slots + [a], gates=_gates("a"))
    m.write_who("head-1", m.picture.slots + [b], gates=_gates("b"))
    art = engine._act(m, engine._brief(m, "worker", slot=a), slot=a)
    art.channel_id = "a"
    m.accept_artifact(art)  # merges SECRET-a into the living picture
    engine._act(m, engine._brief(m, "worker", slot=b), slot=b)  # living picture, not the split snapshot
    assert "isolation_leak:a->b" in diagnose(m)["flags"]


def test_isolation_verdict_survives_disk(tmp_path: Path):
    m = element_at_rest("iso-3", "E", "P", "S")
    m.calls = [
        {"function": "worker", "channel": "a", "heard_channels": []},
        {"function": "worker", "channel": "b", "heard_channels": ["a"]},
    ]
    path = save_mission(m, tmp_path / "iso.json")
    assert "packet" not in json.loads(path.read_text())["calls"][0]
    assert "isolation_leak:a->b" in diagnose(load_mission(path))["flags"]


def test_old_board_without_evidence_is_unverified(tmp_path: Path):
    m = element_at_rest("iso-4", "E", "P", "S")
    m.calls = [{"function": "worker", "channel": "a"}, {"function": "worker", "channel": "b"}]
    assert "isolation_unverified" in diagnose(m)["flags"]


# --- No hidden code loading ---


def test_cli_does_not_touch_sys_path():
    src = inspect.getsource(cli_mod)
    assert "sys.path" not in src
    assert "ecphory" not in src


# --- Working memory starts clean ---


def test_reused_mission_id_starts_clean(tmp_path: Path, capsys):
    store = MemoryStore(tmp_path)
    store.remember_working("so-001", "channel:source-a", "OLD RUN PRODUCT")
    rc = main(["run", "--id", "so-001", "--store", str(tmp_path), "--out", str(tmp_path / "so.json"), "--look", "enough"])
    assert rc == 0
    assert "channel:source-a" not in store.working_facts("so-001")


def test_unsafe_mission_id_refused(tmp_path: Path):
    with pytest.raises(InvariantError) as e:
        MemoryStore(tmp_path).remember_working("../escape", "k", "v")
    assert e.value.code == "STORE"


def test_cli_keeps_operator_doctrine(tmp_path: Path, capsys):
    store = MemoryStore(tmp_path)
    store.write_doctrine("standing", "operator doctrine")
    main(["run", "--store", str(tmp_path), "--out", str(tmp_path / "so.json"), "--look", "enough"])
    assert store.read_doctrine("standing").strip() == "operator doctrine"


# --- World matching ---


def test_world_file_must_name_the_channel():
    assert decide([Seam("a", "need")], world=World(existing_files=["data/report.md"])) is not None
    assert decide([Seam("a", "need")], world=World(existing_files=["out/a.md"])) is None


# --- write_who ---


def test_refused_write_who_leaves_no_split_event():
    m = element_at_rest("ww-1", "E", "P", "S")
    no_head = [s for s in m.picture.slots if s.function != "head"]
    with pytest.raises(InvariantError) as e:
        m.write_who("head-1", no_head + [Slot(id="w-c", function="worker", channel_id="c")], gates=_gates("c"))
    assert e.value.code == "WHO"
    assert not any(ev.event == "split" for ev in m.log)


def test_retasking_a_worker_needs_gates():
    m = element_at_rest("ww-2", "E", "P", "S")
    m.write_who("head-1", m.picture.slots + [Slot(id="w-a", function="worker", channel_id="a")], gates=_gates("a"))
    moved = [s for s in m.picture.slots if s.id != "w-a"] + [Slot(id="w-a", function="worker", channel_id="other")]
    with pytest.raises(InvariantError) as e:
        m.write_who("head-1", moved)
    assert e.value.code == "INV-8"
    assert m.picture.slot("w-a").channel_id == "a"


def test_duplicate_slot_ids_refused():
    m = element_at_rest("ww-3", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        m.write_who("head-1", m.picture.slots + [Slot(id="memory-1", function="memory")])
    assert e.value.code == "WHO"


# --- Codes and budgets ---


class SpawnAsker(StubAdapter):
    def act(self, brief):
        art = super().act(brief)
        art.requests = ["spawn:another-worker"]
        return art


def test_tool_violation_reports_tools_code(tmp_path: Path):
    m = element_at_rest("tc-1", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=SpawnAsker()).run_standing_order(m, look_update="x", operator_why="?")
    assert e.value.code == "TOOLS"
    assert m.status.value == "abort"
    assert len(m.calls) == 1  # the offending call is on the record


def test_run_may_spend_its_whole_call_budget(tmp_path: Path):
    m = element_at_rest("bc-1", "E", "P", "S")
    Engine(MemoryStore(tmp_path), budget=Budget(max_calls=2)).run_standing_order(m, look_update="l", operator_why="?")
    assert m.status.value == "complete"
    assert len(m.calls) == 2


def test_run_may_not_exceed_its_call_budget(tmp_path: Path):
    m = element_at_rest("bc-2", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), budget=Budget(max_calls=1)).run_standing_order(m, look_update="l", operator_why="?")
    assert e.value.code == "BUDGET"
    assert len(m.calls) == 1


def test_aborted_mission_cannot_complete():
    m = element_at_rest("bc-3", "E", "P", "S")
    with pytest.raises(InvariantError):
        m.halt("operator kill switch")
    with pytest.raises(InvariantError):
        m.complete()
    assert m.status.value == "abort"


# --- Why notes ---


def test_defer_without_reason_leaves_note_untouched():
    m = element_at_rest("wn-1", "E", "P", "S")
    m.submit_why("later?", "n1")
    with pytest.raises(InvariantError) as e:
        m.respond_why("head-1", "n1", "DEFER", "")
    assert e.value.code == "INV-4"
    assert m.notes["n1"].response is None
    assert m.notes["n1"].status.value == "open"


def test_unknown_note_is_an_invariant_error():
    m = element_at_rest("wn-2", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        m.respond_why("head-1", "nope", "KEEP_ROSTER", "x")
    assert e.value.code == "WHY"


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
