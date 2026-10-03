from pathlib import Path

import pytest

from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.live import ScriptedLive
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.persist import load_mission


def test_peer_handoff_does_not_merge_who_or_where(tmp_path: Path):
    store = MemoryStore(tmp_path)
    a = element_at_rest("peer-a", "Hold west", "Deny west", "West held")
    b = element_at_rest("peer-b", "Hold east", "Deny east", "East held")
    who_a = [s.id for s in a.picture.slots]
    where_b = b.picture.current_picture
    Engine(store).handoff_adjacent(a, b, "west is set, you own east")
    assert [s.id for s in a.picture.slots] == who_a
    assert [s.id for s in b.picture.slots] == who_a
    assert b.picture.current_picture == where_b
    assert any(d.net == "adjacent" and "adjacent-in" in d.evidence for d in b.deltas)
    assert any(d.net == "adjacent" and "adjacent-net" in d.evidence for d in a.deltas)


def test_verifier_fail_blocks_complete(tmp_path: Path):
    replies = [
        '{"claim":"standing text","evidence":["look"],"uncertainty":"x","channel_id":"head-integrate","delta_to_picture":"d","requests":[]}',
        '{"claim":"PASS","evidence":["nothing relevant"],"uncertainty":"x","channel_id":"verify","delta_to_picture":"d","requests":[]}',
    ]
    store = MemoryStore(tmp_path)
    m = element_at_rest("vf-1", "Issue order", "Picture", "Issued")
    with pytest.raises(InvariantError) as e:
        Engine(store, adapter=ScriptedLive(replies)).run_standing_order(
            m, look_update="enough", operator_why="one?"
        )
    assert e.value.code in ("INV-5", "SCHEMA", "BUDGET")
    assert m.last_verify and m.last_verify["score"] < 1


def test_board_command(tmp_path: Path, capsys):
    out = tmp_path / "b.json"
    assert main([
        "brief",
        "--effect", "Issue the order",
        "--purpose", "Hold the picture",
        "--look", "enough",
        "--store", str(tmp_path),
        "--out", str(out),
        "--id", "board-1",
    ]) == 0
    capsys.readouterr()
    assert main(["board", str(out)]) == 0
    text = capsys.readouterr().out
    assert "health" in text
    assert "workers" in text
    m = load_mission(out)
    assert m.status.value == "complete"
