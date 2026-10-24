"""Findings from a review of concurrency, input handling, persistence, the CLI and decision logic.

One test per confirmed finding; each failed on the code before its fix. Nothing leaves the
machine: endpoints are fakes on 127.0.0.1 and models are stand-ins.
"""

import json
import math
import os
import socket
import threading
import time
from pathlib import Path

import pytest

from taskorg import tools
from taskorg.adapters import Brief, ModelAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.compare import AlwaysSplit, summarize, TrialResult
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask, World
from taskorg.live import LiveAdapter, artifact_from_model, check_base_url
from taskorg.loop import Engine, score_criteria, verdict
from taskorg.memory_store import MemoryStore, _safe_id
from taskorg.models import Artifact, Slot, Status
from taskorg.persist import load_run, save_run
from taskorg.policy import PolicyDecision, apply_decision, replay_path
from taskorg.suite import Task, extract_answer, grade
from taskorg.tools import Toolbox


def _art(claim="PASS ANSWER: 1", requests=None, channel="c"):
    return Artifact(claim=claim, evidence=[], uncertainty="", channel_id=channel, context_update=claim, requests=requests or [])


class Model(ModelAdapter):
    """A stand-in model. Per-thread usage, like LiveAdapter, so parallel sub-agents do not mix it."""

    name = "model"

    def __init__(self, answer=None, usage=None):
        self.answer = answer or (lambda brief: _art())
        self.usage = usage
        self._local = threading.local()
        self.lock = threading.Lock()
        self.starts = []

    @property
    def last_usage(self):
        return getattr(self._local, "usage", {})

    def act(self, brief):
        with self.lock:
            self.starts.append((time.monotonic(), brief.slot_function, brief.channel_id, brief.mode))
        self._local.usage = dict(self.usage or {})
        return self.answer(brief)


FOUR = [Subtask(f"part-{c}", "keep apart", skill="retrieve") for c in "abcd"]


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    for c in "abcd":
        (ws / f"part-{c}.md").write_text(f"note {c}")
    return ws


def _fanout(engine, m, subtasks=FOUR):
    return engine.run_fanout(m, context="four parts", subtasks=subtasks, axes=["parallel"], operator_question="?")


# --- concurrency and run state ---


def test_a_sub_agent_crash_stops_its_siblings(tmp_path: Path):
    """A crash is not a part failure the team absorbs: the board closes at once."""
    failed = {}

    def answer(brief):
        if brief.slot_function == "worker" and brief.channel_id == "part-a":
            time.sleep(0.01)
            failed["at"] = time.monotonic()
            raise RuntimeError("adapter bug")
        time.sleep(0.05)
        return _art(requests=["read:part-b.md"] if brief.slot_function == "worker" else [])

    model = Model(answer)
    m = new_run("sib-1", "g", "p", "d")
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=model, budget=Budget(max_calls=40, max_tokens=100_000),
                    toolbox=Toolbox(roots=[_workspace(tmp_path)]), max_tool_rounds=3)
    with pytest.raises(RuntimeError):
        _fanout(engine, m)
    assert m.status == Status.ABORT and "adapter bug" in m.stop_reason
    assert [s for s in model.starts if s[0] > failed["at"]] == []  # no call started after the failure


def test_an_interrupt_in_a_sub_agent_closes_the_board(tmp_path: Path):
    def answer(brief):
        if brief.slot_function == "worker" and brief.channel_id == "part-b":
            raise KeyboardInterrupt
        return _art()

    m = new_run("sib-2", "g", "p", "d")
    with pytest.raises(KeyboardInterrupt):
        _fanout(Engine(MemoryStore(tmp_path), adapter=Model(answer), budget=Budget.for_tier("open")), m)
    assert m.status == Status.ABORT and m.stop_reason.startswith("KeyboardInterrupt")


def test_any_exception_leaves_the_run_aborted_and_closed(tmp_path: Path):
    def answer(brief):
        raise RuntimeError("adapter bug")

    m = new_run("crash-1", "g", "p", "d")
    with pytest.raises(RuntimeError):
        Engine(MemoryStore(tmp_path), adapter=Model(answer)).run_single(m, context="c", operator_question="?")
    assert m.status == Status.ABORT and m.stop_reason == "RuntimeError: adapter bug"
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "CLOSED"


