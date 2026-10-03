from pathlib import Path

from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.persist import load_run, save_run


def test_single_agent_loop(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.write_guidelines("standing", "Switch skills before splitting. Check the context before starting a sub-agent.")
    m = new_run(
        "p1-001",
        "Complete the default task",
        "Shared context",
        "Task recorded",
    )
    result = Engine(store).run_single(
        m,
        context="Primary path blocked. Second source is open.",
        operator_question="Why not start from the middle?",
        lead_response="KEEP_ROSTER",
        lead_reason="One slot can write this report",
    )
    assert result.verified is True
    assert result.product is not None
    assert result.operator_question.startswith("Why not")
    assert result.lead_answer == "KEEP_ROSTER"
    assert m.status.value == "complete"
    assert m.summary()["could_this_have_been_one"] is True
    assert m.summary()["context_checked"] is True
    assert m.state.slot("lead-1").skill == "draft"
    assert m.state.worker_count() == 0
    assert "question-1" in m.notes
    assert m.notes["question-1"].status.value == "closed"
    assert store.working_facts("p1-001")["context"].startswith("Primary path")
    episode = tmp_path / "episodic" / "p1-001.json"
    assert episode.exists()


def test_replay_from_disk(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("p1-replay", "Complete the default task", "Shared context", "Task recorded")
    Engine(store).run_single(
        m,
        context="Context is enough",
        operator_question="Is one slot enough?",
        lead_reason="yes",
    )
    path = tmp_path / "runs" / "p1-replay.json"
    save_run(m, path)
    loaded = load_run(path)
    assert loaded.status.value == "complete"
    assert loaded.notes["question-1"].response == "KEEP_ROSTER"
    assert loaded.summary()["could_this_have_been_one"] is True
    assert any(e.event == "context" for e in loaded.log)
    assert any(e.event == "switch_skill" for e in loaded.log)
    assert any(e.event == "complete" for e in loaded.log)


def test_scoped_brief_does_not_include_other_runs(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.write_guidelines("d", "no dump")
    store.remember_working("alpha", "secret", "do not leak")
    store.remember_working("beta", "ok", "beta only")
    packet = store.scoped_brief("beta")
    assert "beta only" in packet
    assert "do not leak" not in packet
