from pathlib import Path

from taskorg.diagnostics import diagnose
from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact


def test_diagnose_who_and_adapter(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("ld-1", "Issue order", "Picture", "Issued")
    Engine(store).run_standing_order(m, look_update="enough", operator_why="one?")
    report = diagnose(m)
    assert report["who"]["unchanged"] is True
    assert report["authority"]["hits"] == []
    assert report["adapter"] == "stub"
    assert report["health"] == "ok"


def test_authority_language_flags():
    m = element_at_rest("ld-2", "Issue order", "Picture", "Issued")
    m.artifacts.append(
        Artifact(
            claim="I should write_who and spawn a worker",
            evidence=["none"],
            uncertainty="n",
            channel_id="head-integrate",
            delta_to_picture="x",
        )
    )
    report = diagnose(m)
    assert report["authority"]["hits"]
    assert report["health"] == "degraded"