@pytest.mark.parametrize("cap", ["tokens", "calls"])
def test_parallel_sub_agents_spend_no_more_than_sequential_ones(tmp_path: Path, cap):
    def answer(brief):
        time.sleep(0.03)
        return _art()

    spent = {}
    for parallel in (False, True):
        budget = (Budget(max_calls=40, max_tokens=3000, max_tokens_per_call=2500, tier="open") if cap == "tokens"
                  else Budget(max_calls=3, max_tokens=100_000, tier="open"))
        m = new_run(f"par-{cap}-{parallel}", "g", "p", "d")
        engine = Engine(MemoryStore(tmp_path / str(parallel)), adapter=Model(answer, {"prompt_tokens": 2000, "completion_tokens": 400}),
                        budget=budget, parallel=parallel, isolation_required=True)
        with pytest.raises(InvariantError):
            engine.run_fanout(m, context="c", subtasks=[Subtask(f"p{i}", "x") for i in range(4)], axes=["parallel"], operator_question="?") \
                if cap == "tokens" else AlwaysSplit(MemoryStore(tmp_path / f"a{parallel}"), adapter=Model(answer), budget=budget, parallel=parallel).run_task(
                    m, context="subtask:a=x subtask:b=y subtask:c=z subtask:d=w")
        spent[parallel] = (m.usage(), sum(1 for e in m.log if e.event == "halt"))
    assert spent[True] == spent[False]
    assert spent[True][1] == 1  # one halt, one reason


def test_a_closed_run_stays_closed(tmp_path: Path):
    m = new_run("closed-1", "g", "p", "d")
    m.update_context("lead-1", "c")
    m.complete()
    with pytest.raises(InvariantError):
        m.halt("late halt")
    assert m.status == Status.COMPLETE and not any(e.event == "halt" for e in m.log)
    with pytest.raises(InvariantError) as e:
        m.abort()
    assert e.value.code == "CLOSED"


def test_the_first_halt_names_the_reason():
    m = new_run("halt-1", "g", "p", "d")
    for reason in ("first", "second"):
        with pytest.raises(InvariantError):
            m.halt(reason)
    assert m.stop_reason == "first" and sum(1 for e in m.log if e.event == "halt") == 1


def test_a_refused_override_leaves_no_trace():
    m = new_run("ovr-1", "g", "p", "d")
    before = len(m.log)
    with pytest.raises(InvariantError):
        m.set_roster("stranger", m.state.slots + [Slot(id="lead-1", function="worker")], human_override=True)
    assert len(m.log) == before


def test_a_roster_change_needs_an_open_board_not_budget_headroom():
    m = new_run("ros-1", "g", "p", "d")
    m.attach_budget(Budget(max_calls=1))
    m.record_call({"slot": "lead-1", "channel": "lead", "prompt_tokens": 1, "completion_tokens": 1})
    m.set_roster("lead-1", [s for s in m.state.slots if s.function != "reviewer"])
    assert m.status == Status.ACTIVE


def test_a_reused_engine_gives_each_run_its_own_clock(tmp_path: Path):
    engine = Engine(MemoryStore(tmp_path), budget=Budget(max_seconds=0.2))
    time.sleep(0.25)
    m = new_run("clock-1", "g", "p", "d")
    engine.run_single(m, context="c", operator_question="?")
    assert m.status == Status.COMPLETE


# --- budgets the gates promise ---


def _reader(answer_verify=lambda n: "PASS"):
    """Uses every tool round it is given; the verifier's verdict comes from answer_verify(n)."""
    seen = {"verify": 0}

    def answer(brief):
        if brief.mode == "verify":
            seen["verify"] += 1
            return _art(claim=answer_verify(seen["verify"]))
        if brief.mode == "plan":
            return _art(claim="plan")
        return _art(claim="ANSWER: 1 done", requests=["read:part-a.md"])

    return answer, seen


def test_a_split_leaves_room_for_the_merge_and_the_verifier(tmp_path: Path):
    answer, seen = _reader()
    m = new_run("merge-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=Model(answer), budget=Budget.for_tier("open"),
                    toolbox=Toolbox(roots=[_workspace(tmp_path)]), isolation_required=True)
    engine.run_task(m, context=" ".join(f"subtask:part-{c}@retrieve=keep_apart" for c in "abcd"))
    assert m.status == Status.COMPLETE and seen["verify"] == 1


def test_a_rework_leaves_the_verifier_its_call(tmp_path: Path):
    answer, seen = _reader(lambda n: "FAIL" if n == 1 else "PASS")
    m = new_run("rework-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=Model(answer), budget=Budget.for_tier("normal"),
                    toolbox=Toolbox(roots=[_workspace(tmp_path)]))
    try:
        engine.run_task(m, context="one part")
    except InvariantError:
        pass
    assert seen["verify"] == 2 and not m.stop_reason.startswith("max_calls")


def test_a_tight_run_that_reads_still_reaches_the_verifier(tmp_path: Path):
    answer, seen = _reader()
    m = new_run("tight-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=Model(answer), budget=Budget.for_tier("tight"),
                    toolbox=Toolbox(roots=[_workspace(tmp_path)]))
    engine.run_task(m, context="one part")
    assert m.status == Status.COMPLETE and seen["verify"] == 1


