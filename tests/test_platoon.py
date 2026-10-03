"""Specialists, sandboxed tools, lead-driven task organization, concurrent elements."""

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
from taskorg.factory import element_at_rest
from taskorg.gates import Seam, World, assess
from taskorg.live import LiveAdapter, ScriptedLive, system_prompt
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import QUALS
from taskorg.persist import load_mission
from taskorg.quals import ROLE
from taskorg.seams import parse_seams
from taskorg.tools import Toolbox

TWO = "Two notes. seam:note-a@retrieve=sources_must_not_mix seam:note-b@retrieve=sources_must_not_mix"


def _engine(tmp_path: Path, pace: str = "run", **kw) -> Engine:
    return Engine(MemoryStore(tmp_path / "store"), budget=Budget.for_pace(pace), **kw)


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "note-a.md").write_text("Q3 revenue was 4.1M.\nQ3 churn was 2 percent.\n")
    (ws / "note-b.md").write_text("Hiring plan: 3 engineers.\n")
    return ws


def _reply(claim, evidence=(), requests=()):
    return json.dumps({
        "claim": claim, "evidence": list(evidence), "uncertainty": "script",
        "channel_id": "x", "delta_to_picture": "", "requests": list(requests),
    })


# --- qualifications and seams ---


def test_every_qualification_has_a_role():
    assert set(ROLE) == set(QUALS)


def test_seam_names_its_specialty():
    seams = parse_seams("seam:a@retrieve=must_not_mix seam:b=plain_split")
    assert [(s.channel_id, s.skill, s.named_failure) for s in seams] == [
        ("a", "retrieve", "must not mix"),
        ("b", "execute", "plain split"),
    ]


# --- gates ---


def _verdict(verdicts, channel):
    return next(v for v in verdicts if v.seam.channel_id == channel)


def test_two_independent_parts_are_legal():
    verdicts = assess([Seam("a", "mix"), Seam("b", "mix")])
    assert all(v.legal for v in verdicts)
    for v in verdicts:
        v.gates.assert_legal()


def test_one_open_part_is_the_leads_job():
    [v] = assess([Seam("a", "mix")])
    assert v.gate == "can_someone_else"
    assert v.gates.can_someone_else is True


def test_world_cover_leaves_one_open_part_for_the_lead():
    verdicts = assess([Seam("a", "mix"), Seam("b", "mix")], world=World(existing_files=["out/a.md"]))
    assert "covers a" in _verdict(verdicts, "a").refused
    assert _verdict(verdicts, "b").refused.startswith("one open seam")


def test_each_gate_refuses_in_order():
    verdicts = assess([
        Seam("dup", "x"), Seam("dup", "x"),
        Seam("silent", ""),
        Seam("odd", "x", skill="juggle"),
        Seam("verify", "x"),
        Seam("checker", "x", skill="verify"),
        Seam("ok-1", "x"), Seam("ok-2", "x"),
    ])
    assert _verdict(verdicts[1:], "dup").gate == "can_someone_else"
    assert _verdict(verdicts, "silent").gate == "should_we"
    assert _verdict(verdicts, "odd").gate == "could_we"
    assert "reserved" in _verdict(verdicts, "verify").refused
    assert _verdict(verdicts, "checker").gate == "can_someone_else"
    assert [v.seam.channel_id for v in verdicts if v.legal] == ["dup", "ok-1", "ok-2"]


def test_pace_refuses_the_split():
    verdicts = assess([Seam("a", "x"), Seam("b", "x")], allow_split=False, pace="crawl")
    assert not any(v.legal for v in verdicts)
    assert all("pace crawl" in v.refused for v in verdicts)


def test_budget_pays_for_some_elements_or_none():
    three = [Seam("a", "x"), Seam("b", "x"), Seam("c", "x")]
    partial = assess(three, calls_left=4, calls_after_split=2)
    assert [v.legal for v in partial] == [True, True, False]
    none = assess(three, calls_left=3, calls_after_split=2)
    assert not any(v.legal for v in none)
    costly = assess(three, calls_left=8, calls_after_split=2, element_cost=lambda s: 3)
    assert [v.legal for v in costly] == [True, True, False]


def test_worker_cap_holds():
    verdicts = assess([Seam(c, "x") for c in "abcdef"], worker_slots_left=4)
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
    m = element_at_rest("tl-1", "Answer two notes", "Do not mix", "Integrated")
    _engine(tmp_path, toolbox=Toolbox(roots=[ws])).run_mission(m, look_update=TWO)
    tools = [e.detail for e in m.log if e.event == "tool"]
    assert {t["channel"] for t in tools} == {"note-a", "note-b"}
    a = next(x for x in m.artifacts if x.channel_id == "note-a")
    assert any("4.1M" in ev for ev in a.evidence)
    assert not any("Hiring" in ev for ev in a.evidence)


