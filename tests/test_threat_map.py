"""What model text can reach. A marker in every field a model fills, then a look at where it went.

The map is in SECURITY.md. It holds for every way a run can go: a plain split, a failed verdict and rework,
hostile channel names, a part handed back, a malformed sub-agent, and the cards.
"""

import pytest

from taskorg.adapters import ModelAdapter
from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import SKILLS, Artifact
from taskorg.review import LESSONS, part_statuses
from taskorg.tools import Toolbox

MARK = "ZQXMARK"
SCENARIOS = {
    "plain": {},
    "rework": {"verdict": "FAIL"},
    "hostile channels": {"channels": [f"a{MARK}x", f"b{MARK}y"]},
    "handed back": {"report_up": True, "hand_back": True},
    "malformed part": {"malformed": True},
    "cards": {"cards": True},
}


class Marked(ModelAdapter):
    """Puts the marker in every field it fills."""

    name = "marked"

    def __init__(self, verdict="PASS", channels=("alpha", "beta"), hand_back=False, malformed=False, **_):
        self.verdict, self.channels, self.hand_back, self.malformed = verdict, channels, hand_back, malformed

    def act(self, brief):
        tag = f"{MARK}-{brief.slot_function}"
        requests = []
        channel = brief.channel_id or brief.slot_function
        claim = f"{tag} criterion ANSWER: 1"
        if brief.slot_function == "verifier":
            claim = f"{self.verdict} {tag} criterion"
        elif brief.mode == "plan":
            requests = [f"subtask:{c}@retrieve=keep {MARK} apart" for c in self.channels]
        elif brief.slot_function == "worker":
            if self.malformed:
                channel = f"wrong{MARK}"
            elif self.hand_back:
                requests = [f"replan:{tag} the plan is wrong"]
        return Artifact(claim=claim, evidence=[f"{tag} evidence"], uncertainty=f"{tag} doubt", channel_id=channel,
                        context_update=f"{tag} note", requests=requests)


class Clean(ModelAdapter):
    """A later run's model, which keeps every brief it is sent."""

    name = "clean"

    def __init__(self):
        self.briefs = []

    def act(self, brief):
        self.briefs.append(brief)
        claim = "PASS criterion" if brief.slot_function == "verifier" else "criterion ANSWER: 1"
        return Artifact(claim=claim, evidence=[], uncertainty="", channel_id=brief.channel_id or brief.slot_function,
                        context_update="", requests=[])


def _budget(calls=30):
    return Budget(max_calls=calls, max_tokens=10**7, max_seconds=60, max_tokens_per_call=100_000,
                  allow_split=True, allow_adapt=True, tier="bench")


def _run(store, adapter, run_id, toolbox, **engine):
    run = new_run(run_id, goal="the goal", purpose="the purpose", done_when="done")
    run.state.success_criteria = ["criterion"]
    try:
        Engine(store, adapter=adapter, budget=_budget(), toolbox=toolbox, max_tool_rounds=2, **engine).run_task(run, context="known")
    except InvariantError:
        pass
    return run


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    for name in ("alpha", "beta"):
        (root / f"{name}.md").write_text(f"# {name}\nRevenue was 1.0.\n")
    return root


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_model_text_stays_out_of_what_later_runs_read(tmp_path, workspace, scenario):
    setup = SCENARIOS[scenario]
    store = MemoryStore(tmp_path / "store")
    run = _run(store, Marked(**setup), "first", Toolbox(roots=[workspace]), isolation_required=True,
               report_up=setup.get("report_up", False), cards=setup.get("cards", False))
    assert any(s.function == "worker" for s in run.state.slots), "the run must reach a split, or this tests nothing"

    for folder in ("guidelines", "records"):
        for path in (store.root / folder).rglob("*"):
            assert not path.is_file() or MARK not in path.read_text(encoding="utf-8"), path
    assert all(MARK not in lesson for lesson, _ in store.lessons())
    assert all(lesson in LESSONS.values() for lesson, _ in store.lessons())

    later = Clean()
    _run(store, later, "second", Toolbox(roots=[]))
    assert later.briefs
    assert not [b.slot_function for b in later.briefs if MARK in b.packet + b.context + b.goal + b.purpose]


def test_positions_are_known_skills_and_the_models_name_comes_from_settings(tmp_path, workspace):
    store = MemoryStore(tmp_path / "store")
    _run(store, Marked(), "first", Toolbox(roots=[workspace]), isolation_required=True)
    records = store.position_records()
    assert records and all(r["skill"] in SKILLS and MARK not in r["model"] for r in records)


def test_no_code_reads_the_episodic_archive_back():
    """It holds a product's text, so nothing may carry it into a brief."""
    from pathlib import Path

    import taskorg

    root = Path(taskorg.__file__).parent
    readers = [p.name for p in root.glob("*.py") if p.name != "memory_store.py" and ".episodic" in p.read_text(encoding="utf-8")]
    assert readers == []


class Proposes(Clean):
    """A lead that proposes two parts, which the gates refuse because the work fits one call."""

    def act(self, brief):
        art = super().act(brief)
        if brief.mode == "plan":
            art.requests = ["subtask:alpha@retrieve=keep apart", "subtask:beta@retrieve=keep apart"]
        return art


def test_a_part_the_lead_did_alone_reads_as_covered(tmp_path, workspace):
    run = _run(MemoryStore(tmp_path / "store"), Proposes(), "alone", Toolbox(roots=[workspace]))
    assert run.status.value == "complete" and not any(s.function == "worker" for s in run.state.slots)
    assert set(part_statuses(run).values()) == {"no sub-agent; covered by the lead"}
    assert diagnose(run)["team"]["parts"] == part_statuses(run)


def test_a_part_is_not_covered_when_the_run_stopped_before_the_verifier(tmp_path, workspace):
    class Stops(Proposes):
        def act(self, brief):
            if brief.mode == "work":
                raise InvariantError("LIVE", "the endpoint failed")
            return super().act(brief)

    run = _run(MemoryStore(tmp_path / "store"), Stops(), "stopped", Toolbox(roots=[workspace]))
    assert set(part_statuses(run).values()) == {"no sub-agent; not covered"}
