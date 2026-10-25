"""Ready for a live run. Four gaps found in the past live data and the live-path rehearsal:

1. the size check left no room for the reply, so a call could fit and still overrun when it replied;
2. one malformed reply ended the run, or lost the part, with no second chance;
3. a run verified only against the default criteria looked as trustworthy as any other;
4. the verifier checked the criteria and not the goal, so an answer about Jean Genet the playwright
   passed a task about Genet the kernel.
"""

import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from taskorg.adapters import Brief, ModelAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import DEFAULT_CRITERIA, new_run
from taskorg.gates import Subtask
from taskorg.live import LiveAdapter, ScriptedLive, system_prompt
from taskorg.loop import RETRY_NOTE, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact, Status
from taskorg.persist import LEGACY_DEFAULT_CRITERIA, load_run, save_run
from taskorg.review import LESSONS

GOOD = json.dumps({"claim": "PASS ANSWER: 1", "evidence": [], "uncertainty": "", "channel_id": "c",
                   "context_update": "", "requests": []})


def _art(claim="PASS ANSWER: 1"):
    return Artifact(claim=claim, evidence=[], uncertainty="", channel_id="c", context_update=claim, requests=[])


def _run(name, criteria=("ANSWER:",)):
    m = new_run(name, "g", "p", "d")
    if criteria is not None:
        m.state.success_criteria = list(criteria)
    return m


class Replies(ModelAdapter):
    """Answers from a list: an Artifact, an exception to raise, or a callable of the brief."""

    name = "replies"

    def __init__(self, *replies, min_reply=0, usage=None, size=None):
        self.replies, self.briefs, self.min_reply_tokens, self.usage, self.size = list(replies), [], min_reply, usage, size

    def estimate_tokens(self, brief):
        return self.size if self.size is not None else super().estimate_tokens(brief)

    @property
    def last_usage(self):
        return dict(self.usage or {})

    def act(self, brief):
        self.briefs.append(brief)
        reply = self.replies.pop(0) if self.replies else _art()
        if callable(reply) and not isinstance(reply, Artifact):
            reply = reply(brief)
        if isinstance(reply, BaseException):
            raise reply
        return reply


MALFORMED = InvariantError("SCHEMA", "model returned no JSON object")


# --- 1. room for the reply ---


def test_a_call_that_fits_only_without_its_reply_is_not_sent(tmp_path: Path):
    adapter = Replies(min_reply=300, size=1000)  # the brief alone fits 1,200; with its reply it does not
    m = _run("room-1")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget(max_tokens_per_call=1200)).run_single(
            m, context="c", operator_question="?")
    assert "plus ~300 for the reply" in str(e.value) and "not sent" in str(e.value)
    assert adapter.briefs == [] and m.calls == []


def test_the_room_grows_with_the_largest_reply_seen(tmp_path: Path):
    adapter = Replies(usage={"prompt_tokens": 50, "completion_tokens": 1400}, size=150)
    m = _run("room-2")
    engine = Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget(max_tokens_per_call=1500))
    with pytest.raises(InvariantError) as e:
        engine.run_single(m, context="c", operator_question="?")
    assert len(m.calls) == 1  # the first call's 1,400-token reply leaves no room for the next brief
    assert "plus ~1400 for the reply" in str(e.value)


def test_the_live_adapter_leaves_room_before_its_first_reply(tmp_path: Path):
    engine = Engine(MemoryStore(tmp_path), adapter=LiveAdapter("https://api.example.invalid/v1", "k", "m"))
    assert engine._reply_room(_run("room-3")) == LiveAdapter.min_reply_tokens == 200
    assert Engine(MemoryStore(tmp_path / "b"))._reply_room(_run("room-4")) == 0  # the stub's replies are known


# --- 2. one retry for a malformed reply ---


def test_a_malformed_reply_is_asked_again_and_the_run_goes_on(tmp_path: Path):
    adapter = Replies(MALFORMED)
    m = _run("retry-1")
    engine = Engine(MemoryStore(tmp_path), adapter=adapter)
    result = engine.run_single(m, context="c", operator_question="?")
    assert result.verified and m.status == Status.COMPLETE
    assert [c.get("failed") for c in m.calls] == ["SCHEMA", None, None]  # the slip, its retry, the verifier
    assert adapter.briefs[1].packet.endswith(RETRY_NOTE) and not adapter.briefs[0].packet.endswith(RETRY_NOTE)
    assert [e.event for e in m.log].count("retry") == 1
    assert m.review["outcome"] == "complete" and m.review["lessons"] == [LESSONS["schema"]]
    assert engine.store.lessons() == [(LESSONS["schema"], 1)]


def test_a_reply_malformed_twice_stops_the_run(tmp_path: Path):
    m = _run("retry-2")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=Replies(MALFORMED, MALFORMED)).run_single(m, context="c", operator_question="?")
    assert e.value.code == "SCHEMA" and [c["failed"] for c in m.calls] == ["SCHEMA", "SCHEMA"]


@pytest.mark.parametrize("code", ["ROSTER", "LIVE", "TOOLS", "BUDGET"])
def test_only_a_malformed_reply_is_retried(tmp_path: Path, code):
    adapter = Replies(InvariantError(code, "no"))
    m = _run(f"retry-3-{code}")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=adapter).run_single(m, context="c", operator_question="?")
    assert e.value.code == code and len(adapter.briefs) == 1 and not any(ev.event == "retry" for ev in m.log)


def test_a_retry_is_a_budgeted_call(tmp_path: Path):
    adapter = Replies(MALFORMED)
    m = _run("retry-4")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget(max_calls=1)).run_single(m, context="c", operator_question="?")
    assert "max_calls 1 reached" in str(e.value) and len(adapter.briefs) == 1