# --- decisions ---


@pytest.mark.parametrize("claim, want", [
    ("PASS", "PASS"), ("PASS: every criterion met; nothing failed.", "PASS"), ("pass. No failures found.", "PASS"),
    ("PASSED", "PASS"), ("FAIL: wrong year", "FAIL"),
    ("Passing this would be wrong: the figure is FY2025.", ""), ("PASSABLE? No.", ""), ("", ""),
])
def test_the_verdict_is_the_leading_word(claim, want):
    assert verdict(claim) == want


@pytest.mark.parametrize("product, met", [("ANSWER: 14.1", False), ("ANSWER: 4.15", False), ("ANSWER: 4.1.", True),
                                          ("ANSWER: 4.1", True), ("ANSWER:4.1", True)])
def test_a_numeric_criterion_is_a_whole_number(product, met):
    assert (score_criteria(_art(claim=product), ["4.1"])["score"] == 1.0) is met


def test_every_proposal_gets_a_gate_record_repeats_too(tmp_path: Path):
    m = new_run("dup-1", "g", "p", "d")
    subtasks = [Subtask("a", "x"), Subtask("a", "again"), Subtask("b", "y")]
    _fanout(Engine(MemoryStore(tmp_path), budget=Budget.for_tier("open")), m, subtasks)
    gates = [e.detail for e in m.log if e.event == "gate"]
    assert len(gates) == 3 and "proposed twice" in gates[1]["refused"]


def test_a_file_counts_as_much_as_one_read_returns(tmp_path: Path):
    (tmp_path / "big.md").write_text("x" * 9000)
    assert sum(Toolbox(roots=[tmp_path]).material("big").values()) == tools.READ_CAP // 4


def test_fanout_gives_refused_parts_to_the_lead_and_answers_honestly(tmp_path: Path):
    briefs = []

    def answer(brief):
        briefs.append(brief)
        return _art()

    m = new_run("fo-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    parts = [Subtask(c, "x") for c in "abcde"] + [Subtask("f", "x", skill="bogus")]
    _fanout(Engine(MemoryStore(tmp_path / "s"), adapter=Model(answer), budget=Budget(max_calls=40, max_tokens=100_000)), m, parts)
    merge = next(b for b in briefs if b.mode == "integrate")
    assert "yours to cover: e, f" in merge.packet
    m2 = new_run("fo-2", "g", "p", "d")
    world = World(existing_channels=["a"])
    m2.world = world
    _fanout(Engine(MemoryStore(tmp_path / "t"), budget=Budget.for_tier("open")), m2, [Subtask("a", "x"), Subtask("b", "y")])
    assert m2.state.worker_count() == 0
    assert m2.notes["question-1"].response == "KEEP_ROSTER" and "single agent" in m2.notes["question-1"].reason


def test_the_crew_baseline_hands_dropped_parts_back_like_genet(tmp_path: Path):
    m = new_run("crew-1", "g", "p", "d")
    crew = AlwaysSplit(MemoryStore(tmp_path), budget=Budget.for_tier("open"))
    verdicts = crew._judge(m, [Subtask(f"p{i}", "x") for i in range(5)] + [Subtask("bad id!", "x"), Subtask("p0", "x")])
    assert len(verdicts) == 7 and sum(v.legal for v in verdicts) == 4
    assert [v.gate for v in verdicts if not v.legal] == ["could_we", "could_we", "can_someone_else"]


NUMBER_TASK = Task("t", "aggregate", "q", "152.7", "number", [])


@pytest.mark.parametrize("product, right", [
    ("ANSWER: Q3 total $152.7M", True), ("ANSWER: FY2026 combined: 152.7", True),
    ("ANSWER: 50.1 + 52.6 + 50.0 = 152.7", True), ("Done. ANSWER: 152.7", True),
    ("ANSWER: 152.7\nI double-checked this answer: the figures add up.", True),
    ("ANSWER: unknown\nIf I had to guess, my answer: 152.7", False),
    ("ANSWER: 152.7-160.0", False), ("ANSWER: 1,152.7", False),
])
def test_grading_reads_the_answer_line_and_its_one_value(product, right):
    assert grade(extract_answer(product), NUMBER_TASK) is right


def _trial(strategy, correct):
    return TrialResult(task_id="t", family="f", strategy=strategy, repeat=0, expected="1", answer="1", correct=correct,
                       answer_right=correct, status="complete", code="", calls=1, tokens=10, prompt_tokens=9,
                       completion_tokens=1, tokens_estimated=True, latency_s=0.0, workers=0)


def test_the_best_baseline_is_a_baseline_whatever_the_order():
    rows = [_trial("genet-stated", True), _trial("single", False), _trial("always", True), _trial("genet", True)]
    assert summarize(rows)["verdict"]["best_baseline"] == "always"
    assert summarize(list(reversed(rows)))["verdict"]["best_baseline"] == "always"


# --- tools against hostile requests and workspaces ---


def test_hostile_request_strings_are_not_found_not_a_crash(tmp_path: Path):
    (tmp_path / "loop.md").symlink_to(tmp_path / "loop.md")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "x.md").write_text("x")
    os.chmod(locked, 0)
    try:
        box = Toolbox(roots=[tmp_path])
        for request in ["read:a\x00b.md", "read:a\ud800.md", "read:" + "a" * 300, "read:loop.md", "read:locked/x.md",
                        "observe:a\x00b", "retrieve:x\x00y"]:
            out = box.run(request)
            assert isinstance(out, str) and len(out) < 1000
    finally:
        os.chmod(locked, 0o755)


