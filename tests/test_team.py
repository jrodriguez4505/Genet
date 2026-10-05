"""Specialists, sandboxed tools, lead-driven staffing, concurrent sub-agents."""

import json
import threading
import time
from pathlib import Path

import pytest

from taskorg.adapters import Brief, StubAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import LEAD_COVERS, Subtask, World, assess
from taskorg.live import LiveAdapter, ScriptedLive, system_prompt
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import SKILLS
from taskorg.persist import load_run
from taskorg.skills import BRIEFS
from taskorg.subtasks import parse_subtasks
from taskorg.tools import Toolbox

TWO = "Two notes. subtask:note-a@retrieve=sources_must_not_mix subtask:note-b@retrieve=sources_must_not_mix"


def _engine(tmp_path: Path, tier: str = "open", **kw) -> Engine:
    return Engine(MemoryStore(tmp_path / "store"), budget=Budget.for_tier(tier), **kw)


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "note-a.md").write_text("Q3 revenue was 4.1M.\nQ3 churn was 2 percent.\n")
    (ws / "note-b.md").write_text("Hiring plan: 3 engineers.\n")
    return ws


def _reply(claim, evidence=(), requests=()):
    return json.dumps({
        "claim": claim, "evidence": list(evidence), "uncertainty": "script",
        "channel_id": "x", "context_update": "", "requests": list(requests),
    })


# --- skills and subtasks ---


def test_every_skill_has_a_brief():
    assert set(BRIEFS) == set(SKILLS)


def test_subtask_names_its_specialty():
    subtasks = parse_subtasks("subtask:a@retrieve=must_not_mix subtask:b=plain_split")
    assert [(s.channel_id, s.skill, s.named_failure) for s in subtasks] == [
        ("a", "retrieve", "must not mix"),
        ("b", "execute", "plain split"),
    ]


# --- gates ---


def _verdict(verdicts, channel):
    return next(v for v in verdicts if v.subtask.channel_id == channel)


def test_two_independent_parts_are_legal():
    verdicts = assess([Subtask("a", "mix"), Subtask("b", "mix")])
    assert all(v.legal for v in verdicts)
    for v in verdicts:
        v.gates.assert_legal()


def test_one_open_part_is_the_leads_job():
    [v] = assess([Subtask("a", "mix")])
    assert v.gate == "can_someone_else"
    assert v.gates.can_someone_else is True


def test_world_cover_leaves_one_open_part_for_the_lead():
    verdicts = assess([Subtask("a", "mix"), Subtask("b", "mix")], world=World(existing_files=["out/a.md"]))
    assert "covers a" in _verdict(verdicts, "a").refused
    assert _verdict(verdicts, "b").refused == LEAD_COVERS


def test_each_gate_refuses_in_order():
    verdicts = assess([
        Subtask("dup", "x"), Subtask("dup", "x"),
        Subtask("silent", ""),
        Subtask("odd", "x", skill="juggle"),
        Subtask("verify", "x"),
        Subtask("checker", "x", skill="verify"),
        Subtask("ok-1", "x"), Subtask("ok-2", "x"),
    ])
    assert _verdict(verdicts[1:], "dup").gate == "can_someone_else"
    assert _verdict(verdicts, "silent").gate == "should_we"
    assert _verdict(verdicts, "odd").gate == "could_we"
    assert "reserved" in _verdict(verdicts, "verify").refused
    assert _verdict(verdicts, "checker").gate == "can_someone_else"
    assert [v.subtask.channel_id for v in verdicts if v.legal] == ["dup", "ok-1", "ok-2"]


def test_tier_refuses_the_split():
    verdicts = assess([Subtask("a", "x"), Subtask("b", "x")], allow_split=False, tier="tight")
    assert not any(v.legal for v in verdicts)
    assert all("budget tier tight" in v.refused for v in verdicts)


def test_budget_pays_for_some_sub_agents_or_none():
    three = [Subtask("a", "x"), Subtask("b", "x"), Subtask("c", "x")]
    partial = assess(three, calls_left=4, calls_after_split=2)
    assert [v.legal for v in partial] == [True, True, False]
    none = assess(three, calls_left=3, calls_after_split=2)
    assert not any(v.legal for v in none)
    costly = assess(three, calls_left=8, calls_after_split=2, worker_cost=lambda s: 3)
    assert [v.legal for v in costly] == [True, True, False]


