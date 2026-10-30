"""The shared situation (team design part 8): every field of it is acted on by the kernel, or gone.

Decision points and forecasts, abort criteria the operator sets, the main effort, a sub-agent handing
its part back when the plan is wrong for it, and a situation kept current between a member's calls.
"""

import json
import threading
from pathlib import Path

import pytest

from taskorg.adapters import TOOL_RESULTS, ModelAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask
from taskorg.loop import REPORT_UP_NOTE, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import MAX_WORKERS, Artifact, NoteStatus, Status
from taskorg.persist import load_run, run_to_dict, save_run
from taskorg.schema import state_contract
from taskorg.situation import DECISION_POINTS, Forecast, parse_abort
from taskorg.tools import Toolbox

PARTS = [Subtask(c, "keep apart") for c in ("part-a", "part-b", "part-c")]


def _art(claim="PASS ANSWER: 1", requests=None):
    return Artifact(claim=claim, evidence=[], uncertainty="", channel_id="x", context_update=claim, requests=requests or [])


class Team(ModelAdapter):
    """Answers every call. `reply` may change a worker's reply; `usage` is what each call reports."""

    name = "team"

    def __init__(self, reply=None, verify="PASS", usage=None):
        self.reply, self.verify, self.usage = reply or (lambda brief, art: art), verify, usage
        self.briefs = []
        self._lock = threading.Lock()

    def act(self, brief):
        with self._lock:
            self.briefs.append(brief)
            if self.usage:
                self.last_usage = {"prompt_tokens": self.usage, "completion_tokens": 0}
        if brief.mode == "verify":
            return _art(claim=self.verify)
        if brief.mode == "plan":
            return _art(claim="plan", requests=[t for t in brief.context.split() if t.startswith("subtask:")])
        art = _art()
        return self.reply(brief, art) if brief.slot_function == "worker" else art


def _engine(tmp_path, adapter, **kw):
    kw.setdefault("budget", Budget(max_calls=40, max_tokens=200_000))
    kw.setdefault("parallel", False)
    return Engine(MemoryStore(tmp_path / "store"), adapter=adapter, **kw)


def _run(name="sit-1"):
    m = new_run(name, "Answer three parts", "Keep the parts apart", "One merged answer")
    m.state.success_criteria = ["ANSWER:"]
    return m


def _fanout(engine, m, subtasks=PARTS):
    return engine.run_fanout(m, context="three parts", subtasks=subtasks, axes=["parallel"], operator_question="?")


def _points(m):
    return [e.detail for e in m.log if e.event == "decision_point"]


# --- the fields: pace is gone, the decision points are the run's ---


def test_a_new_run_checks_at_every_decision_point_and_has_no_pace():
    m = _run()
    assert m.state.checkpoints == list(DECISION_POINTS) == ["plan", "reports", "verdict"]
    assert m.state.primary == "" and m.state.abort_criteria == [] and m.state.projections == []
    assert not hasattr(m.state, "cadence")
    contract = state_contract(m.state)
    assert contract["schedule"] == {"checkpoints": ["plan", "reports", "verdict"]}
    assert "cadence" not in run_to_dict(m)["state"]


# --- abort criteria come from a fixed list ---


def test_abort_criteria_are_parsed_from_the_fixed_list():
    assert parse_abort(["forecast_short", " parts_failed:02 ", "forecast_short", ""]) == ["forecast_short", "parts_failed:2"]
    assert parse_abort([]) == [] and parse_abort(None) == []


@pytest.mark.parametrize("bad", [
    "stop if it looks wrong", "parts_failed", "parts_failed:0", "parts_failed:x", "parts_failed:-1",
    "parts_failed:²", "parts_failed:12345", "forecast_short:1", "forecast_short:", "FORECAST_SHORT",
])
def test_free_text_and_malformed_abort_criteria_are_refused(bad):
    with pytest.raises(InvariantError) as e:
        parse_abort([bad])
    assert e.value.code == "ABORT"