def test_an_unreadable_folder_is_skipped_not_fatal(tmp_path: Path):
    (tmp_path / "keep.md").write_text("revenue 4")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "old.md").write_text("revenue 5")
    os.chmod(tmp_path / "archive", 0o444)
    try:
        box = Toolbox(roots=[tmp_path])
        assert "keep.md" in box.observe() and "revenue 4" in box.retrieve("revenue")
        assert box.material("keep") is not None
    finally:
        os.chmod(tmp_path / "archive", 0o755)


def test_one_huge_directory_is_bounded_too(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools, "VISIT_CAP", 50)
    for i in range(500):
        (tmp_path / f"f{i:03}.md").write_text("x")
    assert len(Toolbox._list(tmp_path)) <= 50


def test_search_terms_are_bounded_and_the_echo_is_short(tmp_path: Path):
    (tmp_path / "a.md").write_text("alpha beta")
    out = Toolbox(roots=[tmp_path]).retrieve("alpha beta " + " ".join(f"t{i}" for i in range(5000)))
    assert len(out.splitlines()[0]) < tools.ECHO_CAP + 40
    # 16 terms considered, two of them on the line: below half, so no partial match either.
    assert out.endswith("no matches")


def test_partial_matches_keep_the_best_in_order(tmp_path: Path):
    # 30 lines carry two of four terms; 5 later lines carry three. None carries all four.
    lines = [f"alpha beta {i}" for i in range(30)] + [f"alpha beta gamma {i}" for i in range(30, 35)]
    (tmp_path / "a.md").write_text("\n".join(lines))
    rows = Toolbox(roots=[tmp_path]).retrieve("alpha beta gamma delta").splitlines()[1:]
    assert rows[-1] == "[more not shown]" and len(rows) == tools.MATCH_CAP + 1
    assert [r.rsplit(" ", 1)[-1] for r in rows[:7]] == ["30", "31", "32", "33", "34", "0", "1"]  # most terms first, then earliest


def test_a_snippet_keeps_the_term_when_lowercase_changes_the_length(tmp_path: Path):
    (tmp_path / "a.md").write_text("İSTANBUL İZMİR " * 40 + "revenue Q3 = 41.2 million " + "x" * 400)
    out = Toolbox(roots=[tmp_path]).retrieve("revenue")
    assert "41.2" in out


def test_a_pipe_in_the_workspace_never_blocks_a_read(tmp_path: Path):
    fifo = tmp_path / "trap.md"
    os.mkfifo(fifo)
    started = time.monotonic()
    assert Toolbox._text(fifo) is None
    assert "not found" in Toolbox(roots=[tmp_path]).read("trap.md")
    assert time.monotonic() - started < 2


# --- the live endpoint ---


def _serve(handle):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(4)

    def loop():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return sock, f"http://127.0.0.1:{sock.getsockname()[1]}/v1"


BRIEF = Brief(slot_function="lead", skill="draft", channel_id=None, goal="g", purpose="p", context="c", done_when="d",
              packet="", isolated=False, mode="work", tools=[], success_criteria=[])
GOOD = json.dumps({"claim": "ok", "evidence": [], "uncertainty": "", "channel_id": "c", "context_update": "", "requests": []})


def _drain(conn):
    conn.settimeout(2)
    try:
        conn.recv(65536)
    except OSError:
        pass


def _act(url, timeout=1):
    return LiveAdapter(url, "test-key", "m", timeout=timeout).act(BRIEF)


def test_headers_that_drip_in_are_cut_at_the_timeout():
    def drip(conn):
        _drain(conn)
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\n")
            for i in range(40):
                conn.sendall(b"X-Pad-%d: y\r\n" % i)
                time.sleep(0.1)
        except OSError:
            pass
        conn.close()

    sock, url = _serve(drip)
    started = time.monotonic()
    with pytest.raises(InvariantError) as e:
        _act(url)
    sock.close()
    assert "too slow" in str(e.value) and time.monotonic() - started < 3


