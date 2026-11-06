"""What the held-out run asked of the kernel, and the benches that test it.

A round of tools fits the call that must carry it. A rework hears why the verifier failed the product. The lead and
sub-agents can be told how to read a line with no year. And two benches: files where a heading does not hold for every
line, and the tapes' reworks asked again. What a real model does with any of this is for a live run.
"""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from taskorg import checks, rework_bench as rb, verify_bench as vb
from taskorg.adapters import TOOL_RESULTS, ModelAdapter
from taskorg.anthropic_live import AnthropicAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.compare import comparison_budget, run_trial
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.live import LiveAdapter
from taskorg.loop import MAX_TOOL_REQUESTS, REWORK_HEAD, REWORK_REASON_CHARS, ROUND_CUT, Engine, rework_said
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.sim import SimModel
from taskorg.suite import build_suite, slug
from taskorg.tape import Player, replay_adapter
from taskorg.tools import Toolbox


def _art(claim="ANSWER: 1", requests=()):
    return Artifact(claim=claim, evidence=["e"], uncertainty="u", channel_id="", context_update="", requests=list(requests))


class Scripted(ModelAdapter):
    """Replies in turn, or what a callable makes of the brief. Each brief is kept."""

    name = "scripted"

    def __init__(self, *replies, reply_tokens=10):
        self.replies, self.briefs = list(replies), []
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": reply_tokens}

    def act(self, brief):
        self.briefs.append(brief)
        reply = self.replies.pop(0) if self.replies else _art()
        return reply(brief) if callable(reply) else reply


def _run(name="r"):
    run = new_run(name, goal="g", purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    return run


def _files(tmp_path: Path, **sizes) -> Path:
    root = tmp_path / "files"
    root.mkdir(exist_ok=True)
    for name, size in sizes.items():
        (root / f"{name}.md").write_text("x" * size)
    return root


def _lead_reads(engine, run):
    """The lead's brief with its reading tools on, as a lead working alone has them."""
    run.switch_skill(run.state.lead_id, run.state.lead_id, "retrieve", "read")
    return engine._brief(run, "lead", extra="WORK.", mode="work")


def _act(tmp_path, adapter, root, cap=1_000, rounds=2):
    run = _run()
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, budget=Budget(max_tokens_per_call=cap), toolbox=Toolbox(roots=[root]),
                    max_tool_rounds=rounds)
    engine._arm(run)
    return run, engine._act(run, _lead_reads(engine, run))


# --- a round of tools fits the call that must carry it ---


def test_what_a_round_returns_stops_at_what_the_next_call_can_carry(tmp_path: Path):
    root = _files(tmp_path, a=1_200, b=1_200, c=1_200, d=1_200)
    adapter = Scripted(_art("reading", ["read:a.md", "read:b.md", "read:c.md", "read:d.md"]), _art("ANSWER: 2"))
    run, product = _act(tmp_path, adapter, root, cap=800)
    assert product.claim == "ANSWER: 2"
    sent = adapter.briefs[1].packet
    assert "[read a.md]" in sent and "[read b.md]" in sent and "[read c.md]" not in sent and "[read d.md]" not in sent
    assert ROUND_CUT.format(n=2) in sent
    assert adapter.estimate_tokens(adapter.briefs[1]) <= 800
    # The record says what the call saw, and what it did not.
    assert [e.detail["request"] for e in run.log if e.event == "tool"] == ["read:a.md", "read:b.md"]
    cut = [e.detail for e in run.log if e.event == "tool_round_cut"]
    assert len(cut) == 1 and cut[0]["not_run"] == ["read:c.md", "read:d.md"] and cut[0]["slot"] == "lead"


def test_a_round_that_fits_is_not_touched(tmp_path: Path):
    root = _files(tmp_path, a=800, b=800)
    adapter = Scripted(_art("reading", ["read:a.md", "read:b.md"]), _art("ANSWER: 2"))
    run, _ = _act(tmp_path, adapter, root, cap=800)
    assert "no room" not in adapter.briefs[1].packet and not [e for e in run.log if e.event == "tool_round_cut"]
    assert [e.detail["request"] for e in run.log if e.event == "tool"] == ["read:a.md", "read:b.md"]


def test_a_run_goes_on_when_nothing_in_a_round_fits(tmp_path: Path):
    root = _files(tmp_path, a=3_900)
    adapter = Scripted(_art("reading", ["read:a.md"]), _art("ANSWER: 2"))
    run, product = _act(tmp_path, adapter, root, cap=300)
    assert product.claim == "ANSWER: 2" and ROUND_CUT.format(n=1) in adapter.briefs[1].packet and "[read a.md]" not in adapter.briefs[1].packet
    assert not [e for e in run.log if e.event == "tool"]


