from pathlib import Path

from taskorg.diagnostics import _authority
from taskorg.factory import new_run
from taskorg.gates import World, decide, Subtask
from taskorg.models import Artifact


def test_exists_file_blocks_matching_subtask(tmp_path: Path):
    already = tmp_path / "source-a.md"
    already.write_text("done")
    world = World(existing_files=[str(already)], existing_channels=["source-a"])
    rec = decide([Subtask("source-a", "need writer")], world=world)
    assert rec is None


def test_guidelines_quote_is_not_authority_hit():
    m = new_run("n1", "Write", "Keep", "Done")
    m.artifacts.append(
        Artifact(
            claim="The reviewer may not take over the roster. Keep the context.",
            evidence=[],
            uncertainty="n",
            channel_id="draft",
            context_update="x",
        )
    )
    assert _authority(m)["hits"] == []