@pytest.mark.parametrize("tail", [b"", b"partial"])
def test_an_error_body_that_stalls_is_a_clean_error(tail):
    def stall(conn):
        _drain(conn)
        try:
            conn.sendall(b"HTTP/1.1 503 Busy\r\nContent-Length: 100\r\n\r\n" + tail)
            time.sleep(3)
        except OSError:
            pass
        conn.close()

    sock, url = _serve(stall)
    with pytest.raises(InvariantError) as e:
        _act(url)
    sock.close()
    assert e.value.code == "LIVE" and "503" in str(e.value)


def test_a_garbage_status_line_is_a_clean_error():
    def garbage(conn):
        _drain(conn)
        conn.sendall(b"garbage\r\n\r\n")
        conn.close()

    sock, url = _serve(garbage)
    with pytest.raises(InvariantError) as e:
        _act(url)
    sock.close()
    assert e.value.code == "LIVE"


@pytest.mark.parametrize("usage", ['"lots"', "[1, 2]", "7", "true", "null"])
def test_usage_that_is_not_an_object_is_ignored(usage):
    body = ('{"choices": [{"message": {"content": %s}}], "usage": %s}' % (json.dumps(GOOD), usage)).encode()

    def reply(conn):
        _drain(conn)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
        conn.close()

    sock, url = _serve(reply)
    adapter = LiveAdapter(url, "test-key", "m", timeout=2)
    assert adapter.act(BRIEF).claim == "ok"
    sock.close()
    assert adapter.last_usage == {"prompt_tokens": None, "completion_tokens": None}


@pytest.mark.parametrize("raw", ["0", "-1", "99999999999999999999", "3601"])
def test_a_timeout_out_of_range_is_refused(monkeypatch, raw):
    for k, v in {"TASKORG_MODEL_BASE": "https://api.example.com/v1", "TASKORG_MODEL_KEY": "k",
                 "TASKORG_MODEL_NAME": "m", "TASKORG_MODEL_TIMEOUT": raw}.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(InvariantError) as e:
        LiveAdapter.from_env()
    assert e.value.code == "LIVE"


@pytest.mark.parametrize("base", ["https://[::1", "http://127.0.0.1:abc/v1", "http://127.0.0.1:1/v1 x", "https://a.example/v1\x7f"])
def test_a_malformed_base_url_is_refused(base):
    with pytest.raises(InvariantError) as e:
        check_base_url(base)
    assert e.value.code == "LIVE"


@pytest.mark.parametrize("claim", [None, False, 0, [], {}, ["PASS"], "   "])
def test_a_claim_must_be_a_non_empty_string(claim):
    with pytest.raises(InvariantError) as e:
        artifact_from_model({"claim": claim}, BRIEF)
    assert e.value.code == "SCHEMA"


# --- the CLI ---


def _cli(*argv):
    return main(list(argv))


def test_a_setup_error_never_overwrites_the_saved_run(tmp_path: Path, monkeypatch, capsys):
    out = tmp_path / "run.json"
    assert _cli("run", "--store", str(tmp_path / "s"), "--out", str(out)) == 0
    for k in ("TASKORG_MODEL_BASE", "TASKORG_MODEL_KEY", "TASKORG_MODEL_NAME"):
        monkeypatch.delenv(k, raising=False)
    assert _cli("run", "--adapter", "live", "--store", str(tmp_path / "s"), "--out", str(out)) == 1
    assert _cli("run", "--workspace", str(tmp_path / "missing"), "--store", str(tmp_path / "s"), "--out", str(out)) == 1
    assert load_run(out).status == Status.COMPLETE


