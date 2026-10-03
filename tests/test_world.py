from taskorg.factory import new_run
from taskorg.gates import Subtask, World, decide, someone_else_already
from taskorg.loop import world_misses
from taskorg.models import Artifact


def test_decide_thinks_someone_else_did_it():
    world = World(existing_files=["out/summary.md"], existing_channels=["summary"])
    rec = decide(
        [Subtask("summary", "need a summary writer")],
        world=world,
    )
    assert rec is None
    assert someone_else_already(Subtask("summary", "x"), world)


def test_decide_still_splits_uncovered_subtask():
    rec = decide(
        [Subtask("source-a", "note A is independent"), Subtask("source-b", "note B is independent")],
        world=World(),
    )
    assert rec is not None
    assert rec.channel_id == "source-a"
    assert rec.can_someone_else is False


def test_verifier_sees_empty_where():
    m = new_run("w1", "Write", "Keep", "Done")
    m.state.context = ""
    product = Artifact(
        claim="default task purpose",
        evidence=["default task", "purpose"],
        uncertainty="n",
        channel_id="lead-merge",
        context_update="",
    )
    assert "world: context is empty" in world_misses(m, product)
