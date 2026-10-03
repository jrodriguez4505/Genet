from pathlib import Path

from taskorg.diagnostics import diagnose
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact


def test_diagnose_roster_and_adapter(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("ld-1", "Write the report", "Keep the context", "Report written")
    Engine(store).run_single(m, context="enough", operator_question="one?")
    report = diagnose(m)
    assert report["roster"]["unchanged"] is True
    assert report["authority"]["hits"] == []
    assert report["adapter"] == "stub"
    assert report["health"] == "ok"


def test_authority_language_flags():
    m = new_run("ld-2", "Write the report", "Keep the context", "Report written")
    m.artifacts.append(
        Artifact(
            claim="I should set_roster and spawn a worker",
            evidence=["none"],
            uncertainty="n",
            channel_id="lead-merge",
            context_update="x",
        )
    )
    report = diagnose(m)
    assert report["authority"]["hits"]
    assert report["health"] == "degraded"