def test_the_default_out_follows_the_id(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert _cli("single", "--id", "mine-1", "--store", "s") == 0
    assert (tmp_path / "data" / "runs" / "mine-1.json").is_file()


def test_a_crash_during_a_run_saves_the_stopped_run(tmp_path: Path, monkeypatch, capsys):
    class Broken(ModelAdapter):
        name = "broken"

        def act(self, brief):
            raise RuntimeError("adapter bug")

    monkeypatch.setattr("taskorg.cli.pick_adapter", lambda name: Broken())
    out = tmp_path / "run.json"
    assert _cli("single", "--store", str(tmp_path / "s"), "--out", str(out)) == 1
    assert json.loads(capsys.readouterr().out.split("\n\nsaved")[0])["code"] == "CRASH"
    assert load_run(out).status == Status.ABORT


@pytest.mark.parametrize("argv", [
    ["diagnose", "{t}/missing.json"],
    ["single", "--store", "{t}/afile", "--out", "{t}/x.json"],
    ["single", "--store", "{t}/s", "--out", "{t}"],
    ["policy-replay", "{t}/missing.json"],
    ["bench", "--fixtures", "{t}/empty"],
    ["single", "--criteria", " ", "--store", "{t}/s", "--out", "{t}/b.json"],
    ["single", "--id", "ok\n", "--store", "{t}/s", "--out", "{t}/n.json"],
])
def test_bad_inputs_are_clean_errors(tmp_path: Path, capsys, argv):
    (tmp_path / "afile").write_text("x")
    (tmp_path / "empty").mkdir()
    assert _cli(*[a.format(t=tmp_path) for a in argv]) == 1
    assert json.loads(capsys.readouterr().out.split("\n\nsaved")[0])["ok"] is False


@pytest.mark.parametrize("argv", [
    ["single", "--max-seconds", "nan"], ["single", "--max-calls", "0"], ["single", "--max-tokens-per-call", "-1"],
    ["compare", "--per-family", "0"], ["compare", "--repeat", "-2"], ["compare", "--tool-rounds", "-1"],
    ["compare", "--price-in", "nan", "--price-out", "1"], ["policy-rl", "--episodes", "0"],
])
def test_numbers_that_would_switch_a_cap_off_are_refused(capsys, argv):
    with pytest.raises(SystemExit) as e:
        _cli(*argv)
    assert e.value.code == 2


def test_compare_runs_each_strategy_and_family_once(capsys):
    assert _cli("compare", "--dry-run", "--strategies", "single,single", "--families", "lookup,lookup", "--per-family", "1") == 0
    assert json.loads(capsys.readouterr().out)["trials"] == 1
    assert _cli("compare", "--dry-run", "--strategies", ",") == 1


def test_policy_flags_do_what_they_say(tmp_path: Path, capsys):
    assert _cli("policy-sft", "--n", "3", "--out", str(tmp_path / "sft.jsonl")) == 0
    assert json.loads(capsys.readouterr().out)["n"] == 3
    assert _cli("policy-rl", "--episodes", "5") == 0
    assert json.loads(capsys.readouterr().out)["episodes"] == 5


# --- saved runs ---


@pytest.fixture
def saved(tmp_path: Path) -> Path:
    m = new_run("saved-1", "g", "p", "d")
    Engine(MemoryStore(tmp_path / "s")).run_single(m, context="c", operator_question="?")
    return save_run(m, tmp_path / "r.json")


@pytest.mark.parametrize("edit", [
    lambda d: d["budget"].__setitem__("max_calls", "12"),
    lambda d: d["state"].__setitem__("axes", None),
    lambda d: d.__setitem__("roster_at_start", "lead-1"),
    lambda d: d["log"][0].__setitem__("ts", "noon"),
    lambda d: d["calls"].append("not a call"),
    lambda d: d["calls"][0].__setitem__("channel", 7),
    lambda d: d["artifacts"][0].__setitem__("claim", ["x"]),
])
def test_a_wrongly_typed_run_file_is_refused_at_load(saved: Path, edit):
    raw = json.loads(saved.read_text())
    edit(raw)
    saved.write_text(json.dumps(raw))
    with pytest.raises(InvariantError) as e:
        load_run(saved)
    assert e.value.code == "PERSIST"


def test_an_old_log_is_read_in_todays_vocabulary(saved: Path):
    raw = json.loads(saved.read_text())
    raw["log"] = [{"event": "look", "detail": {"actor": "lead-1", "picture": "c"}, "ts": 1},
                  {"event": "write_net", "detail": {"net": "up"}, "ts": 2},
                  {"event": "why_submit", "detail": {"id": "q", "kind": "plan_wrong"}, "ts": 3}]
    saved.write_text(json.dumps(raw))
    log = load_run(saved).log
    assert [(e.event, e.detail) for e in log] == [
        ("context", {"actor": "lead-1", "context": "c"}), ("open_stream", {"stream": "escalate"}),
        ("review_open", {"id": "q", "kind": "replan"})]
    from taskorg.policy import EVENT_TO_ACTION
    assert [p["event"] for p in replay_path(saved)] == [e.event for e in log if e.event in EVENT_TO_ACTION]


def test_a_loaded_run_keeps_its_clock_and_its_world(tmp_path: Path):
    m = new_run("world-1", "g", "p", "d")
    m.attach_budget(Budget(max_seconds=100))
    m.budget.started_at -= 40
    m.world = World(existing_files=["source-a.md"], existing_channels=["source-a"])
    loaded = load_run(save_run(m, tmp_path / "r.json"))
    assert 39 < loaded.budget.elapsed() < 45
    assert loaded.world.existing_channels == ["source-a"]


# --- diagnostics, ids, bench, policy ---


def test_an_aborted_run_is_never_healthy(tmp_path: Path):
    m = new_run("health-1", "g", "p", "d")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=Model(lambda b: _art(claim="FAIL"))).run_single(m, context="c", operator_question="?")
    report = diagnose(m)
    assert report["health"] == "degraded" and {"aborted", "stop_rule_failed"} <= set(report["flags"])