# --- decision points and forecasts ---


def test_a_split_run_records_a_forecast_at_each_decision_point(tmp_path: Path):
    m = _run()
    result = _fanout(_engine(tmp_path, Team()), m)
    assert m.status == Status.COMPLETE and result.verified
    points = _points(m)
    assert [p["at"] for p in points] == ["plan", "reports", "verdict"]
    # The sub-agents, the merge and the check; then the merge and the check; then nothing.
    assert [p["calls"] for p in points] == [5, 2, 0]
    assert all(p["abort"] is None and p["short"] is False for p in points)
    # The forecasts are the kernel's, one line per decision point, kept with the run.
    assert len(m.state.projections) == 3
    assert m.state.projections[0].startswith("plan: the rest needs at least 5 calls")
    assert "calls and about" in m.state.projections[0] and "left" in m.state.projections[0]
    assert load_run(save_run(m, tmp_path / "r.json")).state.projections == m.state.projections


def test_a_single_agent_run_checks_after_the_plan_and_after_the_verdict(tmp_path: Path):
    m = _run("sit-single")
    _engine(tmp_path, Team()).run_task(m, context="one source holds it")
    assert [(p["at"], p["calls"]) for p in _points(m)] == [("plan", 2), ("verdict", 0)]


def test_the_kernel_checks_only_the_decision_points_the_run_lists(tmp_path: Path):
    m = _run()
    m.state.checkpoints = ["verdict"]
    _fanout(_engine(tmp_path, Team()), m)
    assert [p["at"] for p in _points(m)] == ["verdict"]
    assert len(m.state.projections) == 1


def test_a_forecast_counts_calls_and_tokens_left():
    fc = Forecast(at="plan", calls=2, tokens=8_000, calls_left=5, tokens_left=6_000)
    assert fc.short  # tokens
    assert not Forecast(at="plan", calls=2, tokens=8_000, calls_left=2, tokens_left=8_000).short  # spending the last is legal
    assert Forecast(at="plan", calls=3, tokens=0, calls_left=2, tokens_left=10).short  # calls
    assert not Forecast(at="plan", calls=9, tokens=9, calls_left=None, tokens_left=None).short  # no budget, never short


# --- forecast_short stops a run before it spends what cannot finish ---


def _tight(m, tmp_path, criteria):
    """4,000 tokens a call against 10,000: the plan leaves too little for the work and the check."""
    m.state.abort_criteria = criteria
    engine = _engine(tmp_path, Team(usage=4_000), budget=Budget(max_calls=40, max_tokens=10_000, max_tokens_per_call=8_000))
    with pytest.raises(InvariantError) as e:
        engine.run_task(m, context="one source holds it")
    return e.value


def test_forecast_short_stops_the_run_at_the_plan_and_spends_less(tmp_path: Path):
    stopped = _run("sit-abort")
    err = _tight(stopped, tmp_path / "a", ["forecast_short"])
    assert err.code == "ABORT" and stopped.status == Status.ABORT
    assert "abort criterion forecast_short met at plan" in stopped.stop_reason
    assert stopped.usage()[0] == 1  # the plan only
    point = _points(stopped)[-1]
    assert point["at"] == "plan" and point["short"] and point["abort"] == "forecast_short"
    assert any("the run stopped at a decision point: abort criterion forecast_short met at plan" in w
               for w in stopped.review["what_failed"])

    # The same run without the criterion goes on, and stops on its budget after spending more.
    goes_on = _run("sit-on")
    err = _tight(goes_on, tmp_path / "b", [])
    assert err.code == "BUDGET"
    assert goes_on.usage()[0] > stopped.usage()[0] and goes_on.usage()[1] > stopped.usage()[1]


def test_forecast_short_counts_calls_too(tmp_path: Path):
    m = _run("sit-calls")
    m.state.abort_criteria = ["forecast_short"]
    with pytest.raises(InvariantError, match="forecast_short met at plan"):
        _engine(tmp_path, Team(), budget=Budget(max_calls=2, max_tokens=200_000)).run_task(m, context="c")
    assert len(m.calls) == 1


