from pathlib import Path

from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.factory import element_at_rest
from taskorg.gates import Seam
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_diagnose_standing_order(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("dx-1", "Issue order", "Picture", "Issued")
    Engine(store).run_standing_order(m, look_update="enough", operator_why="one?")
    report = diagnose(m)
    assert report["health"] == "ok"
    assert report["mission"]["could_this_have_been_one"] is True
    assert "look" in report["phases_seen"]
    assert "complete" in report["phases_seen"]
    assert any(i["kind"] == "up" for i in report["interactions"])
    assert report["mission"]["duration_s"] >= 0
    assert report["performance"]["calls"] >= 2
    assert report["performance"]["tokens"] > 0
    assert report["pace"]["name"] == "run"
    assert report["pace"]["armed"] is True


def test_diagnose_split_has_element_net(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("dx-2", "Clear", "Deny", "Held")
    Engine(store).run_multi_axis(
        m,
        look_update="two seams",
        seams=[Seam("source-a", "source-a"), Seam("source-b", "rear")],
        axes=["sequential", "fan_in"],
        operator_why="vector?",
    )
    report = diagnose(m)
    assert report["mission"]["workers"] == 2
    assert report["nets"]["delta_counts"].get("element", 0) >= 2
    assert "split" in report["phases_seen"]
    assert report["health"] == "ok"
    assert report["performance"]["calls"] >= 2
    assert report["isolation"]["pairs"]
    assert not report["isolation"]["flags"]


def test_isolation_detects_sibling_packet():
    m = element_at_rest("dx-leak", "Clear", "Deny", "Held")
    m.calls = [
        {"function": "worker", "channel": "source-a", "packet": "clean"},
        {"function": "worker", "channel": "source-b", "packet": "see channel:source-a leaked"},
    ]
    from taskorg.diagnostics import diagnose

    report = diagnose(m)
    assert report["isolation"]["flags"]
    assert report["health"] == "degraded"


def test_diagnose_names_crawl_pace(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("dx-crawl", "Issue order", "Picture", "Issued")
    Engine(store, budget=Budget.for_pace("crawl")).run_standing_order(
        m, look_update="enough", operator_why="one?"
    )
    report = diagnose(m)
    assert report["pace"]["name"] == "crawl"
    assert report["pace"]["allow_split"] is False
    assert report["health"] == "ok"
