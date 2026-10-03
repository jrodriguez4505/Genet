from pathlib import Path

import pytest

from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.live import ScriptedLive
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.persist import load_run


def test_peer_handoff_does_not_merge_roster_or_context(tmp_path: Path):
    store = MemoryStore(tmp_path)
    a = new_run("peer-a", "Write part A", "Cover part A", "Part A done")
    b = new_run("peer-b", "Write part B", "Cover part B", "Part B done")
    who_a = [s.id for s in a.state.slots]
    where_b = b.state.context
    Engine(store).handoff_peer(a, b, "part A is done; part B is yours")
    assert [s.id for s in a.state.slots] == who_a
    assert [s.id for s in b.state.slots] == who_a
    assert b.state.context == where_b
    assert any(d.stream == "peer" and "peer-in" in d.evidence for d in b.deltas)
    assert any(d.stream == "peer" and "peer-stream" in d.evidence for d in a.deltas)


def test_verifier_fail_blocks_complete(tmp_path: Path):
    replies = [
        '{"claim":"standing text","evidence":["context"],"uncertainty":"x","channel_id":"lead-merge","context_update":"d","requests":[]}',
        '{"claim":"PASS","evidence":["nothing relevant"],"uncertainty":"x","channel_id":"verify","context_update":"d","requests":[]}',
    ]
    store = MemoryStore(tmp_path)
    m = new_run("vf-1", "Write the report", "Keep the context", "Report written")
    with pytest.raises(InvariantError) as e:
        Engine(store, adapter=ScriptedLive(replies)).run_single(
            m, context="enough", operator_question="one?"
        )
    assert e.value.code in ("INV-5", "SCHEMA", "BUDGET")
    assert m.last_verify and m.last_verify["score"] < 1


def test_board_command(tmp_path: Path, capsys):
    out = tmp_path / "b.json"
    assert main([
        "brief",
        "--goal", "Write the report",
        "--purpose", "Keep the context",
        "--context", "enough",
        "--store", str(tmp_path),
        "--out", str(out),
        "--id", "board-1",
    ]) == 0
    capsys.readouterr()
    assert main(["board", str(out)]) == 0
    text = capsys.readouterr().out
    assert "health" in text
    assert "workers" in text
    m = load_run(out)
    assert m.status.value == "complete"
