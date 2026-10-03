from pathlib import Path

from taskorg.cli import main
from taskorg.persist import load_run
from taskorg.schema import REQUIRED_ARTIFACT, REQUIRED_STATE, state_contract


def test_schemas_are_bound():
    assert "claim" in REQUIRED_ARTIFACT
    assert "roster" in REQUIRED_STATE


def test_cli_halt_saves_run(tmp_path: Path, capsys):
    out = tmp_path / "halt.json"
    rc = main([
        "fanout", "--tier", "tight", "--id", "halt-save",
        "--store", str(tmp_path), "--out", str(out),
        "--context", "subtask:source-a=x subtask:source-b=y",
        "--subtasks", "source-a:x,source-b:y",
    ])
    assert rc == 1
    assert out.exists()
    m = load_run(out)
    assert m.status.value == "abort"
    assert "cannot fan out" in m.stop_reason


def test_brief_command(tmp_path: Path, capsys):
    out = tmp_path / "brief.json"
    rc = main([
        "brief",
        "--goal", "Write the report",
        "--purpose", "Keep the context",
        "--context", "enough from the first source",
        "--id", "brief-t",
        "--store", str(tmp_path),
        "--out", str(out),
    ])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "could_this_have_been_one" in printed
    m = load_run(out)
    contract = state_contract(m.state)
    assert contract["goal"]["goal"] == "Write the report"
    assert contract["purpose"]["purpose"] == "Keep the context"