def test_a_file_cut_from_one_round_is_not_counted_as_held_in_the_next(tmp_path: Path):
    """A file read in full is not searched again: true only of a file the call was shown."""
    root = _files(tmp_path, a=1_200, b=1_200)
    (root / "b.md").write_text("needle " + "x" * 1_200)
    adapter = Scripted(_art("reading", ["read:a.md", "read:b.md"]), _art("searching", ["retrieve:needle"]), _art("ANSWER: 2"))
    run, _ = _act(tmp_path, adapter, root, cap=500)
    # The search finds b.md, which the first round cut: its result is no room again or the line, never "read in full above".
    assert "read in full above" not in adapter.briefs[2].packet
    assert "already in full above" not in adapter.briefs[2].packet


class RoomyRound(Scripted):
    """An adapter that has measured what a lead's reply needs after a round."""

    round_reply_tokens = 300


def _script():
    return _art("reading", ["read:a.md", "read:b.md", "read:c.md", "read:d.md"]), _art("ANSWER: 2")


def test_a_cut_round_gives_back_reads_until_a_lead_has_room_to_reply(tmp_path: Path):
    """On the tapes a call that merely fit left 700 tokens after a cut, and thinking took them all: an empty reply."""
    root = _files(tmp_path, a=1_200, b=1_200, c=1_200, d=1_200)
    (tmp_path / "p").mkdir()
    (tmp_path / "r").mkdir()
    plain, roomy = Scripted(*_script()), RoomyRound(*_script())
    _act(tmp_path / "p", plain, root, cap=800)
    run, product = _act(tmp_path / "r", roomy, root, cap=800)
    assert product.claim == "ANSWER: 2"
    assert plain.briefs[1].packet.count("[read ") == 2
    sent = roomy.briefs[1].packet
    assert "[read a.md]" in sent and "[read b.md]" not in sent and ROUND_CUT.format(n=3) in sent
    assert roomy.estimate_tokens(roomy.briefs[1]) + roomy.round_reply_tokens <= 800
    # The record says what the call saw and what it did not: a read given back is not a read.
    assert [e.detail["request"] for e in run.log if e.event == "tool"] == ["read:a.md"]
    cut = [e.detail for e in run.log if e.event == "tool_round_cut"]
    assert len(cut) == 1 and cut[0]["not_run"] == ["read:b.md", "read:c.md", "read:d.md"]


def test_a_round_that_fits_keeps_every_read_whatever_a_cut_would_leave(tmp_path: Path):
    """The room is for a lead told of a cut. On the tapes a lead told of none rarely ran out with far less."""
    root = _files(tmp_path, a=800, b=800)
    adapter = RoomyRound(_art("reading", ["read:a.md", "read:b.md"]), _art("ANSWER: 2"))
    adapter.round_reply_tokens = 700
    run, _ = _act(tmp_path, adapter, root, cap=800)
    assert "no room" not in adapter.briefs[1].packet and not [e for e in run.log if e.event == "tool_round_cut"]
    assert [e.detail["request"] for e in run.log if e.event == "tool"] == ["read:a.md", "read:b.md"]


def test_a_read_given_back_is_not_held_in_the_next_round(tmp_path: Path):
    """A file read in full is not searched again: true only of a file the call was shown."""
    root = _files(tmp_path, a=1_200, b=1_200, c=1_200, d=1_200)
    (root / "b.md").write_text("needle " + "x" * 1_200)
    adapter = RoomyRound(_art("reading", ["read:a.md", "read:b.md", "read:c.md", "read:d.md"]), _art("searching", ["retrieve:needle"]), _art("ANSWER: 2"))
    run, _ = _act(tmp_path, adapter, root, cap=800)
    assert "[read b.md]" not in adapter.briefs[1].packet
    # The search leaves out what the call was shown, a.md, and only that.
    assert "1 file(s) read in full above" in adapter.briefs[2].packet


def test_a_cut_round_with_nothing_to_give_back_still_goes_on(tmp_path: Path):
    root = _files(tmp_path, a=3_900)
    adapter = RoomyRound(_art("reading", ["read:a.md"]), _art("ANSWER: 2"))
    _, product = _act(tmp_path, adapter, root, cap=500)
    assert product.claim == "ANSWER: 2" and ROUND_CUT.format(n=1) in adapter.briefs[1].packet


def _overflow_edge(tmp_path: Path, slack: int):
    """A run and a brief whose next call, carrying one result, has `slack` tokens of room under the cap."""
    (tmp_path / "s0").mkdir()
    probe = Engine(MemoryStore(tmp_path / "s0"), adapter=RoomyRound(), budget=Budget(max_tokens_per_call=8_000), toolbox=Toolbox(roots=[tmp_path]))
    run = _run()
    probe._arm(run)
    brief = _lead_reads(probe, run)
    note = ROUND_CUT.format(n=MAX_TOOL_REQUESTS)
    size = probe.adapter.estimate_tokens(replace(brief, packet=f"{brief.packet}\n{TOOL_RESULTS}\n" + "\n\n".join(["r", note])))
    run = _run()
    engine = Engine(MemoryStore(tmp_path / "s1"), adapter=RoomyRound(), budget=Budget(max_tokens_per_call=size + slack), toolbox=Toolbox(roots=[tmp_path]))
    engine._arm(run)
    return engine, run, _lead_reads(engine, run)


