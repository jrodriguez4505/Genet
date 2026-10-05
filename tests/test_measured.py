"""The measured "should we": fan out only for declared isolation or material that does not fit one context."""

import json
from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import LEAD_COVERS, Subtask, assess
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.persist import load_run
from taskorg.tools import Toolbox

TWO = "Two notes. subtask:note-a@retrieve=sources_must_not_mix subtask:note-b@retrieve=sources_must_not_mix"


def _sizes(**tokens):
    return lambda s: tokens.get(s.channel_id)


PAIR = [Subtask("a", "x"), Subtask("b", "x")]


# --- the gate ---


def test_material_that_fits_stays_with_one_agent():
    verdicts = assess(PAIR, policy="measured", material=_sizes(a=300, b=300), context_limit=2000)
    assert not any(v.legal for v in verdicts)
    assert all(v.gate == "should_we" and "fits in one context: ~600 tokens" in v.refused for v in verdicts)
    assert all(v.gates.should_we is False for v in verdicts)


def test_material_that_does_not_fit_is_a_reason():
    verdicts = assess(PAIR, policy="measured", material=_sizes(a=800, b=800), context_limit=2000)
    assert all(v.legal and v.basis == "measured" for v in verdicts)


def test_unknown_material_is_not_a_reason():
    verdicts = assess(PAIR, policy="measured", material=_sizes(a=5000), context_limit=2000)
    assert all("no measurable reason" in v.refused for v in verdicts)


def test_declared_isolation_is_a_reason_even_when_it_fits():
    verdicts = assess(PAIR, policy="measured", declared=True, material=_sizes(a=1, b=1), context_limit=2000)
    assert all(v.legal and v.basis == "declared" for v in verdicts)


def test_stated_policy_takes_the_leads_reasons():
    verdicts = assess(PAIR, policy="stated")
    assert all(v.legal and v.basis == "stated" for v in verdicts)


def test_gates_still_run_in_order_under_the_measured_policy():
    lone = assess([Subtask("a", "x")], policy="measured", material=_sizes(a=9999), context_limit=10)
    assert lone[0].refused == LEAD_COVERS
    tier = assess(PAIR, policy="measured", declared=True, allow_split=False, tier="tight")
    assert all(v.gate == "could_we" and "tier tight" in v.refused for v in tier)


def test_unknown_policy_is_refused():
    with pytest.raises(InvariantError) as e:
        assess(PAIR, policy="vibes")
    assert e.value.code == "GATES"


# --- the material estimate ---


def test_material_counts_files_named_for_the_channel_or_in_the_note(tmp_path: Path):
    ws = tmp_path / "ws"
    (ws / ".hidden").mkdir(parents=True)
    (ws / "a.md").write_text("x" * 400)
    (ws / "extra.txt").write_text("y" * 800)
    (ws / ".hidden" / "b.md").write_text("z" * 4000)
    outside = tmp_path / "b.md"
    outside.write_text("w" * 4000)
    box = Toolbox(roots=[ws])
    assert box.material("a") == 100
    assert box.material("a", "also read extra.txt") == 300
    assert box.material("b") is None  # hidden or outside the workspace: not counted
    assert Toolbox().material("a") is None


# --- end to end ---


def _workspace(tmp_path: Path, chars: int) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "note-a.md").write_text("Q3 revenue was 4.1M. " + "filler " * (chars // 7))
    (ws / "note-b.md").write_text("Hiring plan: 3 engineers. " + "filler " * (chars // 7))
    return ws


def _run(tmp_path: Path, chars: int, context: int, **kw):
    m = new_run("ms-1", "Answer two notes", "Do not mix", "Integrated")
    budget = Budget(max_calls=20, max_tokens=100_000, max_tokens_per_call=context, tier="open")
    Engine(MemoryStore(tmp_path / "s"), budget=budget, toolbox=Toolbox(roots=[_workspace(tmp_path, chars)]), **kw).run_task(m, context=TWO)
    return m


def test_small_notes_stay_with_one_agent(tmp_path: Path):
    m = _run(tmp_path, chars=400, context=4000)
    assert m.state.worker_count() == 0
    assert "fits in one context" in m.notes["question-1"].reason


def test_large_notes_fan_out(tmp_path: Path):
    m = _run(tmp_path, chars=6000, context=4000)
    assert m.state.worker_count() == 2
    assert {e.detail["basis"] for e in m.log if e.event == "gate"} == {"measured"}


def test_isolation_flag_fans_out_small_notes(tmp_path: Path):
    m = _run(tmp_path, chars=400, context=4000, isolation_required=True)
    assert m.state.worker_count() == 2


def test_operator_named_subtasks_count_as_declared(tmp_path: Path):
    m = new_run("fo-1", "E", "P", "S")
    Engine(MemoryStore(tmp_path), budget=Budget.for_tier("open")).run_fanout(
        m, context="x", subtasks=[Subtask("a", "x"), Subtask("b", "y")], axes=["fan_in"], operator_question="?")
    assert m.state.worker_count() == 2


# --- CLI ---


@pytest.mark.parametrize("flags, workers", [([], 0), (["--isolate"], 2), (["--split-policy", "stated"], 2)])
def test_cli_split_flags(tmp_path: Path, capsys, flags, workers):
    ws = _workspace(tmp_path, 100)
    out = tmp_path / "r.json"
    rc = main(["run", "--tier", "open", "--workspace", str(ws), "--store", str(tmp_path / "d"), "--out", str(out),
               "--context", TWO, *flags])
    assert rc == 0, capsys.readouterr().out
    assert load_run(out).state.worker_count() == workers


def test_cli_compare_accepts_genet_stated(capsys):
    assert main(["compare", "--strategies", "genet,genet-stated", "--dry-run", "--per-family", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["trials"] == 4 * 2


def test_the_first_refusing_gate_names_the_reason():
    """A sub-task refused at should-we keeps that reason even when the tier would also refuse."""
    verdicts = assess(PAIR, policy="measured", material=_sizes(a=10, b=10), context_limit=2000,
                      allow_split=False, tier="tight", calls_left=1)
    assert all(v.gate == "should_we" and "fits in one context" in v.refused for v in verdicts)