def test_a_run_whose_forecast_holds_completes_with_forecast_short_set(tmp_path: Path):
    m = _run("sit-holds")
    m.state.abort_criteria = ["forecast_short"]
    assert _fanout(_engine(tmp_path, Team()), m).verified and m.status == Status.COMPLETE


def test_an_abort_criterion_the_kernel_cannot_test_stops_the_run(tmp_path: Path):
    m = _run("sit-junk")
    m.state.abort_criteria = ["when it feels wrong"]
    with pytest.raises(InvariantError) as e:
        _fanout(_engine(tmp_path, Team()), m)
    assert e.value.code == "ABORT" and m.status == Status.ABORT and len(m.calls) == 0


# --- parts_failed:N stops a run at the reports ---


def _fails(channel):
    def reply(brief, art):
        if brief.channel_id == channel:
            raise InvariantError("LIVE", "the endpoint failed")
        return art
    return reply


def test_parts_failed_stops_the_run_when_the_reports_come_in(tmp_path: Path):
    m = _run("sit-parts")
    m.state.abort_criteria = ["parts_failed:1"]
    with pytest.raises(InvariantError, match="parts_failed:1 met at reports"):
        _fanout(_engine(tmp_path, Team(_fails("part-b"))), m)
    assert not any(c.get("mode") == "integrate" for c in m.calls)  # stopped before the merge


def test_parts_failed_counts_up_to_its_value(tmp_path: Path):
    m = _run("sit-parts-2")
    m.state.abort_criteria = ["parts_failed:2"]
    assert _fanout(_engine(tmp_path, Team(_fails("part-b"))), m).verified  # one failed part: the lead covers it


# --- the main effort is judged first ---


def _six():
    return [Subtask(f"part-{i}", "keep apart") for i in range(1, 7)]


def test_the_main_effort_is_staffed_when_the_cap_runs_short(tmp_path: Path):
    without = _run("sit-main-0")
    _fanout(_engine(tmp_path / "a", Team()), without, _six())
    staffed = {s.channel_id for s in without.state.slots if s.function == "worker"}
    assert len(staffed) == MAX_WORKERS and "part-6" not in staffed

    m = _run("sit-main-1")
    m.state.primary = "part-6"
    _fanout(_engine(tmp_path / "b", Team()), m, _six())
    staffed = {s.channel_id for s in m.state.slots if s.function == "worker"}
    assert "part-6" in staffed and len(staffed) == MAX_WORKERS
    assert [e.detail for e in m.log if e.event == "main_effort"] == [{"channel": "part-6", "proposed": True}]


def test_a_main_effort_nobody_proposed_changes_nothing(tmp_path: Path):
    m = _run("sit-main-2")
    m.state.primary = "part-9"
    _fanout(_engine(tmp_path, Team()), m)
    assert [e.detail for e in m.log if e.event == "main_effort"] == [{"channel": "part-9", "proposed": False}]
    assert [s.channel_id for s in m.state.slots if s.function == "worker"] == ["part-a", "part-b", "part-c"]


# --- reported up: a sub-agent hands its part back when the plan is wrong for it ---


def _hands_back(channel, why="my file is the look-alike's, not this company's"):
    def reply(brief, art):
        if brief.channel_id == channel:
            art.requests = [f"replan: {why}"]
            art.claim = art.context_update = "PASS ANSWER: a guess"
        return art
    return reply