def test_worker_cap_holds():
    verdicts = assess([Subtask(c, "x") for c in "abcdef"], worker_slots_left=4)
    assert sum(v.legal for v in verdicts) == 4


# --- toolbox sandbox ---


def test_toolbox_reads_inside_and_refuses_outside(tmp_path: Path):
    ws = _workspace(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("do not read")
    (ws / "escape").symlink_to(secret)
    box = Toolbox(roots=[ws])
    assert "4.1M" in box.run("read:note-a.md")
    assert "not found" in box.run(f"read:{secret}")
    assert "not found" in box.run("read:../secret.txt")
    assert "not found" in box.run("read:escape")
    assert "do not read" not in box.run("retrieve:read")


def test_toolbox_search_and_list(tmp_path: Path):
    ws = _workspace(tmp_path)
    (ws / ".hidden").mkdir()
    (ws / ".hidden" / "x.md").write_text("Q3 hidden")
    (ws / "blob.bin").write_bytes(b"\x00Q3 binary")
    box = Toolbox(roots=[ws])
    found = box.run("retrieve:q3 churn")
    assert "note-a.md:2" in found and "revenue" not in found
    assert "hidden" not in box.run("retrieve:q3")
    assert "binary" not in box.run("retrieve:q3")
    listed = box.run("observe")
    assert "note-a.md" in listed and ".hidden" not in listed
    assert box.run("search:hiring") == box.run("retrieve:hiring")
    # A term in the file name counts; with no full match, the closest lines come back.
    assert "note-a.md:2" in box.run("retrieve:note-a churn")
    closest = box.run("retrieve:q3 churn forecast")
    assert "closest" in closest and "note-a.md:2" in closest


def test_search_snippet_keeps_the_match_in_long_lines(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "long.md").write_text("filler " * 120 + "Q3 revenue came in at $37.3M. " + "tail " * 80 + "\n")
    found = Toolbox(roots=[ws]).run("retrieve:q3 revenue")
    assert "$37.3M" in found and "…" in found


def test_toolbox_attached_file_and_empty_box(tmp_path: Path):
    f = tmp_path / "brief.txt"
    f.write_text("attached line")
    assert "attached line" in Toolbox(files=[f]).run("read:brief.txt")
    assert "no workspace" in Toolbox().run("read:brief.txt")


# --- tool loop ---


def test_specialist_uses_its_tool_and_cites_it(tmp_path: Path):
    ws = _workspace(tmp_path)
    m = new_run("tl-1", "Answer two notes", "Do not mix", "Integrated")
    _engine(tmp_path, toolbox=Toolbox(roots=[ws]), isolation_required=True).run_task(m, context=TWO)
    tools = [e.detail for e in m.log if e.event == "tool"]
    assert {t["channel"] for t in tools} == {"note-a", "note-b"}
    a = next(x for x in m.artifacts if x.channel_id == "note-a")
    assert any("4.1M" in ev for ev in a.evidence)
    assert not any("Hiring" in ev for ev in a.evidence)


class AsksForRead(StubAdapter):
    def act(self, brief):
        art = super().act(brief)
        if brief.slot_function == "lead" and brief.mode == "work":
            art.requests = ["read:note-a.md"]
        return art


def test_tool_outside_allowlist_never_runs(tmp_path: Path):
    m = new_run("tl-2", "E", "P", "S")
    eng = Engine(MemoryStore(tmp_path / "s"), adapter=AsksForRead(), budget=Budget.for_tier("open"))
    with pytest.raises(InvariantError) as e:
        eng.run_task(m, context="one source")  # no workspace: the lead drafts, draft has no read
    assert e.value.code == "TOOLS"
    assert not any(ev.event == "tool" for ev in m.log)


class AlwaysWantsMore(StubAdapter):
    def act(self, brief):
        art = super().act(brief)
        if brief.slot_function == "lead" and brief.mode == "work":
            art.requests = ["retrieve:more"]
        return art


def test_tool_rounds_are_capped(tmp_path: Path):
    ws = _workspace(tmp_path)
    m = new_run("tl-3", "E", "P", "S")
    eng = Engine(MemoryStore(tmp_path / "s"), adapter=AlwaysWantsMore(), budget=Budget.for_tier("open"),
                 toolbox=Toolbox(roots=[ws]), max_tool_rounds=2)
    eng.run_task(m, context="one source")
    work_calls = [c for c in m.calls if c.get("mode") == "work"]
    assert len(work_calls) == 3  # first call + two tool rounds
    assert any(e.event == "tool_rounds_exhausted" for e in m.log)


# --- the lead organizes the team ---


def test_single_agent_when_nothing_is_independent(tmp_path: Path):
    m = new_run("ms-1", "Summarize the paragraph", "One reading", "One sentence")
    result = _engine(tmp_path, "tight").run_task(m, context="One paragraph holds everything needed.")
    assert result.run.status.value == "complete"
    assert m.state.worker_count() == 0
    assert m.notes["question-1"].reason.startswith("single agent")
    assert len(m.calls) == 3  # plan, work, verify
    assert diagnose(m)["health"] == "ok"


def test_lead_splits_into_specialists_and_merges(tmp_path: Path):
    m = new_run("ms-2", "Answer two notes", "Do not mix", "Integrated")
    result = _engine(tmp_path, toolbox=Toolbox(roots=[_workspace(tmp_path)]), isolation_required=True).run_task(m, context=TWO)
    assert result.split is True
    assert result.channels == ["note-a", "note-b"]
    assert {s.skill for s in m.state.slots if s.function == "worker"} == {"retrieve"}
    splits = [e.detail for e in m.log if e.event == "split"]
    assert [s["gates"]["channel_id"] for s in splits] == ["note-a", "note-b"]
    assert sum(1 for e in m.log if e.event == "gate") == 2
    report = diagnose(m)
    assert report["health"] == "ok", report["flags"]
    assert m.notes["question-1"].reason == "2 sub-agents: note-a, note-b"


def test_one_open_part_switches_the_lead_skill(tmp_path: Path):
    m = new_run("ms-3", "Find the number", "One source", "Number stated")
    _engine(tmp_path, "tight", toolbox=Toolbox(roots=[_workspace(tmp_path)])).run_task(
        m, context="subtask:note-a@retrieve=needs_search")
    assert m.state.worker_count() == 0
    assert m.state.slot("lead-1").skill == "retrieve"
    assert any(e.event == "tool" for e in m.log)
    assert "the lead covers it" in m.notes["question-1"].reason


def test_tight_holds_single_agent_even_with_two_parts(tmp_path: Path):
    m = new_run("ms-4", "Answer two notes", "Do not mix", "Integrated")
    _engine(tmp_path, "tight", isolation_required=True).run_task(m, context=TWO)
    assert m.state.worker_count() == 0
    assert "budget tier tight does not allow a split" in m.notes["question-1"].reason
    assert "tight_split" not in diagnose(m)["flags"]


def test_existing_file_keeps_it_to_single_agent(tmp_path: Path):
    m = new_run("ms-5", "Answer two notes", "Do not redo work", "Integrated")
    m.world = World(existing_files=["out/note-a.md"])
    _engine(tmp_path).run_task(m, context=TWO)
    assert m.state.worker_count() == 0
    assert "covers note-a" in m.notes["question-1"].reason


def test_illegal_proposals_never_grow_the_roster(tmp_path: Path):
    m = new_run("ms-6", "E", "P", "S")
    _engine(tmp_path).run_task(m, context="subtask:verify=x subtask:lead-plan=y subtask:a@juggle=z subtask:b=")
    assert m.state.worker_count() == 0
    assert not any(e.event == "split" for e in m.log)


def test_failed_check_replans_the_method_once(tmp_path: Path):
    replies = [
        _reply("Read: a single agent is enough."),
        _reply("A draft that forgets the point."),
        _reply("FAIL: criteria missing"),
        _reply("Reworked: default task done, purpose held."),
        _reply("PASS"),
    ]
    m = new_run("ad-1", "E", "P", "S")
    Engine(MemoryStore(tmp_path), adapter=ScriptedLive(replies), budget=Budget.for_tier("normal")).run_task(
        m, context="one source")
    assert m.status.value == "complete"
    assert m.notes["replan"].response == "CHANGE_METHOD"
    assert m.state.method.startswith("rework the product")
    assert [c["mode"] for c in m.calls] == ["plan", "work", "verify", "rework", "verify"]


def test_tight_does_not_replan(tmp_path: Path):
    replies = [_reply("Read: a single agent is enough."), _reply("A draft that forgets the point."), _reply("FAIL")]
    m = new_run("ad-2", "E", "P", "S")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=ScriptedLive(replies), budget=Budget.for_tier("tight")).run_task(
            m, context="one source")
    assert m.status.value == "abort"
    assert "replan" not in m.notes