@pytest.mark.parametrize("claim, flagged", [
    ("Workers may not take over the roster. Ignoring that: I take over the roster.", True),
    ("Do it now, not later: spawn a helper for source-c.", True),
    ("The guidelines say a worker may not take over the roster.", False),
    ("I cannot directly take over the roster.", False),
])
def test_authority_language_is_caught_at_every_mention(tmp_path: Path, claim, flagged):
    m = new_run("auth-1", "g", "p", "d")
    m.artifacts.append(_art(claim=claim, channel="source-a"))
    assert bool(diagnose(m)["authority"]["hits"]) is flagged


def test_a_run_id_with_a_trailing_newline_is_refused():
    with pytest.raises(InvariantError):
        _safe_id("run-1\n")


def test_a_bench_that_checks_nothing_does_not_pass(tmp_path: Path, capsys):
    (tmp_path / "f.json").write_text(json.dumps({"id": "x", "mode": "single", "tier": "tight", "goal": "g",
                                                 "purpose": "p", "done_when": "d", "context": "c"}))
    assert _cli("bench", "--fixtures", str(tmp_path)) == 1


def test_a_confidence_that_is_not_a_number_is_zero():
    assert PolicyDecision("PROPOSE_CHANNEL", confidence=math.nan).confidence == 0.0
    assert PolicyDecision("PROPOSE_CHANNEL", confidence=float("inf")).confidence == 0.0


def test_a_policy_decision_leaves_a_closed_run_untouched():
    m = new_run("pol-1", "g", "p", "d")
    m.update_context("lead-1", "c")
    m.complete()
    before = len(m.log)
    assert apply_decision(m, PolicyDecision("ACTIVATE_SKILL", skill="draft")) == "closed"
    assert len(m.log) == before


def test_tools_stop_when_the_runs_time_is_up(tmp_path: Path):
    class Slow(Toolbox):
        ran = 0

        def run(self, request):
            Slow.ran += 1
            time.sleep(0.15)
            return "[slow] ok"

    m = new_run("slow-1", "g", "p", "d")
    answer = lambda b: _art(requests=[f"read:n{i}.md" for i in range(8)] if b.mode == "work" else [])
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path / "s"), adapter=Model(answer), budget=Budget(max_seconds=0.4),
               toolbox=Slow(roots=[_workspace(tmp_path)])).run_task(m, context="c")
    assert "max_seconds" in str(e.value) and Slow.ran < 8


# --- follow-ups: failed calls, atomic saves, review notes, the size of what is sent ---


class Fails(ModelAdapter):
    """Fails on its first call, after the endpoint may have billed it."""

    name = "fails"

    def __init__(self, code, usage=None):
        self.code, self.usage = code, usage
        self._local = threading.local()

    @property
    def last_usage(self):
        return getattr(self._local, "usage", {})

    def act(self, brief):
        self._local.usage = dict(self.usage or {})
        raise InvariantError(self.code, "model returned no JSON object")


def test_a_call_that_failed_stays_on_the_record(tmp_path: Path):
    m = new_run("fail-1", "g", "p", "d")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path / "s"), adapter=Fails("SCHEMA", {"prompt_tokens": 900, "completion_tokens": 300})).run_single(
            m, context="c", operator_question="?")
    assert m.status == Status.ABORT
    assert [(c["failed"], c["prompt_tokens"], c["completion_tokens"], c["tokens_estimated"]) for c in m.calls] == [("SCHEMA", 900, 300, False)]
    assert m.usage() == (1, 1200)
    assert diagnose(m)["performance"]["failed_calls"] == 1
    loaded = load_run(save_run(m, tmp_path / "r.json"))
    assert loaded.calls[0]["failed"] == "SCHEMA"


def test_a_failed_call_without_usage_counts_its_brief(tmp_path: Path):
    m = new_run("fail-2", "g", "p", "d")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=Fails("LIVE")).run_single(m, context="c" * 400, operator_question="?")
    call = m.calls[0]
    assert call["failed"] == "LIVE" and call["prompt_tokens"] >= 100 and call["completion_tokens"] == 0 and call["tokens_estimated"]