class AsksForRead(StubAdapter):
    def act(self, brief):
        art = super().act(brief)
        if brief.slot_function == "head" and brief.mode == "work":
            art.requests = ["read:note-a.md"]
        return art


def test_tool_outside_allowlist_never_runs(tmp_path: Path):
    m = element_at_rest("tl-2", "E", "P", "S")
    eng = Engine(MemoryStore(tmp_path / "s"), adapter=AsksForRead(), budget=Budget.for_pace("run"))
    with pytest.raises(InvariantError) as e:
        eng.run_mission(m, look_update="one source")  # no workspace: the lead drafts, draft has no read
    assert e.value.code == "TOOLS"
    assert not any(ev.event == "tool" for ev in m.log)


class AlwaysWantsMore(StubAdapter):
    def act(self, brief):
        art = super().act(brief)
        if brief.slot_function == "head" and brief.mode == "work":
            art.requests = ["retrieve:more"]
        return art


def test_tool_rounds_are_capped(tmp_path: Path):
    ws = _workspace(tmp_path)
    m = element_at_rest("tl-3", "E", "P", "S")
    eng = Engine(MemoryStore(tmp_path / "s"), adapter=AlwaysWantsMore(), budget=Budget.for_pace("run"),
                 toolbox=Toolbox(roots=[ws]), max_tool_rounds=2)
    eng.run_mission(m, look_update="one source")
    work_calls = [c for c in m.calls if c.get("mode") == "work"]
    assert len(work_calls) == 3  # first call + two tool rounds
    assert any(e.event == "tool_rounds_exhausted" for e in m.log)


# --- the lead organizes the team ---


def test_one_body_when_nothing_is_independent(tmp_path: Path):
    m = element_at_rest("ms-1", "Summarize the paragraph", "One reading", "One sentence")
    result = _engine(tmp_path, "crawl").run_mission(m, look_update="One paragraph is the whole picture.")
    assert result.mission.status.value == "complete"
    assert m.picture.worker_count() == 0
    assert m.notes["why-1"].reason.startswith("one body")
    assert len(m.calls) == 3  # plan, work, verify
    assert diagnose(m)["health"] == "ok"


def test_lead_splits_into_specialists_and_regroups(tmp_path: Path):
    m = element_at_rest("ms-2", "Answer two notes", "Do not mix", "Integrated")
    result = _engine(tmp_path, toolbox=Toolbox(roots=[_workspace(tmp_path)])).run_mission(m, look_update=TWO)
    assert result.split is True
    assert result.channels == ["note-a", "note-b"]
    assert {s.skill for s in m.picture.slots if s.function == "worker"} == {"retrieve"}
    splits = [e.detail for e in m.log if e.event == "split"]
    assert [s["gates"]["channel_id"] for s in splits] == ["note-a", "note-b"]
    assert sum(1 for e in m.log if e.event == "gate") == 2
    report = diagnose(m)
    assert report["health"] == "ok", report["flags"]
    assert m.notes["why-1"].reason == "2 elements: note-a, note-b"


def test_one_open_part_cross_trains_the_lead(tmp_path: Path):
    m = element_at_rest("ms-3", "Find the number", "One source", "Number stated")
    _engine(tmp_path, "crawl", toolbox=Toolbox(roots=[_workspace(tmp_path)])).run_mission(
        m, look_update="seam:note-a@retrieve=needs_search")
    assert m.picture.worker_count() == 0
    assert m.picture.slot("head-1").skill == "retrieve"
    assert any(e.event == "tool" for e in m.log)
    assert "the lead covers it" in m.notes["why-1"].reason


def test_crawl_holds_one_body_even_with_two_parts(tmp_path: Path):
    m = element_at_rest("ms-4", "Answer two notes", "Do not mix", "Integrated")
    _engine(tmp_path, "crawl").run_mission(m, look_update=TWO)
    assert m.picture.worker_count() == 0
    assert "pace crawl does not allow a split" in m.notes["why-1"].reason
    assert "crawl_split" not in diagnose(m)["flags"]


def test_existing_file_keeps_it_to_one_body(tmp_path: Path):
    m = element_at_rest("ms-5", "Answer two notes", "Do not redo work", "Integrated")
    m.world = World(existing_files=["out/note-a.md"])
    _engine(tmp_path).run_mission(m, look_update=TWO)
    assert m.picture.worker_count() == 0
    assert "covers note-a" in m.notes["why-1"].reason