def test_a_part_handed_back_goes_to_the_lead_with_its_reason(tmp_path: Path):
    team = Team(_hands_back("part-b"))
    m = _run("sit-up")
    result = _fanout(_engine(tmp_path, team, report_up=True), m)
    assert m.status == Status.COMPLETE and result.verified
    # Not merged: the guess never reaches the shared context.
    assert {d.channel_id for d in m.deltas if d.stream == "merge"} == {"part-a", "part-c"}
    assert "a guess" not in m.state.context
    merge = next(b for b in team.briefs if b.mode == "integrate")
    assert ("reported they could not be done as planned, so they are yours to cover: "
            "part-b (its reason: my file is the look-alike's, not this company's)") in merge.packet
    # Reported up on the escalate stream, as a replan request the kernel closed with the new method.
    assert any(d.stream == "escalate" and d.claim.startswith("part-b:") for d in m.deltas)
    note = m.notes["replan-part-b"]
    assert note.kind == "replan" and note.status == NoteStatus.CLOSED and note.response == "CHANGE_METHOD"
    # The new method: the one that split, with the lead covering the part.
    assert note.reason == "multi-axis; the lead covers part-b, which its sub-agent reported could not be done as planned"
    assert "part-b: the sub-agent reported the plan wrong for it, and the lead covered the part" in m.notes["question-1"].reason
    assert [e.detail["channel"] for e in m.log if e.event == "part_reported"] == ["part-b"]


def test_a_handed_back_part_counts_as_covered_and_is_not_a_failure(tmp_path: Path):
    m = _run("sit-up-2")
    m.state.abort_criteria = ["parts_failed:1"]
    assert _fanout(_engine(tmp_path, Team(_hands_back("part-b")), report_up=True), m).verified
    assert m.review is None


def test_every_part_handed_back_still_leaves_the_world_accounted_for(tmp_path: Path):
    def all_back(brief, art):
        art.requests = ["replan: nothing here"]
        return art
    m = _run("sit-up-3")
    assert _fanout(_engine(tmp_path, Team(all_back), report_up=True), m).verified
    assert not any(d.stream == "merge" for d in m.deltas)
    assert all(n.status == NoteStatus.CLOSED for n in m.notes.values())


def test_a_reason_is_bounded_model_text(tmp_path: Path):
    team = Team(_hands_back("part-b", why="x" * 5_000))
    m = _run("sit-up-4")
    _fanout(_engine(tmp_path, team, report_up=True), m)
    reason = next(e.detail["reason"] for e in m.log if e.event == "part_reported")
    assert reason == "x" * 200


def test_without_report_up_the_brief_is_unchanged_and_a_replan_request_is_just_text(tmp_path: Path):
    team = Team(_hands_back("part-b"))
    m = _run("sit-up-off")
    _fanout(_engine(tmp_path, team), m)
    assert not any(REPORT_UP_NOTE in b.packet for b in team.briefs)
    assert {d.channel_id for d in m.deltas if d.stream == "merge"} == {"part-a", "part-b", "part-c"}
    assert not any(e.event == "part_reported" for e in m.log)

    on = Team()
    _fanout(_engine(tmp_path / "on", on, report_up=True), _run("sit-up-on"))
    workers = [b for b in on.briefs if b.slot_function == "worker"]
    assert workers and all(REPORT_UP_NOTE in b.packet for b in workers)


def test_a_part_handed_back_shows_in_the_review_when_the_run_has_one(tmp_path: Path):
    def reply(brief, art):
        if brief.channel_id == "part-a":
            raise InvariantError("LIVE", "the endpoint failed")
        return _hands_back("part-b")(brief, art)
    m = _run("sit-up-5")
    _fanout(_engine(tmp_path, Team(reply), report_up=True), m)
    assert m.review["parts"]["part-b"] == "handed back: the plan was wrong for it; covered by the lead"
    assert "the lead covered part-b, which its sub-agent handed back" in m.review["what_was_done"]
    assert "the lead reworked the product once" not in m.review["what_was_done"]


# --- kept current: a member's next call carries the situation as it stands ---


