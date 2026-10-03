from pathlib import Path

from taskorg.diagnostics import _authority
from taskorg.factory import element_at_rest
from taskorg.gates import World, decide, Seam
from taskorg.models import Artifact


def test_exists_file_blocks_matching_seam(tmp_path: Path):
    already = tmp_path / "source-a.md"
    already.write_text("done")
    world = World(existing_files=[str(already)], existing_channels=["source-a"])
    rec = decide([Seam("source-a", "need writer")], world=world)
    assert rec is None


def test_doctrine_quote_is_not_authority_hit():
    m = element_at_rest("n1", "Write", "Hold", "Done")
    m.artifacts.append(
        Artifact(
            claim="Why may not take over the roster. Hold the picture.",
            evidence=[],
            uncertainty="n",
            channel_id="draft",
            delta_to_picture="x",
        )
    )
    assert _authority(m)["hits"] == []