def test_a_leads_round_keeps_exactly_the_room_the_adapter_asks_for(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    engine, run, brief = _overflow_edge(tmp_path / "a", 300)
    assert engine._round_overflows(run, brief, ["r"], None, cut=True) is False
    engine, run, brief = _overflow_edge(tmp_path / "b", 299)
    assert engine._round_overflows(run, brief, ["r"], None, cut=True) is True
    # A round not being cut asks only what any call asks.
    assert engine._round_overflows(run, brief, ["r"], None) is False


def test_a_sub_agents_round_keeps_its_own_room_and_not_a_leads(tmp_path: Path):
    """The gates sized a sub-agent's part by its own room, so a lead's would cut files they admitted."""
    engine, run, brief = _overflow_edge(tmp_path, 100)
    worker = SimpleNamespace(id="w1", function="worker")
    assert engine._round_overflows(run, brief, ["r"], worker, cut=True) is False
    assert engine._round_overflows(run, brief, ["r"], None, cut=True) is True


def test_the_reply_room_of_a_call_with_no_round_does_not_change(tmp_path: Path):
    """The setting cuts rounds. A call sent as it stands goes as it did, so a tape's other calls stay what they were."""
    (tmp_path / "s0").mkdir()
    measure = RoomyRound()
    engine = Engine(MemoryStore(tmp_path / "s0"), adapter=measure, budget=Budget(max_tokens_per_call=8_000), toolbox=Toolbox(roots=[tmp_path]))
    run = _run()
    engine._arm(run)
    size = measure.estimate_tokens(_lead_reads(engine, run))
    assert engine._reply_room(run) == 0
    adapter = RoomyRound(_art("ANSWER: 2"))
    root = _files(tmp_path, a=10)
    _, product = _act(tmp_path, adapter, root, cap=size + 20)
    assert product.claim == "ANSWER: 2" and len(adapter.briefs) == 1


def test_claude_keeps_what_the_tapes_measured_and_the_others_keep_nothing():
    assert AnthropicAdapter.round_reply_tokens == 3_000 and LiveAdapter.round_reply_tokens == 0 and SimModel.round_reply_tokens == 0
    assert AnthropicAdapter("", "m", client=object()).tape_header()["round_reply_tokens"] == 3_000


def _tape_with(tmp_path: Path, **header) -> Path:
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m"} | header) + "\n")
    return path


def test_a_replay_keeps_what_its_tape_kept(tmp_path: Path):
    assert replay_adapter(Player(_tape_with(tmp_path, round_reply_tokens=3_000))).round_reply_tokens == 3_000
    assert replay_adapter(Player(_tape_with(tmp_path, round_reply_tokens=2_500))).round_reply_tokens == 2_500
    # A tape older than the setting replays as it ran, whatever today's code keeps.
    assert replay_adapter(Player(_tape_with(tmp_path))).round_reply_tokens == 0


@pytest.mark.parametrize("bad", [-1, True, "3000", 3_000.0, [3_000]])
def test_a_tape_cannot_say_anything_of_its_rounds(tmp_path: Path, bad):
    with pytest.raises(InvariantError):
        Player(_tape_with(tmp_path, round_reply_tokens=bad))


@pytest.mark.parametrize("size", range(1_000, 1_500, 7))
def test_the_room_for_a_cut_note_and_a_reply_is_kept_at_every_size(tmp_path: Path, size: int):
    """Near the cap a result fits only without the note, or only without the reply. Neither may stop the run."""
    root = _files(tmp_path, a=size, b=1_200)
    adapter = Scripted(_art("reading", ["read:a.md", "read:b.md"]), _art("ANSWER: 2"), reply_tokens=40)
    run, product = _act(tmp_path, adapter, root, cap=400)
    assert product.claim == "ANSWER: 2"
    assert all(adapter.estimate_tokens(b) + 40 <= 400 for b in adapter.briefs[1:])


def test_a_run_with_no_budget_is_not_cut(tmp_path: Path):
    root = _files(tmp_path, a=3_000, b=3_000)
    adapter = Scripted(_art("reading", ["read:a.md", "read:b.md"]), _art("ANSWER: 2"))
    run = _run()
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, toolbox=Toolbox(roots=[root]), max_tool_rounds=2)
    run.budget = None
    engine._act(run, _lead_reads(engine, run))
    assert "no room" not in adapter.briefs[1].packet and "[read b.md]" in adapter.briefs[1].packet


def test_a_note_about_too_many_requests_still_comes_first(tmp_path: Path):
    root = _files(tmp_path, **{f"f{i}": 10 for i in range(MAX_TOOL_REQUESTS + 2)})
    adapter = Scripted(_art("reading", [f"read:f{i}.md" for i in range(MAX_TOOL_REQUESTS + 2)]), _art("ANSWER: 2"))
    _act(tmp_path, adapter, root, cap=8_000)
    assert f"{TOOL_RESULTS}\n[2 more tool requests not run" in adapter.briefs[1].packet


