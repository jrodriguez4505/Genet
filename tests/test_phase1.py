from pathlib import Path

from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.persist import load_mission, save_mission


def test_standing_order_loop(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.write_doctrine("standing", "Slide before split. Look before spawn.")
    m = element_at_rest(
        "p1-001",
        "Complete the default task",
        "Shared picture",
        "Task recorded",
    )
    result = Engine(store).run_standing_order(
        m,
        look_update="Primary path blocked. Second source is open.",
        operator_why="Why not start middle-out?",
        head_response="KEEP_ROSTER",
        head_reason="One slot can write this order",
    )
    assert result.verified is True
    assert result.product is not None
    assert result.why_question.startswith("Why not")
    assert result.why_response == "KEEP_ROSTER"
    assert m.status.value == "complete"
    assert m.summary()["could_this_have_been_one"] is True
    assert m.summary()["looked_through_door"] is True
    assert m.picture.slot("head-1").skill == "draft"
    assert m.picture.worker_count() == 0
    assert "why-1" in m.notes
    assert m.notes["why-1"].status.value == "closed"
    assert store.working_facts("p1-001")["look"].startswith("Primary path")
    episode = tmp_path / "episodic" / "p1-001.json"
    assert episode.exists()


def test_replay_from_disk(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("p1-replay", "Complete the default task", "Shared picture", "Task recorded")
    Engine(store).run_standing_order(
        m,
        look_update="Enough picture",
        operator_why="Is one slot enough?",
        head_reason="yes",
    )
    path = tmp_path / "missions" / "p1-replay.json"
    save_mission(m, path)
    loaded = load_mission(path)
    assert loaded.status.value == "complete"
    assert loaded.notes["why-1"].response == "KEEP_ROSTER"
    assert loaded.summary()["could_this_have_been_one"] is True
    assert any(e.event == "look" for e in loaded.log)
    assert any(e.event == "slide" for e in loaded.log)
    assert any(e.event == "complete" for e in loaded.log)


def test_scoped_brief_does_not_include_other_missions(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.write_doctrine("d", "no dump")
    store.remember_working("alpha", "secret", "do not leak")
    store.remember_working("beta", "ok", "beta only")
    packet = store.scoped_brief("beta")
    assert "beta only" in packet
    assert "do not leak" not in packet
