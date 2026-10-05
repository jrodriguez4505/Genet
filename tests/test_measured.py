"""The measured "should we": fan out only for declared isolation or material that does not fit one context."""

import json
from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import LEAD_COVERS, Subtask, assess
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.persist import load_run
from taskorg.tools import Toolbox

TWO = "Two notes. subtask:note-a@retrieve=sources_must_not_mix subtask:note-b@retrieve=sources_must_not_mix"


def _sizes(**tokens):
    """Each sub-task has a file of its own of the given size."""
    return lambda s: {f"{s.channel_id}.md": tokens[s.channel_id]} if s.channel_id in tokens else None


def _files(**shares):
    """Each sub-task needs the named files; a name shared by two sub-tasks is one file."""
    return lambda s: shares.get(s.channel_id)


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


def test_a_shared_file_counts_once():
    big = {"big.md": 800}
    verdicts = assess(PAIR, policy="measured", material=_files(a=big, b=big), context_limit=2000)
    assert all("fits in one context: ~800 tokens" in v.refused for v in verdicts)


def test_a_split_that_does_not_shrink_the_work_is_refused():
    big = {"big.md": 3000}
    verdicts = assess(PAIR, policy="measured", material=_files(a=big, b=big), context_limit=2000)
    assert all(v.gate == "should_we" and "does not shrink the work" in v.refused for v in verdicts)
    # One sub-task needing everything is the same: its sub-agent still carries the whole load.
    verdicts = assess(PAIR, policy="measured", material=_files(a={"big.md": 3000, "s.md": 50}, b={"s.md": 50}),
                      context_limit=2000)
    assert all("does not shrink the work: one sub-task alone needs all ~3050 tokens" in v.refused for v in verdicts)


def test_partly_shared_material_that_a_split_shrinks_is_a_reason():
    verdicts = assess(PAIR, policy="measured", context_limit=2000,
                      material=_files(a={"shared.md": 600, "a.md": 600}, b={"shared.md": 600, "b.md": 600}))
    assert all(v.legal and v.basis == "measured" for v in verdicts)


def test_the_room_is_the_limit_less_the_measured_overhead():
    sizes = _sizes(a=750, b=750)
    measured = assess(PAIR, policy="measured", material=sizes, context_limit=2000, overhead=300)
    assert all("~1500 tokens of material vs 1700 available per call after ~300 for the brief" in v.refused for v in measured)
    # Without a measurement the gate falls back to fit_fraction of the limit, and 1500 does not fit 1000.
    guessed = assess(PAIR, policy="measured", material=sizes, context_limit=2000)
    assert all(v.legal and v.basis == "measured" for v in guessed)
    # A brief that fills the call leaves no room at all.
    full = assess(PAIR, policy="measured", material=_sizes(a=1, b=1), context_limit=2000, overhead=2500)
    assert all(v.legal for v in full)


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
    assert box.material("a") == {str((ws / "a.md").resolve()): 100}
    assert sum(box.material("a", "also read extra.txt").values()) == 300
    assert box.material("b") is None  # hidden or outside the workspace: not counted
    assert Toolbox().material("a") is None


def test_material_keys_a_file_once_when_it_is_both_in_a_root_and_attached(tmp_path: Path):
    (tmp_path / "a.md").write_text("x" * 400)
    box = Toolbox(roots=[tmp_path], files=[tmp_path / "a.md"])
    assert box.material("a") == {str((tmp_path / "a.md").resolve()): 100}


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
    assert diagnose(m)["run"]["split_basis"] == []


def test_the_overhead_is_the_leads_planning_call(tmp_path: Path):
    m = _run(tmp_path, chars=400, context=4000)
    plan = next(c for c in m.calls if c["function"] == "lead")
    cost = plan["prompt_tokens"] + plan["completion_tokens"]
    assert f"available per call after ~{cost} for the brief and reply" in m.notes["question-1"].reason


def test_large_notes_fan_out(tmp_path: Path):
    m = _run(tmp_path, chars=9000, context=4000)
    assert m.state.worker_count() == 2
    assert {e.detail["basis"] for e in m.log if e.event == "gate"} == {"measured"}
    d = diagnose(m)
    assert d["run"]["split_basis"] == ["measured"]
    assert {i["detail"].get("basis") for i in d["interactions"] if i["event"] == "gate"} == {"measured"}


def test_isolation_flag_fans_out_small_notes(tmp_path: Path):
    m = _run(tmp_path, chars=400, context=4000, isolation_required=True)
    assert m.state.worker_count() == 2


def test_two_sub_tasks_over_one_large_file_stay_with_one_agent(tmp_path: Path):
    """Splitting one file between two readers does not make either brief smaller."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "report.md").write_text("Q3 revenue was 4.1M. " + "filler " * 4000)
    m = new_run("ms-2", "Answer two questions about the report", "Do not mix", "Integrated")
    budget = Budget(max_calls=20, max_tokens=100_000, max_tokens_per_call=4000, tier="open")
    context = "subtask:part-1@retrieve=read_report.md_revenue subtask:part-2@retrieve=read_report.md_hiring"
    Engine(MemoryStore(tmp_path / "s"), budget=budget, toolbox=Toolbox(roots=[ws])).run_task(m, context=context)
    assert m.state.worker_count() == 0
    assert "does not shrink the work" in m.notes["question-1"].reason


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