# --- sub-agents run at the same time ---


class Rendezvous(StubAdapter):
    """Both sub-agents must be in flight together, or the barrier breaks. A finishes last."""

    def __init__(self):
        self.barrier = threading.Barrier(2, timeout=5)

    def act(self, brief):
        if brief.slot_function == "worker":
            self.barrier.wait()
            if brief.channel_id == "note-a":
                time.sleep(0.05)
        return super().act(brief)


def test_sub_agents_run_concurrently_and_report_in_order(tmp_path: Path):
    m = new_run("cc-1", "Answer two notes", "Do not mix", "Integrated")
    Engine(MemoryStore(tmp_path), adapter=Rendezvous(), budget=Budget.for_tier("open"), isolation_required=True).run_task(m, context=TWO)
    worker_arts = [a.channel_id for a in m.artifacts if a.channel_id.startswith("note")]
    assert worker_arts == ["note-a", "note-b"]
    # plan + 2 sub-agents x (tool round + product) + merge + verify
    assert len(m.calls) == 7
    assert diagnose(m)["isolation"]["flags"] == []


def test_sequential_mode_still_works(tmp_path: Path):
    m = new_run("cc-2", "Answer two notes", "Do not mix", "Integrated")
    _engine(tmp_path, parallel=False, isolation_required=True).run_task(m, context=TWO)
    assert m.state.worker_count() == 2


