from pathlib import Path

from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.reads import attach_reads


def test_read_lands_in_brief_and_does_not_spawn(tmp_path: Path):
    src = tmp_path / "live_proof.txt"
    src.write_text("TOKEN_QZ7 live proof table crawl-live-4 PASS")
    store = MemoryStore(tmp_path)
    m = element_at_rest("rd-1", "Write five lines", "Trustable record", "Five lines")
    attach_reads(store, m, [str(src)])
    packet = store.scoped_brief(m.id, extra="use the file")
    assert "TOKEN_QZ7" in packet
    result = Engine(store).run_standing_order(m, look_update="one file is the picture", operator_why="one?")
    assert result.mission.picture.worker_count() == 0
    assert result.mission.status.value == "complete"
