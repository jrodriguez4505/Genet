from pathlib import Path

from taskorg.cli import main
from taskorg.persist import load_mission
from taskorg.schema import REQUIRED_ARTIFACT, REQUIRED_FIVE, picture_contract


def test_schemas_are_bound():
    assert "claim" in REQUIRED_ARTIFACT
    assert "who" in REQUIRED_FIVE


def test_cli_halt_saves_mission(tmp_path: Path, capsys):
    out = tmp_path / "halt.json"
    rc = main([
        "split", "--pace", "crawl", "--id", "halt-save",
        "--store", str(tmp_path), "--out", str(out),
        "--look", "seam:source-a=x seam:rear=y",
        "--seams", "source-a:x,rear:y",
    ])
    assert rc == 1
    assert out.exists()
    m = load_mission(out)
    assert m.status.value == "abort"
    assert "cannot split" in m.stop_reason


def test_brief_command(tmp_path: Path, capsys):
    out = tmp_path / "brief.json"
    rc = main([
        "brief",
        "--effect", "Issue the order",
        "--purpose", "Hold the picture",
        "--look", "enough from the first source",
        "--id", "brief-t",
        "--store", str(tmp_path),
        "--out", str(out),
    ])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "could_this_have_been_one" in printed
    m = load_mission(out)
    contract = picture_contract(m.picture)
    assert contract["what"]["effect"] == "Issue the order"
    assert contract["why"]["purpose"] == "Hold the picture"