# --- a rework hears why ---


def _rework(tmp_path, said, **engine):
    adapter = Scripted(_art("ANSWER: 1"), _art(said), _art("ANSWER: 2"), _art("PASS. Fine."))
    run = _run()
    e = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, budget=Budget(max_calls=20, allow_adapt=True), **engine)
    e._arm(run)
    product = e._act(run, e._brief(run, "lead", extra="WORK.", mode="work"))
    run.accept_artifact(product)
    e._verify(run, product, adapt=True)
    return next(b for b in adapter.briefs if b.mode == "rework")


def test_a_rework_brief_says_what_the_verifier_said(tmp_path: Path):
    said = "FAIL: bellmoor.md says Q3 revenue was 12.0, and the product says 13.0."
    brief = _rework(tmp_path, said)
    assert f"{REWORK_HEAD}It said: {said} Misses: " in brief.packet


def test_what_a_rework_hears_is_bounded(tmp_path: Path):
    brief = _rework(tmp_path, "FAIL: " + "y" * (REWORK_REASON_CHARS * 3))
    assert brief.packet.count("y") <= REWORK_REASON_CHARS + 400
    assert rework_said("FAIL " + "y" * 9_999) == f"It said: {('FAIL ' + 'y' * 9_999)[:REWORK_REASON_CHARS]} "


def test_older_tapes_get_the_brief_they_recorded(tmp_path: Path):
    brief = _rework(tmp_path, "FAIL: a reason.", rework_reason=False)
    assert f"{REWORK_HEAD}Misses: " in brief.packet and "a reason" not in brief.packet.split("Misses: ")[0]


def test_the_reason_is_on_by_default():
    assert Engine(MemoryStore(Path("/tmp/never-written"))).rework_reason is True


# --- the lead and sub-agents told how to read an undated line ---


def test_authors_are_told_when_asked_and_a_plan_and_the_verifier_are_not(tmp_path: Path):
    note = checks.AUTHOR_RULES["headed"]
    assert note == checks.HEADING_RULE.strip() and checks.AUTHOR_RULES["none"] == ""
    run = _run()
    plain = Engine(MemoryStore(tmp_path / "a"))
    told = Engine(MemoryStore(tmp_path / "b"), author_note=note)
    assert plain.author_note == ""
    for engine in (plain, told):
        engine.store.remember_working(run.id, "context", "c")
    for mode in ("work", "integrate", "rework"):
        brief = told._brief(run, "lead", extra="WORK.", mode=mode)
        assert note in brief.packet and "WORK." in brief.packet and brief.packet.count(note) == 1, mode
        assert note not in plain._brief(run, "lead", extra="WORK.", mode=mode).packet
    assert note in told._brief(run, "lead", mode="work").packet
    assert note not in told._brief(run, "lead", extra="PLAN.", mode="plan").packet
    assert note not in told._brief(run, "verifier", extra="P", mode="verify").packet.replace(checks.SOURCE_RULE, "")


def test_a_sub_agent_is_told_too(tmp_path: Path):
    suite = build_suite(seed=101, per_family=1, families=("aggregate",), entities=10, distractors=6)
    corpus = suite.write_corpus(tmp_path / "corpus")
    note = checks.AUTHOR_RULES["headed"]
    seen = []

    class Sees(SimModel):
        def act(self, brief):
            seen.append(brief)
            return super().act(brief)

    run_trial(suite.tasks[0], "always-told", Sees(), corpus, budget=comparison_budget(40, 8_000), verify={"author_note": note, "verify_note": ""})
    workers = [b for b in seen if b.slot_function == "worker"]
    assert workers and all(note in b.packet for b in workers)
    assert not any(note in b.packet for b in seen if b.mode == "plan" or b.slot_function == "verifier")


def _engines(monkeypatch):
    from taskorg import cli

    given, real = [], cli.Engine

    def spy(*args, **kwargs):
        given.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(cli, "Engine", spy)
    return given


def test_a_run_takes_both_switches(tmp_path: Path, monkeypatch):
    given = _engines(monkeypatch)
    base = ["run", "--store", str(tmp_path / "s"), "--out", str(tmp_path / "o.json")]
    assert main(base) == 0 and main([*base, "--no-rework-reason", "--author-rule", "headed"]) == 0
    assert given[0]["rework_reason"] is True and given[0]["author_note"] == ""
    assert given[1]["rework_reason"] is False and given[1]["author_note"] == checks.AUTHOR_RULES["headed"]


