"""Calls never loop, and token usage is counted exactly.

A hostile stand-in model does random damage: tool floods, proposal floods, malformed replies,
failed calls, authority violations, failing verdicts, and token counts that are random, missing
or not numbers. Across random budgets, strategies, entry points and parallelism, every run must:

- end, complete or aborted, in bounded time, leaving no thread behind;
- make no more calls than max_calls, retries and failed calls included;
- record every call the model was given, exactly once;
- record each call's tokens as the model reported them, or the kernel's estimate when it did not;
- spend under max_tokens plus one call's cap;
- report the same totals everywhere: the run, diagnose, a comparison trial, a saved and reloaded run.
"""

import random
import threading
import time
from pathlib import Path

import pytest

from taskorg.adapters import ModelAdapter
from taskorg.budget import Budget
from taskorg.compare import AlwaysSplit, SingleAgent
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.persist import load_run, save_run
from taskorg.tools import Toolbox


class Hostile(ModelAdapter):
    """Seeded, so a failing seed reproduces. Logs what it reported for every call it was given."""

    name = "hostile"

    def __init__(self, seed: int, per_call: int):
        self.rng, self.per_call = random.Random(seed), per_call
        self.lock = threading.Lock()
        self.given: list[dict] = []  # one entry per act(): what usage it reported
        self._local = threading.local()

    @property
    def last_usage(self):
        return getattr(self._local, "usage", {})

    def _usage(self):
        r = self.rng.random()
        if r < 0.25:
            return {}  # not reported
        if r < 0.35:
            return {"prompt_tokens": self.rng.choice([-5, "12", 3.5, None, True]), "completion_tokens": self.rng.choice([-1, [], 7])}
        cap = max(2, self.per_call // 3)
        return {"prompt_tokens": self.rng.randint(1, cap), "completion_tokens": self.rng.randint(1, cap)}

    def act(self, brief):
        with self.lock:
            usage, roll, n = self._usage(), self.rng.random(), self.rng.randint(0, 20)
            self.given.append({"usage": usage, "mode": brief.mode, "fn": brief.slot_function})
        self._local.usage = usage
        time.sleep(self.rng.random() * 0.002)
        if roll < 0.10:
            raise InvariantError("SCHEMA", "model returned no JSON object")
        if roll < 0.14:
            raise InvariantError("LIVE", "model endpoint returned 500")
        if roll < 0.16:
            raise InvariantError("ROSTER", "model tried to change the roster; rejected")
        requests = []
        if brief.mode == "plan" and roll < 0.7:
            requests = [f"subtask:p{i}@retrieve=keep_apart" for i in range(n)]
        elif roll < 0.5:
            requests = [f"read:f{i % 3}.md" for i in range(n)]
        claim = "PASS ANSWER: 1" if (brief.mode != "verify" or roll < 0.75) else "FAIL: not yet"
        return Artifact(claim=claim, evidence=[], uncertainty="", channel_id="x", context_update=claim, requests=requests)


def _run_one(seed: int, tmp: Path) -> dict:
    rng = random.Random(seed)
    per_call = rng.choice([300, 1500, 4000, 16000])
    budget = Budget(max_calls=rng.randint(1, 30), max_tokens=rng.randint(200, 60_000), max_seconds=10.0,
                    max_tokens_per_call=per_call, allow_split=rng.random() < 0.8, allow_adapt=rng.random() < 0.8, tier="open")
    ws = tmp / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (ws / f"f{i}.md").write_text(f"note {i} " * rng.randint(1, 400))
    strategy = rng.choice([Engine, Engine, AlwaysSplit, SingleAgent])
    model = Hostile(seed, per_call)
    engine = strategy(MemoryStore(tmp / "s"), adapter=model, budget=budget, parallel=rng.random() < 0.7,
                      toolbox=Toolbox(roots=[ws]) if rng.random() < 0.7 else Toolbox(),
                      max_tool_rounds=rng.randint(0, 4), isolation_required=rng.random() < 0.5, lessons=rng.random() < 0.5)
    m = new_run(f"bound-{seed}", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    entry = rng.choice(["task", "task", "single", "fanout", "replan"])
    outcome = {}

    def go():
        try:
            if entry == "task":
                engine.run_task(m, context="subtask:a@retrieve=x subtask:b@retrieve=y")
            elif entry == "single":
                engine.run_single(m, context="c", operator_question="?")
            elif entry == "fanout":
                engine.run_fanout(m, context="c", subtasks=[Subtask(f"q{i}", "x", skill="retrieve") for i in range(rng.randint(0, 6))],
                                  axes=["parallel"], operator_question="?")
            else:
                engine.run_replan(m, context="c", replan_reason="r", new_method="m", axes=["sequential"])
        except InvariantError:
            pass
        except Exception as e:  # a crash is a finding
            outcome["crash"] = repr(e)

    threads_before = threading.active_count()
    t = threading.Thread(target=go, daemon=True)
    started = time.monotonic()
    t.start()
    t.join(timeout=20)
    outcome.update(model=model, run=m, budget=budget, hung=t.is_alive(), seconds=time.monotonic() - started,
                   threads_left=threading.active_count() - threads_before, entry=entry, strategy=strategy.__name__)
    return outcome


@pytest.mark.parametrize("seed", range(400))
def test_calls_end_and_every_token_is_counted(tmp_path: Path, seed):
    o = _run_one(seed, tmp_path)
    m, model, b = o["run"], o["model"], o["budget"]
    where = f"seed {seed}: {o['strategy']}.{o['entry']}, max_calls={b.max_calls} max_tokens={b.max_tokens} per_call={b.max_tokens_per_call}"

    # It ends, without a crash, and leaves no thread running.
    assert not o["hung"], f"run did not end: {where}"
    assert "crash" not in o, f"{o.get('crash')}: {where}"
    assert m.status.value in ("complete", "abort"), where
    assert o["threads_left"] <= 0, f"{o['threads_left']} threads left behind: {where}"

    # No more calls than the budget allows, failed calls and retries included.
    assert len(m.calls) <= b.max_calls, where
    # Every call the model was given is on the record, once.
    assert len(model.given) == len(m.calls), f"{len(model.given)} given vs {len(m.calls)} recorded: {where}"

    # Each call's tokens: as reported when the report is a whole, non-negative number; else an estimate.
    reported = [(g["usage"].get("prompt_tokens"), g["usage"].get("completion_tokens")) for g in model.given]
    for c in m.calls:
        assert isinstance(c["prompt_tokens"], int) and c["prompt_tokens"] >= 1, where
        assert isinstance(c["completion_tokens"], int) and c["completion_tokens"] >= 0, where
    valid = lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0  # noqa: E731
    real_calls = [c for c in m.calls if not c["tokens_estimated"]]
    real_reports = [r for r in reported if valid(r[0]) or valid(r[1])]
    assert len(real_calls) == len(real_reports), where
    for c in real_calls:
        assert any((not valid(p) or c["prompt_tokens"] == p) and (not valid(q) or c["completion_tokens"] == q)
                   for p, q in real_reports), f"call tokens {c['prompt_tokens']}/{c['completion_tokens']} not as reported: {where}"

    # Spend stays under the token budget plus one call's cap, when no single call overran its cap.
    calls, tokens = m.usage()
    if all(c["prompt_tokens"] + c["completion_tokens"] <= b.max_tokens_per_call for c in m.calls):
        assert tokens < b.max_tokens + b.max_tokens_per_call, f"spent {tokens}: {where}"

    # The same totals everywhere.
    perf = diagnose(m)["performance"]
    assert (perf["calls"], perf["tokens"]) == (calls, tokens), where
    loaded = load_run(save_run(m, tmp_path / "r.json"))
    assert loaded.usage() == (calls, tokens), where


# --- two token gaps, closed ---

import json  # noqa: E402
import socketserver  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from taskorg.adapters import Brief  # noqa: E402
from taskorg.live import LiveAdapter  # noqa: E402

GOOD = json.dumps({"claim": "PASS ANSWER: 1", "evidence": [], "uncertainty": "", "channel_id": "c",
                   "context_update": "ANSWER: 1", "requests": []})


class Wordy(ModelAdapter):
    """Reports no usage, and writes most of its reply outside the claim."""

    name = "wordy"

    def act(self, brief):
        return Artifact(claim="PASS ANSWER: 1", evidence=["x" * 4000], uncertainty="u" * 2000, channel_id="c",
                        context_update="ANSWER: 1 " + "y" * 2000, requests=[])


def test_an_unreported_reply_is_counted_whole_not_by_its_claim(tmp_path: Path):
    m = new_run("whole-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    Engine(MemoryStore(tmp_path), adapter=Wordy()).run_single(m, context="c", operator_question="?")
    assert all(c["completion_tokens"] >= 2000 and c["tokens_estimated"] for c in m.calls)


class _Endpoint(BaseHTTPRequestHandler):
    """Replies as told. With honor_cap, it stops a reply at max_tokens, as a real endpoint does."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen.append(body)
        content, usage = self.server.reply
        cap = body.get("max_tokens")
        if self.server.honor_cap and cap is not None and len(content) > cap * 4:
            content = content[: cap * 4]  # cut mid-JSON, as a length stop does
        out = {"choices": [{"message": {"content": content}}]}
        if usage is not None:
            out["usage"] = usage
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class _Quick(ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


@pytest.fixture
def endpoint():
    server = _Quick(("127.0.0.1", 0), _Endpoint)
    server.seen, server.reply, server.honor_cap = [], (GOOD, None), False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def _live(server, **kw):
    return LiveAdapter(f"http://127.0.0.1:{server.server_port}/v1", "test-key", "m", timeout=5, **kw)


def test_without_reported_usage_the_live_adapter_counts_the_wire(endpoint, tmp_path: Path):
    m = new_run("wire-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    Engine(MemoryStore(tmp_path), adapter=_live(endpoint)).run_single(m, context="c", operator_question="?")
    sent = [sum(len(x["content"]) for x in body["messages"]) for body in endpoint.seen]
    assert [c["prompt_tokens"] for c in m.calls] == [-(-n // 4) + 8 for n in sent]
    assert all(c["completion_tokens"] == -(-len(GOOD) // 4) and c["tokens_estimated"] for c in m.calls)


def test_a_malformed_reply_without_usage_is_still_counted(endpoint, tmp_path: Path):
    endpoint.reply = ("not json " * 500, None)
    m = new_run("wire-2", "g", "p", "d")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path), adapter=_live(endpoint)).run_single(m, context="c", operator_question="?")
    assert [(c["failed"], c["completion_tokens"]) for c in m.calls] == [("SCHEMA", -(-4500 // 4))] * 2  # the slip and its retry


def test_reported_usage_is_used_as_reported(endpoint, tmp_path: Path):
    endpoint.reply = (GOOD, {"prompt_tokens": 1234, "completion_tokens": 56})
    m = new_run("wire-3", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    Engine(MemoryStore(tmp_path), adapter=_live(endpoint)).run_single(m, context="c", operator_question="?")
    assert [(c["prompt_tokens"], c["completion_tokens"], c["tokens_estimated"]) for c in m.calls] == [(1234, 56, False)] * 2


def test_every_live_request_caps_its_reply_at_what_the_call_has_left(endpoint, tmp_path: Path):
    adapter = _live(endpoint)
    m = new_run("cap-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget(max_tokens_per_call=3000)).run_single(
        m, context="c", operator_question="?")
    for body in endpoint.seen:
        size = -(-sum(len(x["content"]) for x in body["messages"]) // 4) + 8
        assert body["max_tokens"] == 3000 - size  # the cap less the request, never more


@pytest.mark.parametrize("param, expect", [("max_completion_tokens", "max_completion_tokens"), ("none", None)])
def test_the_reply_cap_field_can_be_renamed_or_turned_off(endpoint, tmp_path: Path, monkeypatch, param, expect):
    for k, v in {"TASKORG_MODEL_BASE": f"http://127.0.0.1:{endpoint.server_port}/v1", "TASKORG_MODEL_KEY": "test-key",
                 "TASKORG_MODEL_NAME": "m", "TASKORG_MODEL_MAX_TOKENS_PARAM": param}.items():
        monkeypatch.setenv(k, v)
    m = new_run("cap-2", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    Engine(MemoryStore(tmp_path), adapter=LiveAdapter.from_env()).run_single(m, context="c", operator_question="?")
    for body in endpoint.seen:
        assert "max_tokens" not in body
        assert (expect in body) if expect else not any("tokens" in k for k in body)


def test_a_bad_reply_cap_field_name_is_refused():
    with pytest.raises(InvariantError) as e:
        LiveAdapter("https://api.example.invalid/v1", "k", "m", max_reply_param="Max Tokens!")
    assert e.value.code == "LIVE"


def test_a_reply_cut_at_the_cap_ends_after_one_retry_not_a_loop(endpoint, tmp_path: Path):
    """The endpoint stops a long reply at max_tokens, mid-JSON. The kernel asks once more, then stops."""
    endpoint.honor_cap, endpoint.reply = True, (json.dumps({"claim": "x" * 40_000}), {"prompt_tokens": 100, "completion_tokens": 500})
    m = new_run("cap-3", "g", "p", "d")
    started = time.monotonic()
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=_live(endpoint), budget=Budget(max_tokens_per_call=2000)).run_single(
            m, context="c", operator_question="?")
    assert e.value.code == "SCHEMA" and len(endpoint.seen) == 2 and len(m.calls) == 2
    assert time.monotonic() - started < 5


def test_a_model_that_always_asks_for_tools_runs_out_of_rounds_not_forever(tmp_path: Path):
    class Reader(ModelAdapter):
        name = "reader"
        given = 0

        def act(self, brief):
            Reader.given += 1
            reading = brief.mode == "work"  # never satisfied: asks for more on every round
            return Artifact(claim="still reading" if reading else "FAIL", evidence=[], uncertainty="", channel_id="c",
                            context_update="", requests=["read:f0.md"] if reading else [])

    (tmp_path / "f0.md").write_text("note")
    m = new_run("rounds-1", "g", "p", "d")
    with pytest.raises(InvariantError):
        Engine(MemoryStore(tmp_path / "s"), adapter=Reader(), max_tool_rounds=3, toolbox=Toolbox(roots=[tmp_path])).run_task(
            m, context="c")
    assert any(e.event == "tool_rounds_exhausted" for e in m.log)
    # plan, work and its 3 rounds, verify, one rework, verify again: then the run stops
    assert Reader.given == len(m.calls) == 1 + (1 + 3) + 1 + 1 + 1