def test_illegal_proposals_never_grow_the_roster(tmp_path: Path):
    m = element_at_rest("ms-6", "E", "P", "S")
    _engine(tmp_path).run_mission(m, look_update="seam:verify=x seam:head-plan=y seam:a@juggle=z seam:b=")
    assert m.picture.worker_count() == 0
    assert not any(e.event == "split" for e in m.log)


def test_failed_check_adapts_the_method_once(tmp_path: Path):
    replies = [
        _reply("Read: one body."),
        _reply("A draft that forgets the point."),
        _reply("FAIL: criteria missing"),
        _reply("Reworked: default task done, purpose held."),
        _reply("PASS"),
    ]
    m = element_at_rest("ad-1", "E", "P", "S")
    Engine(MemoryStore(tmp_path), adapter=ScriptedLive(replies), budget=Budget.for_pace("walk")).run_mission(
        m, look_update="one source")
    assert m.status.value == "complete"
    assert m.notes["plan-wrong"].response == "CHANGE_METHOD"
    assert m.picture.method.startswith("rework the product")
    assert [c["mode"] for c in m.calls] == ["plan", "work", "verify", "rework", "verify"]


def test_crawl_does_not_adapt(tmp_path: Path):
    replies = [_reply("Read: one body."), _reply("A draft that forgets the point."), _reply("FAIL")]
    m = element_at_rest("ad-2", "E", "P", "S")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=ScriptedLive(replies), budget=Budget.for_pace("crawl")).run_mission(
            m, look_update="one source")
    assert m.status.value == "abort"
    assert "plan-wrong" not in m.notes


# --- elements run at the same time ---


class Rendezvous(StubAdapter):
    """Both elements must be in flight together, or the barrier breaks. A finishes last."""

    def __init__(self):
        self.barrier = threading.Barrier(2, timeout=5)

    def act(self, brief):
        if brief.slot_function == "worker":
            self.barrier.wait()
            if brief.channel_id == "note-a":
                time.sleep(0.05)
        return super().act(brief)


def test_elements_run_concurrently_and_report_in_order(tmp_path: Path):
    m = element_at_rest("cc-1", "Answer two notes", "Do not mix", "Integrated")
    Engine(MemoryStore(tmp_path), adapter=Rendezvous(), budget=Budget.for_pace("run")).run_mission(m, look_update=TWO)
    worker_arts = [a.channel_id for a in m.artifacts if a.channel_id.startswith("note")]
    assert worker_arts == ["note-a", "note-b"]
    # plan + 2 elements x (tool round + product) + integrate + verify
    assert len(m.calls) == 7
    assert diagnose(m)["isolation"]["flags"] == []


def test_sequential_mode_still_works(tmp_path: Path):
    m = element_at_rest("cc-2", "Answer two notes", "Do not mix", "Integrated")
    _engine(tmp_path, parallel=False).run_mission(m, look_update=TWO)
    assert m.picture.worker_count() == 2


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
    return Brief(slot_function=function, skill=skill, packet="p", effect="e", purpose="p", picture="here",
                 end_state="there", channel_id=channel, tools=tools or [], mode=mode)


def test_system_prompt_fits_role_and_specialty():
    assert "lead" in system_prompt(_brief("head"))
    assert "Worker" not in system_prompt(_brief("head"))
    worker = system_prompt(_brief("worker", "retrieve", "note-a", ["retrieve", "read"]))
    assert "note-a" in worker and "Search before you claim" in worker and '"retrieve:' in worker
    assert "no tools" in system_prompt(_brief("verifier", "verify", tools=["verify"]))


def test_model_per_qualification(monkeypatch):
    monkeypatch.setenv("TASKORG_MODEL_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("TASKORG_MODEL_KEY", "test-key")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "base-model")
    monkeypatch.setenv("TASKORG_MODEL_NAME_REASON", "deep-model")
    live = LiveAdapter.from_env()
    assert live._payload(_brief("head", "reason"))["model"] == "deep-model"
    assert live._payload(_brief("worker", "retrieve"))["model"] == "base-model"
    assert json.loads(live._payload(_brief("head", mode="plan"))["messages"][1]["content"])["mode"] == "plan"


# --- CLI ---


def test_cli_mission(tmp_path: Path, capsys):
    ws = _workspace(tmp_path)
    out = tmp_path / "ms.json"
    rc = main(["mission", "--pace", "run", "--workspace", str(ws), "--store", str(tmp_path / "data"),
               "--out", str(out), "--look", TWO])
    assert rc == 0
    printed = capsys.readouterr().out
    assert '"legal": true' in printed
    assert load_mission(out).picture.worker_count() == 2


def test_cli_missing_workspace(tmp_path: Path, capsys):
    rc = main(["mission", "--workspace", str(tmp_path / "nope"), "--store", str(tmp_path), "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "READ" in capsys.readouterr().out