def test_a_sub_agent_that_slips_once_keeps_its_part(tmp_path: Path):
    def reply(brief):
        if brief.slot_function == "worker" and brief.channel_id == "b" and RETRY_NOTE not in brief.packet:
            return MALFORMED
        return _art()

    m = _run("retry-5")
    Engine(MemoryStore(tmp_path), adapter=Replies(*[reply] * 20), budget=Budget(max_calls=40, max_tokens=200_000)).run_fanout(
        m, context="c", subtasks=[Subtask("a", "x"), Subtask("b", "x")], axes=["parallel"], operator_question="?")
    assert m.status == Status.COMPLETE
    assert {d.channel_id for d in m.deltas if d.stream == "merge"} == {"a", "b"}  # b was asked again, not covered
    assert not any(e.event == "part_failed" for e in m.log)


class _Endpoint(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        content = self.server.replies.pop(0)
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class _Quick(ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def test_the_live_adapter_recovers_from_one_malformed_reply_over_http(tmp_path: Path):
    server = _Quick(("127.0.0.1", 0), _Endpoint)
    server.replies = ["Sure! Here is the product: ANSWER: 1", GOOD, GOOD]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        m = _run("retry-6")
        adapter = LiveAdapter(f"http://127.0.0.1:{server.server_port}/v1", "test-key", "m", timeout=5)
        assert Engine(MemoryStore(tmp_path), adapter=adapter).run_single(m, context="c", operator_question="?").verified
        assert [c.get("failed") for c in m.calls] == ["SCHEMA", None, None]
    finally:
        server.shutdown()
        server.server_close()


def test_the_scripted_model_needs_two_bad_replies_to_fail(tmp_path: Path):
    m = _run("retry-7")
    adapter = ScriptedLive(["not json", GOOD, GOOD])
    assert Engine(MemoryStore(tmp_path), adapter=adapter).run_single(m, context="c", operator_question="?").verified


# --- 3. a run verified only against the defaults says so ---


def test_a_run_on_the_default_criteria_carries_a_warning(tmp_path: Path):
    m = _run("crit-1", criteria=None)
    assert tuple(m.state.success_criteria) == DEFAULT_CRITERIA
    Engine(MemoryStore(tmp_path)).run_single(m, context="c", operator_question="?")
    report = diagnose(m)
    assert report["warnings"] == ["verified_against_default_criteria"] and report["health"] == "ok"
    named = _run("crit-2")
    Engine(MemoryStore(tmp_path / "b"), adapter=Replies()).run_single(named, context="c", operator_question="?")
    assert diagnose(named)["warnings"] == []


def test_the_cli_says_when_only_the_defaults_were_checked(tmp_path: Path, capsys):
    assert main(["single", "--store", str(tmp_path / "s"), "--out", str(tmp_path / "a.json")]) == 0
    assert "default criteria" in json.loads(capsys.readouterr().out.split("\n\nsaved")[0])["warning"]
    assert main(["single", "--criteria", "default task", "--criteria", "outline", "--store", str(tmp_path / "s"),
                 "--out", str(tmp_path / "b.json")]) in (0, 1)
    assert "warning" not in capsys.readouterr().out.split("\n\nsaved")[0]


def test_the_oldest_default_criteria_are_flagged_too(tmp_path: Path):
    m = _run("crit-3", criteria=[c.title() for c in LEGACY_DEFAULT_CRITERIA])
    assert diagnose(load_run(save_run(m, tmp_path / "r.json")))["warnings"] == ["verified_against_default_criteria"]


# --- 4. the verifier checks the goal ---


def test_the_verifier_is_told_to_check_the_goal_and_is_given_it():
    brief = Brief("verifier", "verify", "the product", "Write a five-line status of what the Genet kernel proved",
                  "p", "c", "d", mode="verify")
    prompt = system_prompt(brief)
    assert "answers the goal, its subject and its question" in prompt
    assert "FAIL a product about something other than the goal, even if it repeats the criteria" in prompt
    user = json.loads(LiveAdapter("https://api.example.invalid/v1", "k", "m")._payload(brief)["messages"][1]["content"])
    assert user["goal"] == "Write a five-line status of what the Genet kernel proved"


def test_an_off_goal_product_fails_even_when_it_repeats_the_criteria(tmp_path: Path):
    """The playwright case from the past live data, with a verifier that judges the goal."""
    playwright = _art(claim="Jean Genet proved that identity is fluid. Default task done; purpose served.")
    m = _run("goal-1", criteria=list(DEFAULT_CRITERIA))
    m.state.goal = "Write a five-line status of what the Genet kernel proved"
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=Replies(playwright, _art(claim="FAIL: about the playwright, not the kernel")),
               budget=Budget.for_tier("tight")).run_single(m, context="c", operator_question="?")
    assert e.value.code == "VERIFY" and m.last_verify["score"] == 1.0  # the criteria matched; the verdict did not


def test_the_gate_and_the_size_check_keep_the_same_room_for_a_reply(tmp_path: Path):
    """A short planning reply must not convince the gate that work fits a call the size check would refuse."""
    engine = Engine(MemoryStore(tmp_path), adapter=Replies(min_reply=300))
    m = _run("room-5")
    m.record_call({"slot": "lead-1", "function": "lead", "channel": "lead", "prompt_tokens": 500, "completion_tokens": 10})
    assert engine._overhead(m) == 500 + 300
    m.record_call({"slot": "lead-1", "function": "lead", "channel": "lead", "prompt_tokens": 500, "completion_tokens": 450})
    assert engine._overhead(m) == 500 + 450  # a reply larger than the room counts as itself