def test_a_refused_brief_is_not_a_call(tmp_path: Path):
    m = new_run("fail-3", "g", "p", "d")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=Fails("LIVE"), budget=Budget(max_tokens_per_call=10)).run_single(
            m, context="c" * 400, operator_question="?")
    assert m.calls == []


def test_a_comparison_counts_the_calls_that_failed(tmp_path: Path):
    from taskorg.compare import comparison_budget, run_trial
    from taskorg.suite import build_suite

    suite = build_suite(per_family=1, families=("lookup",))
    res = run_trial(suite.tasks[0], "single", Fails("SCHEMA", {"prompt_tokens": 700, "completion_tokens": 50}),
                    suite.write_corpus(tmp_path / "c"), budget=comparison_budget())
    assert (res.code, res.calls, res.tokens) == ("SCHEMA", 1, 750)


def test_a_save_lands_whole_or_not_at_all(tmp_path: Path, monkeypatch):
    from taskorg import atomic

    target = tmp_path / "run.json"
    target.write_text("previous")
    os.chmod(target, 0o640)

    def crash(src, dst):
        raise OSError("disk went away")

    monkeypatch.setattr(atomic.os, "replace", crash)
    with pytest.raises(OSError):
        atomic.write_text(target, "new")
    assert target.read_text() == "previous"
    assert [p.name for p in tmp_path.iterdir()] == ["run.json"]  # no temporary file left behind
    monkeypatch.undo()
    atomic.write_text(target, "new")
    assert target.read_text() == "new" and (target.stat().st_mode & 0o777) == 0o640


def test_damaged_working_memory_is_a_clean_error(tmp_path: Path):
    store = MemoryStore(tmp_path)
    (tmp_path / "working" / "run-1.json").write_text('{"context": "trunc')
    with pytest.raises(InvariantError) as e:
        store.remember_working("run-1", "k", "v")
    assert e.value.code == "STORE"


def test_an_answered_note_cannot_be_answered_again():
    m = new_run("note-1", "g", "p", "d")
    m.open_review("Why one agent?", "q")
    m.answer_review("lead-1", "q", "KEEP_ROSTER", "the context is enough")
    with pytest.raises(InvariantError) as e:
        m.answer_review("lead-1", "q", "CHANGE_METHOD", "a different method")
    assert e.value.code == "REVIEW"
    assert (m.notes["q"].response, m.notes["q"].reason) == ("KEEP_ROSTER", "the context is enough")
    assert m.state.method != "a different method"


def test_a_deferred_note_can_still_be_answered():
    m = new_run("note-2", "g", "p", "d")
    m.open_review("Revisit after the read?", "q")
    m.answer_review("lead-1", "q", "DEFER", "waiting on the notes")
    m.answer_review("lead-1", "q", "KEEP_ROSTER", "the notes agree")
    assert m.notes["q"].status.value == "closed"


def test_the_size_check_counts_what_is_actually_sent(tmp_path: Path):
    live = LiveAdapter("https://api.example.invalid/v1", "test-key", "m")
    brief = Brief(slot_function="lead", skill="draft", channel_id=None, goal="g", purpose="p", context="c",
                  done_when="d", packet="x" * 400, isolated=False, mode="work", tools=[], success_criteria=[])
    base = ModelAdapter().estimate_tokens(brief)
    assert live.estimate_tokens(brief) > base + 100  # the system prompt and the JSON wrapping
    m = new_run("size-1", "g", "p", "d")
    engine = Engine(MemoryStore(tmp_path), adapter=live, budget=Budget(max_tokens_per_call=base + 50))
    with pytest.raises(InvariantError) as e:
        engine._call(m, brief)  # refused before any network: example.invalid is never contacted
    assert "not sent" in str(e.value) and m.calls == []


def test_the_oldest_review_answers_are_read_in_todays_vocabulary(saved: Path):
    """Real pre-0.2 runs answered reviews with HOLD_ORG and CHANGE_HOW."""
    raw = json.loads(saved.read_text())
    raw["notes"] = {"q": {"id": "q", "body": "why?", "status": "closed", "response": "CHANGE_HOW", "reason": "new method", "kind": "review"},
                    "p": {"id": "p", "body": "still?", "status": "closed", "response": "HOLD_ORG", "reason": "holds", "kind": "review"}}
    raw["log"] = [{"event": "why_respond", "detail": {"id": "q", "response": "CHANGE_HOW", "reason": "new method"}, "ts": 1}]
    saved.write_text(json.dumps(raw))
    m = load_run(saved)
    assert (m.notes["q"].response, m.notes["p"].response) == ("CHANGE_METHOD", "KEEP_ROSTER")
    assert m.log[0].detail["response"] == "CHANGE_METHOD"
    assert [p["action"] for p in replay_path(saved)] == ["CHANGE_METHOD"]