def test_compare_takes_both_switches_and_records_them(tmp_path: Path, monkeypatch):
    from taskorg import compare as compare_module

    seen, real = [], compare_module.run_comparison

    def spy(*args, **kwargs):
        seen.append(kwargs["verify"])
        return real(*args, **kwargs)

    monkeypatch.setattr(compare_module, "run_comparison", spy)
    base = ["compare", "--adapter", "sim", "--per-family", "1", "--families", "lookup", "--strategies", "single"]
    assert main([*base, "--out", str(tmp_path / "a.json")]) == 0
    assert main([*base, "--no-rework-reason", "--author-rule", "headed", "--out", str(tmp_path / "b.json")]) == 0
    assert seen[0]["rework_reason"] is True and seen[0]["author_note"] == ""
    assert seen[1]["rework_reason"] is False and seen[1]["author_note"] == checks.AUTHOR_RULES["headed"]
    a, b = (json.loads((tmp_path / f"{n}.json").read_text())["config"] for n in "ab")
    assert (a["rework_reason"], a["author_rule"]) == (True, "none") and (b["rework_reason"], b["author_rule"]) == (False, "headed")


def test_replaying_a_tape_says_when_the_switches_differ(tmp_path: Path, capsys):
    tape = tmp_path / "t.jsonl"
    settings = {"strategies": ["single"], "families": ["lookup"], "per_family": 1, "repeat": 1, "seed": 7, "entities": None,
                "distractors": 0, "filed": 0, "max_calls_per_trial": 40, "context_tokens": 16_000, "tool_rounds": 3,
                "verify_view": "independent", "verify_sources": "layered", "verify_rule": "both"}
    base = ["compare", "--replay", str(tape), "--per-family", "1", "--families", "lookup", "--strategies", "single"]
    # A tape from before the switch was recorded with no reason in the brief.
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m", "models": {}, "compare": settings}) + "\n")
    assert main([*base, "--out", str(tmp_path / "a.json")]) == 0
    assert "different rework_reason" in capsys.readouterr().err
    assert main([*base, "--no-rework-reason", "--out", str(tmp_path / "b.json")]) == 0
    assert "rework_reason" not in capsys.readouterr().err
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m", "models": {},
                                "compare": settings | {"rework_reason": True, "author_rule": "headed"}}) + "\n")
    assert main([*base, "--out", str(tmp_path / "c.json")]) == 0
    assert "different author_rule" in capsys.readouterr().err


# --- files where a heading does not hold for every line ---


def _suite(n=2, seed=111):
    return build_suite(seed=seed, per_family=n, families=("aggregate",), entities=20, distractors=6)


def test_the_heading_arm_is_what_it_says(tmp_path: Path):
    suite = _suite()
    root = suite.write_corpus(tmp_path / "corpus")
    items = vb.products(suite, ("heading",))
    assert len(items) == 2 * len(vb.HEADING_VARIANTS)
    for task, variant, built in items:
        assert built.arm == "heading"
        q = vb._quarter(task)
        true = {n: suite.companies[n].revenue[q] for n in task.entities}
        copy = vb.corpus_for(built, root, tmp_path / "copy" / f"{task.id}-{built.kind}-{variant}")
        if built.kind == "wrong-year":
            assert copy == root and not built.plant and not built.stale
            continue
        own = built.error["own"] if built.error else next(iter(built.plant))
        # The company's own file is among those opened, in every product of the arm.
        assert own in vb._drawn(suite, task, built.product, built.read)
        text = (copy / own).read_text()
        before = (root / own).read_text()
        if built.kind == "stale-heading":
            assert text == before.replace("FY2026 operating notes", "FY2025 operating notes", 1) and "FY2026 operating notes" in before
            assert not built.plant and built.stale == [own]
            # The figure it states is the file's own line, which now has the file's year.
            assert f"{built.error['stated']:.1f}" in before
            assert f"{sum(true.values()):.1f}" in built.product.claim
            continue
        assert not built.stale and text.startswith(before.rstrip("\n")) and len(built.plant) == 1
        added = text[len(before.rstrip("\n")):]
        form = ("section", "paragraph")[variant] if built.kind == "right" else built.kind
        if form == "section":
            assert "## FY2025 comparatives" in added and "carried over" not in added
        else:
            assert "carried over from last year's report" in added and "##" not in added
        # The added line gives no year, and carries a figure that is not the file's true one.
        line = added.strip().splitlines()[-1].split("report. ")[-1]
        assert "FY20" not in line and "$" in line
        name = next(n for n in task.entities if f"{slug(n)}.md" == own)
        figure = float(line.split("$")[1].split()[0].rstrip("Mm."))
        assert figure != true[name] and 0.69 * true[name] <= figure <= 0.91 * true[name]
        if built.kind == "right":
            assert built.error is None and f"{sum(true.values()):.1f}" in built.product.claim and f"{name} {figure:.1f}" not in built.product.claim
        else:
            assert built.error["stated"] == figure and f"{name} {figure:.1f}" in built.product.claim
            assert f"ANSWER: {round(sum(true.values()) - true[name] + figure, 1):.1f}" in built.product.claim


def test_the_two_right_products_hold_different_traps():
    suite = _suite(1)
    task = suite.tasks[0]
    a, b = (vb.build(suite, task, "right", v, "heading") for v in (0, 1))
    assert "## FY2025 comparatives" in next(iter(a.plant.values())) and "carried over" in next(iter(b.plant.values()))


