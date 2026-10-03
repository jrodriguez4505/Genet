from taskorg.factory import element_at_rest
from taskorg.gates import Seam, World, decide, someone_else_already
from taskorg.loop import world_misses
from taskorg.models import Artifact


def test_decide_thinks_someone_else_did_it():
    world = World(existing_files=["out/summary.md"], existing_channels=["summary"])
    rec = decide(
        [Seam("summary", "need a summary writer")],
        world=world,
    )
    assert rec is None
    assert someone_else_already(Seam("summary", "x"), world)


def test_decide_still_splits_uncovered_seam():
    rec = decide(
        [Seam("source-a", "note A is independent"), Seam("source-b", "note B is independent")],
        world=World(),
    )
    assert rec is not None
    assert rec.channel_id == "source-a"
    assert rec.can_someone_else is False


def test_verifier_sees_empty_where():
    m = element_at_rest("w1", "Write", "Hold", "Done")
    m.picture.current_picture = ""
    product = Artifact(
        claim="default task purpose",
        evidence=["default task", "purpose"],
        uncertainty="n",
        channel_id="head-integrate",
        delta_to_picture="",
    )
    assert "world: Where is empty" in world_misses(m, product)
