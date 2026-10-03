from pathlib import Path

from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.factory import new_run
from taskorg.gates import Subtask
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_diagnose_single_agent(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("dx-1", "Write the report", "Keep the context", "Report written")
    Engine(store).run_single(m, context="enough", operator_question="one?")
    report = diagnose(m)
    assert report["health"] == "ok"
    assert report["run"]["could_this_have_been_one"] is True
    assert "context" in report["phases_seen"]
    assert "complete" in report["phases_seen"]
    assert any(i["kind"] == "review" for i in report["interactions"])
    assert report["run"]["duration_s"] >= 0
    assert report["performance"]["calls"] >= 2
    assert report["performance"]["tokens"] > 0
    assert report["tier"]["name"] == "open"
    assert report["tier"]["armed"] is True


def test_diagnose_split_has_merge_net(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("dx-2", "Summarize the notes", "Keep sources apart", "Summary written")
    Engine(store).run_fanout(
        m,
        context="two subtasks",
        subtasks=[Subtask("source-a", "source-a"), Subtask("source-b", "source-b")],
        axes=["sequential", "fan_in"],
        operator_question="method?",
    )
    report = diagnose(m)
    assert report["run"]["workers"] == 2
    assert report["streams"]["delta_counts"].get("merge", 0) >= 2
    assert "split" in report["phases_seen"]
    assert report["health"] == "ok"
    assert report["performance"]["calls"] >= 2
    assert report["isolation"]["pairs"]
    assert not report["isolation"]["flags"]


def test_isolation_detects_sibling_packet():
    m = new_run("dx-leak", "Summarize the notes", "Keep sources apart", "Summary written")
    m.calls = [
        {"function": "worker", "channel": "source-a", "packet": "clean"},
        {"function": "worker", "channel": "source-b", "packet": "see channel:source-a leaked"},
    ]
    from taskorg.diagnostics import diagnose

    report = diagnose(m)
    assert report["isolation"]["flags"]
    assert report["health"] == "degraded"


def test_diagnose_names_tight_tier(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("dx-tight", "Write the report", "Keep the context", "Report written")
    Engine(store, budget=Budget.for_tier("tight")).run_single(
        m, context="enough", operator_question="one?"
    )
    report = diagnose(m)
    assert report["tier"]["name"] == "tight"
    assert report["tier"]["allow_split"] is False
    assert report["health"] == "ok"