def test_the_control_is_a_line_that_says_fy2025():
    suite = _suite(1)
    built = vb.build(suite, suite.tasks[0], "wrong-year", 0, "heading")
    assert built.arm == "heading" and built.error["stated"] == suite.companies[built.error["company"]].revenue_fy2025_q3


def test_a_trap_belongs_to_the_heading_arm():
    suite = _suite(1)
    for kind in vb.HEADING_TRAPS:
        with pytest.raises(ValueError, match="heading arm"):
            vb.build(suite, suite.tasks[0], kind, 0, "plain")


def test_the_heading_arm_runs_and_reports_every_kind(tmp_path: Path):
    out = tmp_path / "v.json"
    assert main(["verify-bench", "--adapter", "sim", "--questions", "1", "--entities", "20", "--distractors", "6", "--seed", "111",
                 "--setups", "independent-layered,independent-both", "--arms", "heading", "--out", str(out)]) == 0
    saved = json.loads(out.read_text())
    assert len(saved["results"]) == 12 and {r["arm"] for r in saved["results"]} == {"heading"}
    by = saved["summary"]["setups"]["independent-both / heading"]["by_kind"]
    assert set(by) == {"wrong-year", *vb.HEADING_TRAPS}
    assert all(r["error_shown"] for r in saved["results"] if r["kind"] != "right")
    text = vb.render(saved["summary"])
    assert "| independent-both / heading |" in text and "the file is headed FY2025" in text


# --- the tapes' reworks, asked again ---


SETTINGS = {"seed": 7, "per_family": 1, "families": ["aggregate", "breadth"], "entities": 10, "distractors": 6, "filed": 0,
            "context_tokens": 8_000, "verify_view": "independent", "tool_rounds": 2, "max_calls_per_trial": 40}


def _sent(function, mode, goal, packet="p"):
    return {"function": function, "skill": "retrieve", "channel_id": "", "goal": goal, "purpose": "u", "context": "c",
            "done_when": "d", "isolated": True, "tools": ["read", "retrieve"], "success_criteria": ["ANSWER:"], "mode": mode, "packet": packet}


