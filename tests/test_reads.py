from pathlib import Path

from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.reads import attach_reads


def test_read_lands_in_brief_and_does_not_spawn(tmp_path: Path):
    src = tmp_path / "live_proof.txt"
    src.write_text("TOKEN_QZ7 live proof table tight-live-4 PASS")
    store = MemoryStore(tmp_path)
    m = new_run("rd-1", "Write five lines", "Trustable record", "Five lines")
    attach_reads(store, m, [str(src)])
    packet = store.scoped_brief(m.id, extra="use the file")
    assert "TOKEN_QZ7" in packet
    result = Engine(store).run_single(m, context="one file holds everything needed", operator_question="one?")
    assert result.run.state.worker_count() == 0
    assert result.run.status.value == "complete"