def test_a_change_made_after_the_split_reaches_the_next_call(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "part-a.md").write_text("part a holds 1\n")
    (ws / "part-b.md").write_text("part b holds 2\n")
    m = _run("sit-current")

    class Reads(Team):
        def act(self, brief):
            art = super().act(brief)
            if brief.slot_function == "worker" and TOOL_RESULTS not in brief.packet:
                art.requests = [f"read:{brief.channel_id}.md"]
                if brief.channel_id == "part-a":
                    # The lead revises the purpose while part-a is between its calls.
                    m.open_review("does the purpose still hold?", "mid-run")
                    m.answer_review(m.state.lead_id, "mid-run", "REVISE_GOAL", "Report each part's figure in $ millions")
            return art

    team = Reads()
    engine = _engine(tmp_path, team, toolbox=Toolbox(roots=[ws]))
    engine.run_fanout(m, context="two parts", subtasks=[Subtask("part-a", "x", skill="retrieve"),
                                                        Subtask("part-b", "x", skill="retrieve")],
                      axes=["parallel"], operator_question="?")
    first, second = [b for b in team.briefs if b.channel_id == "part-a" and b.slot_function == "worker"]
    assert first.purpose == "Keep the parts apart"
    assert second.purpose == "Report each part's figure in $ millions"
    assert "SITUATION CHANGED since your last call: purpose." in second.packet
    # part-b's first call came after the change, so it starts current and is told nothing.
    b_calls = [b for b in team.briefs if b.channel_id == "part-b" and b.slot_function == "worker"]
    assert all(b.purpose == "Report each part's figure in $ millions" for b in b_calls)
    assert not any("SITUATION CHANGED" in b.packet for b in b_calls)
    assert [e.detail for e in m.log if e.event == "situation_update"] == [{"slot": "w-part-a", "changed": ["purpose"]}]
    # Its context is still the split's: kept current is the situation, not a sibling's notes.
    assert second.context == first.context


def test_an_unchanged_situation_adds_nothing_to_the_next_call(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "part-a.md").write_text("part a holds 1\n")

    class Reads(Team):
        def act(self, brief):
            art = super().act(brief)
            if brief.channel_id == "part-a" and TOOL_RESULTS not in brief.packet:
                art.requests = ["read:part-a.md"]
            return art

    team = Reads()
    m = _run("sit-same")
    _engine(tmp_path, team, toolbox=Toolbox(roots=[ws])).run_fanout(
        m, context="c", subtasks=[Subtask("part-a", "x", skill="retrieve"), Subtask("part-b", "x")],
        axes=["parallel"], operator_question="?")
    assert not any("SITUATION CHANGED" in b.packet for b in team.briefs)
    assert not any(e.event == "situation_update" for e in m.log)


# --- the operator's flags ---


def _cli(tmp_path, *extra):
    return main(["run", "--store", str(tmp_path / "store"), "--out", str(tmp_path / "run.json"), *extra])


def test_the_cli_sets_abort_criteria_and_the_main_effort(tmp_path: Path):
    assert _cli(tmp_path, "--abort", "forecast_short", "--abort", "parts_failed:2", "--main-effort", "north") == 0
    saved = json.loads((tmp_path / "run.json").read_text())["state"]
    assert saved["abort_criteria"] == ["forecast_short", "parts_failed:2"] and saved["primary"] == "north"
    assert saved["checkpoints"] == ["plan", "reports", "verdict"] and len(saved["projections"]) == 2


def test_the_cli_refuses_an_abort_criterion_it_cannot_test_before_anything_runs(tmp_path: Path, capsys):
    assert _cli(tmp_path, "--abort", "if it goes badly") == 1
    said = capsys.readouterr()
    assert "not one the kernel can test" in said.out + said.err
    assert not (tmp_path / "run.json").exists()


def test_an_older_saved_run_with_a_pace_still_loads(tmp_path: Path):
    m = _run("sit-old")
    raw = run_to_dict(m)
    raw["state"]["cadence"] = "run"
    raw["state"]["checkpoints"] = ["context", "switch_skill", "gates", "complete"]
    path = tmp_path / "old.json"
    path.write_text(json.dumps(raw))
    loaded = load_run(path)
    assert loaded.state.checkpoints == ["context", "switch_skill", "gates", "complete"]
    assert not hasattr(loaded.state, "cadence")