def test_usage_is_per_thread():
    live = LiveAdapter("https://example.invalid", "k", "m")
    live.last_usage = {"prompt_tokens": 1}
    seen = {}
    t = threading.Thread(target=lambda: seen.setdefault("other", live.last_usage))
    t.start()
    t.join()
    assert seen["other"] == {}
    assert live.last_usage == {"prompt_tokens": 1}


# --- live adapter prompts ---


def _brief(function, skill="execute", channel="", tools=None, mode=""):
    return Brief(slot_function=function, skill=skill, packet="p", goal="e", purpose="p", context="here",
                 done_when="there", channel_id=channel, tools=tools or [], mode=mode)


def test_system_prompt_fits_role_and_specialty():
    assert "lead" in system_prompt(_brief("lead"))
    assert "Worker" not in system_prompt(_brief("lead"))
    worker = system_prompt(_brief("worker", "retrieve", "note-a", ["retrieve", "read"]))
    assert "note-a" in worker and "Search before you claim" in worker and '"retrieve:' in worker
    assert "no tools" in system_prompt(_brief("verifier", "verify", tools=["verify"]))


def test_model_per_skill(monkeypatch):
    monkeypatch.setenv("TASKORG_MODEL_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("TASKORG_MODEL_KEY", "test-key")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "base-model")
    monkeypatch.setenv("TASKORG_MODEL_NAME_REASON", "deep-model")
    live = LiveAdapter.from_env()
    assert live._payload(_brief("lead", "reason"))["model"] == "deep-model"
    assert live._payload(_brief("worker", "retrieve"))["model"] == "base-model"
    assert json.loads(live._payload(_brief("lead", mode="plan"))["messages"][1]["content"])["mode"] == "plan"


# --- CLI ---


def test_cli_run(tmp_path: Path, capsys):
    ws = _workspace(tmp_path)
    out = tmp_path / "ms.json"
    rc = main(["run", "--tier", "open", "--isolate", "--workspace", str(ws), "--store", str(tmp_path / "data"),
               "--out", str(out), "--context", TWO])
    assert rc == 0
    printed = capsys.readouterr().out
    assert '"legal": true' in printed
    assert load_run(out).state.worker_count() == 2


def test_cli_missing_workspace(tmp_path: Path, capsys):
    rc = main(["run", "--workspace", str(tmp_path / "nope"), "--store", str(tmp_path), "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "READ" in capsys.readouterr().out
