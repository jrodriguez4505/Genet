from pathlib import Path

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.gates import Seam, decide
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_no_seams_means_no_split():
    assert decide([Seam("source-a", "x", covered_by_existing=True)]) is None


def test_uncovered_seam_passes_gates():
    rec = decide([Seam("source-b", "independent source-b channel")])
    assert rec is not None
    assert rec.channel_id == "source-b"
    assert rec.order[0] == "can_someone_else"


def test_multi_axis_isolated_channels(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("p2-split", "Complete the task", "Keep the goal intact", "Task finished")
    result = Engine(store).run_multi_axis(
        m,
        look_update="Primary path blocked. Two sources are independent.",
        seams=[
            Seam("source-a", "independent source-a channel"),
            Seam("source-b", "independent source-b channel"),
        ],
        axes=["parallel", "reverse", "fan_in"],
        operator_why="Why keep a single worker at all?",
    )
    assert result.split is True
    assert result.channels == ["source-a", "source-b"]
    assert m.picture.worker_count() == 2
    assert m.summary()["could_this_have_been_one"] is False
    worker_arts = [a for a in m.artifacts if a.channel_id in ("source-a", "source-b")]
    assert {a.channel_id for a in worker_arts} == {"source-a", "source-b"}
    assert any("source-a" in a.claim for a in worker_arts)
    assert any("source-b" in a.claim for a in worker_arts)
    assert "conflict-" + m.id in m.cues
    assert m.status.value == "complete"
    assert "fan_in" in m.picture.axes


def test_look_without_seams_stays_one(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("p2-one", "Write the order", "Shared picture", "Task recorded")
    result = Engine(store).run_multi_axis(
        m,
        look_update="One room. No second seam.",
        seams=[Seam("only", "none", covered_by_existing=True)],
        axes=["parallel"],
        operator_why="Could this have been one?",
        head_response="KEEP_ROSTER",
        head_reason="yes",
    )
    assert result.split is False
    assert m.picture.worker_count() == 0
    assert m.summary()["could_this_have_been_one"] is True


def test_split_still_cannot_skip_look_recon_rule(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("p2-recon", "Clear", "Deny", "Held")
    m.update_context("head-1", "already see far side")
    from taskorg.models import GateRecord, Slot

    rec = GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure="need eyes",
        could_we=True,
        channel_id="recon",
    )
    with pytest.raises(InvariantError) as e:
        m.request_recon_spawn(
            "head-1",
            Slot(id="w-recon", function="worker", skill="observe", channel_id="recon"),
            rec,
        )
    assert e.value.code == "INV-10"
