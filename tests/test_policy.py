from pathlib import Path

import inspect

from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import World
from taskorg.memory_store import MemoryStore
from taskorg.policy import (
    ACTIONS,
    FEATURE_NAMES,
    PolicyDecision,
    StubPolicy,
    apply_decision,
    clamp,
    encode_board,
    replay_log,
)
import taskorg.policy as policy_mod


def test_policy_source_has_no_write_who():
    src = inspect.getsource(policy_mod)
    assert ".set_roster(" not in src
    assert "set_roster(" not in src
    assert "SPAWN" not in ACTIONS


def test_unknown_action_is_schema():
    try:
        PolicyDecision("SPAWN")
    except InvariantError as e:
        assert e.code == "SCHEMA"
    else:
        raise AssertionError("SPAWN must be illegal")


def test_encode_feature_order():
    m = new_run("p1", "Write a note", "Do not redo work", "Note on disk")
    m.attach_budget(Budget.for_tier("tight"))
    state = encode_board(m)
    assert list(state.features) == list(FEATURE_NAMES)
    assert len(state.vector) == len(FEATURE_NAMES)
    assert state.get("worker_count") == 0.0
    assert state.get("status_active") == 1.0


def test_stub_inspects_when_context_thin():
    m = new_run("p2", "task", "purpose", "done")
    m.state.context_sufficient = False
    dec = StubPolicy().act(encode_board(m))
    assert dec.action == "INSPECT"


def test_stub_holds_when_file_already_exists():
    m = new_run("p3", "Write two notes", "Do not redo work", "Only the open note")
    m.attach_budget(Budget.for_tier("tight"))
    m.world = World(existing_files=["note-a.txt"], existing_channels=["source-a"])
    m.state.context_sufficient = True
    dec = StubPolicy().act(encode_board(m))
    assert dec.action == "HOLD"
    assert dec.rationale_id == "exists-hold"


def test_low_confidence_becomes_hold():
    raw = PolicyDecision("PROPOSE_CHANNEL", confidence=0.1, channel_id="x", named_failure="open")
    assert clamp(raw).action == "HOLD"


def test_apply_propose_does_not_grow_roster(tmp_path: Path):
    m = new_run("p4", "task", "purpose", "done")
    m.attach_budget(Budget.for_tier("open"))
    m.world = World(existing_files=["source-a.json"], existing_channels=["source-a"])
    before = [s.id for s in m.state.slots]
    result = apply_decision(
        m,
        PolicyDecision("PROPOSE_CHANNEL", channel_id="source-a", named_failure="already filed"),
    )
    assert result == "someone-else"
    assert [s.id for s in m.state.slots] == before
    assert m.state.worker_count() == 0


def test_apply_legal_channel_still_unwritten():
    m = new_run("p5", "task", "purpose", "done")
    m.attach_budget(Budget.for_tier("open"))
    result = apply_decision(
        m,
        PolicyDecision("PROPOSE_CHANNEL", channel_id="source-b", named_failure="note B still open"),
    )
    assert result == "legal-unwritten"
    assert m.state.worker_count() == 0


def test_replay_maps_events():
    pairs = replay_log([
        {"event": "context", "detail": {}},
        {"event": "switch_skill", "detail": {}},
        {"event": "set_roster", "detail": {}},
        {"event": "review_answer", "detail": {"response": "KEEP_ROSTER"}},
        {"event": "complete", "detail": {}},
    ])
    assert [p["action"] for p in pairs] == [
        "INSPECT",
        "ACTIVATE_SKILL",
        "PROPOSE_CHANNEL",
        "HOLD",
        "STOP",
    ]


def test_engine_still_green_with_policy_import(tmp_path: Path):
    from taskorg.loop import Engine

    store = MemoryStore(tmp_path)
    store.write_guidelines("standing", "one agent first")
    m = new_run("p6", "Complete the default task", "Keep purpose", "Done")
    result = Engine(store, budget=Budget.for_tier("tight")).run_single(
        m,
        context="One source. The context is enough.",
        operator_question="Could a single agent have done this?",
    )
    assert result.run.status.value == "complete"
    assert result.run.state.worker_count() == 0