def _row(sent, reply="{}", error=None):
    return {"key": "k", "request": {"model": "m", "max_tokens": 4_000, "messages": [{"role": "user", "content": json.dumps(sent)}]},
            "reply": reply, "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "error": error, "latency_s": 1.0}


def _review(product):
    return f"PRODUCT UNDER REVIEW (the lead's current product)\n{product}\nEVIDENCE GIVEN WITH IT\n- x\nVERIFIER RULE\n{checks.SOURCES_HEAD}\n[read a.md]\ntext"


def _says(word):
    return json.dumps({"claim": word, "evidence": [], "uncertainty": "", "channel_id": "", "context_update": "", "requests": []})


def _rework_packet(extra=""):
    return f"GUIDELINES\n(none)\nBRIEF\n{REWORK_HEAD}{extra}Misses: claim is not PASS. Last product: x"


def _tape(tmp_path: Path, settings=None, name="t.jsonl"):
    """Two trials. In the first a wrong product fails, the rework takes a second round of tools, and the new product is
    right. In the second a right product fails, and the tape has no review of the rework. Then a failed call, a verifier
    reply it cannot read, and a rework that follows another question's review."""
    suite = build_suite(seed=7, per_family=1, families=("aggregate", "breadth"), entities=10, distractors=6)
    a, b = suite.tasks[0], suite.tasks[1]
    rows = [
        _row(_sent("verifier", "verify", a.question, _review("Wrong. ANSWER: 1.0")), _says("FAIL: the sum is wrong.")),
        _row(_sent("lead", "rework", a.question, _rework_packet())),
        _row(_sent("lead", "rework", a.question, _rework_packet() + f"\n{TOOL_RESULTS}\n[read a.md]")),
        _row(_sent("verifier", "verify", a.question, _review(f"Fixed. ANSWER: {a.answer}")), _says("PASS.")),
        _row(_sent("verifier", "verify", b.question, _review(f"Right. ANSWER: {b.answer}")), _says("FAIL: a doubt.")),
        _row(_sent("lead", "rework", b.question, _rework_packet())),
        _row(_sent("verifier", "verify", b.question, _review("Wrong. ANSWER: 2.0")), _says("FAIL: again.")),
        _row(_sent("lead", "rework", b.question, _rework_packet()), None, error="boom"),
        _row(_sent("verifier", "verify", b.question, _review("Wrong. ANSWER: 3.0")), "{\"claim\": \"FA"),
        _row(_sent("lead", "rework", b.question, _rework_packet())),
        _row(_sent("verifier", "verify", a.question, _review("Wrong. ANSWER: 4.0")), _says("FAIL: other.")),
        _row(_sent("lead", "rework", b.question, _rework_packet())),
    ]
    path = tmp_path / name
    head = {"tape": 1, "adapter": "anthropic", "model": "m", "models": {}, "compare": settings or SETTINGS}
    path.write_text("\n".join(json.dumps(r) for r in [head, *rows]) + "\n")
    return path, a, b


def test_it_takes_each_rework_once_and_grades_both_sides(tmp_path: Path):
    path, a, b = _tape(tmp_path)
    got = rb.reworks_from(path)
    assert [(r.row, r.task.id, r.right_before, r.recorded_after, r.said) for r in got] == [
        (2, a.id, False, True, "FAIL: the sum is wrong."),
        (6, b.id, True, False, "FAIL: a doubt."),
    ]
    assert got[0].cap == 8_000 and got[0].tool_rounds == 2 and got[0].max_calls == 40 and got[0].brief.mode == "rework"
    assert got[0].brief.view == ""


def test_a_review_of_another_question_is_not_the_reworks_result(tmp_path: Path):
    suite = build_suite(seed=7, per_family=1, families=("aggregate", "breadth"), entities=10, distractors=6)
    a, b = suite.tasks[0], suite.tasks[1]
    rows = [_row(_sent("verifier", "verify", a.question, _review("Wrong. ANSWER: 1.0")), _says("FAIL.")),
            _row(_sent("lead", "rework", a.question, _rework_packet())),
            _row(_sent("verifier", "verify", b.question, _review(f"ANSWER: {a.answer}")), _says("PASS."))]
    path = tmp_path / "x.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in [{"tape": 1, "compare": SETTINGS}, *rows]) + "\n")
    assert rb.reworks_from(path)[0].recorded_after is None


def test_a_tape_with_no_settings_has_no_reworks(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    path.write_text(json.dumps({"tape": 1, "adapter": "anthropic"}) + "\n")
    assert rb.reworks_from(path) == []


def test_the_arms_differ_by_the_reason_and_only_by_it(tmp_path: Path):
    rework = rb.reworks_from(_tape(tmp_path)[0])[0]
    plain, told = rb.in_arm(rework, "plain"), rb.in_arm(rework, "reason")
    assert plain == rework.brief
    assert told.packet == rework.brief.packet.replace(REWORK_HEAD, f"{REWORK_HEAD}It said: FAIL: the sum is wrong. ")
    assert replace(told, packet="") == replace(plain, packet="")


def test_a_tape_recorded_with_the_reason_gives_the_same_arms(tmp_path: Path):
    rework = rb.reworks_from(_tape(tmp_path)[0])[0]
    plain = rb.in_arm(rework, "plain")
    recorded = replace(rework, brief=replace(rework.brief, packet=rework.brief.packet.replace(REWORK_HEAD, f"{REWORK_HEAD}It said: an old\nreason. ")))
    assert rb.in_arm(recorded, "plain") == plain
    assert rb.in_arm(recorded, "reason") == rb.in_arm(rework, "reason")


def test_a_rework_runs_with_its_tools_on_the_cap_it_had(tmp_path: Path):
    path, a, _ = _tape(tmp_path)
    rework = rb.reworks_from(path)[0]
    root = rework.suite.write_corpus(tmp_path / "corpus")
    name = sorted(p.name for p in root.glob("*.md"))[0]
    adapter = Scripted(_art("reading", [f"read:{name}"]), _art(f"Put right. ANSWER: {a.answer}"))
    res = rb.attempt(rework, "reason", adapter, root)
    assert res.right_after is True and res.calls == 2 and res.code == "" and res.right_before is False and res.recorded_after is True
    assert f"[read {name}]" in adapter.briefs[1].packet and "It said: FAIL" in adapter.briefs[0].packet
    assert adapter.briefs[0].max_reply_tokens is not None and adapter.briefs[0].max_reply_tokens < 8_000


def test_a_rework_is_held_to_the_cap_the_run_had(tmp_path: Path):
    rework = rb.reworks_from(_tape(tmp_path, SETTINGS | {"context_tokens": 5})[0])[0]
    root = rework.suite.write_corpus(tmp_path / "corpus")
    res = rb.attempt(rework, "plain", Scripted(_art("ANSWER: 1")), root)
    assert res.code == "BUDGET" and res.right_after is False and res.calls == 0


def test_a_broken_reply_is_a_result_not_a_crash(tmp_path: Path):
    rework = rb.reworks_from(_tape(tmp_path)[0])[0]
    root = rework.suite.write_corpus(tmp_path / "corpus")

    def broken(brief):
        raise InvariantError("TOOLS", "no")

    res = rb.attempt(rework, "plain", Scripted(broken), root)
    assert res.code == "TOOLS" and res.right_after is False and res.answer is None


def _answering(right_on):
    """A lead who gets it right when right_on(brief) holds."""
    def reply(brief):
        answer = next(t.answer for t in build_suite(seed=7, per_family=1, families=("aggregate", "breadth"), entities=10, distractors=6).tasks if t.question == brief.goal)
        return _art(f"ANSWER: {answer}" if right_on(brief) else "ANSWER: 0.5")
    return lambda: _Forever(reply)


class _Forever(ModelAdapter):
    name = "forever"

    def __init__(self, reply):
        self.reply = reply
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 50}

    def act(self, brief):
        return self.reply(brief)


def test_the_summary_counts_both_sides_and_each_pair(tmp_path: Path):
    reworks = rb.reworks_from(_tape(tmp_path)[0])
    # Told why, the lead puts the wrong one right, and talks itself out of the right one.
    results = rb.run_bench(reworks, _answering(lambda b: ("It said" in b.packet) != ("a doubt" in b.packet)), workers=2)
    assert [(r.row, r.arm) for r in results] == [(2, "plain"), (2, "reason"), (6, "plain"), (6, "reason")]
    summary = rb.summarize(results, price_in=1.0, price_out=2.0)
    s, pairs = summary["arms"], summary["paired"]["reason"]
    assert s["plain"]["wrong_put_right"] == [0, 1] and s["reason"]["wrong_put_right"] == [1, 1]
    assert s["plain"]["right_kept"] == [1, 1] or s["plain"]["right_kept"] == [0, 1]
    assert pairs["was_wrong"] == {"first_right_only": 0, "arm_right_only": 1, "both_right": 0, "neither": 0}
    assert sum(pairs["was_right"].values()) == 1
    assert summary["recorded"] == [1, 1]
    assert s["plain"]["cost_total"] == round(2 * (100 + 100) / 1e6, 4)
    text = rb.render(summary)
    assert "| reason | 1 of 1 |" in text and "On the tapes themselves, 1 of 1" in text
    assert "Wrong before, plain against reason: only plain right 0, only reason right 1" in text


def test_a_rework_right_before_is_counted_on_its_own_side(tmp_path: Path):
    reworks = rb.reworks_from(_tape(tmp_path)[0])
    results = rb.run_bench(reworks, _answering(lambda b: "It said" not in b.packet))
    pairs = rb.summarize(results)["paired"]["reason"]
    s = rb.summarize(results)["arms"]
    assert s["plain"]["right_kept"] == [1, 1] and s["reason"]["right_kept"] == [0, 1]
    assert s["plain"]["wrong_put_right"] == [1, 1] and s["reason"]["wrong_put_right"] == [0, 1]
    assert pairs["was_right"] == {"first_right_only": 1, "arm_right_only": 0, "both_right": 0, "neither": 0}
    assert pairs["was_wrong"] == {"first_right_only": 1, "arm_right_only": 0, "both_right": 0, "neither": 0}


def test_the_command_records_and_replays(tmp_path: Path, capsys, monkeypatch):
    path = _tape(tmp_path)[0]
    out = tmp_path / "r.json"
    assert main(["rework-bench", "--tapes", str(path), "--adapter", "sim", "--workers", "2", "--out", str(out)]) == 0
    saved = json.loads(out.read_text())
    assert saved["config"]["reworks"] == 2 and saved["config"]["trials"] == 4 and saved["config"]["was_right"] == 1
    assert len(saved["results"]) == 4 and "## Rework bench" in capsys.readouterr().out


@pytest.mark.parametrize("words, says", [
    (["--arms", "loud"], "name arms"),
    (["--arms", ""], "name arms"),
    (["--price-in", "1"], "both"),
    (["--max-spend", "1"], "--max-spend needs"),
    (["--record", "a", "--replay", "b"], "not both"),
])
def test_the_command_refuses_what_it_cannot_do(tmp_path: Path, words, says, capsys):
    path = _tape(tmp_path)[0]
    assert main(["rework-bench", "--tapes", str(path), *words]) == 1
    assert says in capsys.readouterr().out


def test_the_command_needs_a_tape_it_can_read_and_a_rework_on_it(tmp_path: Path, capsys):
    assert main(["rework-bench", "--tapes", str(tmp_path / "gone.jsonl")]) == 1
    assert "names no tape" in capsys.readouterr().out
    empty = tmp_path / "e.jsonl"
    empty.write_text(json.dumps({"tape": 1, "compare": SETTINGS}) + "\n")
    assert main(["rework-bench", "--tapes", str(empty)]) == 1
    assert "no rework" in capsys.readouterr().out


def test_the_dry_run_calls_no_model(tmp_path: Path, capsys):
    assert main(["rework-bench", "--tapes", str(_tape(tmp_path)[0]), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["trials"] == 4


def test_the_spend_cap_stops_the_bench(tmp_path: Path, monkeypatch):
    path = _tape(tmp_path)[0]
    out = tmp_path / "r.json"
    from taskorg import rework_bench

    real = rework_bench.attempt

    def priced(rework, arm, adapter, root, repeat=0):
        res = real(rework, arm, adapter, root, repeat)
        res.prompt_tokens, res.completion_tokens, res.tokens = 500_000, 500_000, 1_000_000
        return res

    monkeypatch.setattr(rework_bench, "attempt", priced)
    assert main(["rework-bench", "--tapes", str(path), "--adapter", "sim", "--price-in", "1", "--price-out", "1", "--max-spend", "1.5", "--out", str(out)]) == 0
    saved = json.loads(out.read_text())
    assert saved["config"]["stopped_after"] < saved["config"]["trials"]
