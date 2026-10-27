"""Claude through the Messages API, tapes that replay a live run with no key, and a spend cap.

The anthropic adapter runs on a stand-in client here; two tests run the real SDK against a local
endpoint when the SDK is installed. The tape tests record a comparison, replay it with no client
at all, and expect the same results.
"""

import builtins
import json
import socketserver
import threading
import types
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from taskorg import anthropic_live, cli, tape
from taskorg.adapters import Brief
from taskorg.anthropic_live import DEFAULT_MAX_REPLY, MAX_REPLY_CEILING, AnthropicAdapter
from taskorg.compare import TrialResult, run_comparison, spend_cap
from taskorg.errors import InvariantError
from taskorg.live import LiveAdapter
from taskorg.sim import SimModel
from taskorg.suite import build_suite
from taskorg.tools import Toolbox

GOOD = json.dumps({"claim": "PASS ANSWER: 1", "evidence": [], "uncertainty": "", "channel_id": "c",
                   "context_update": "", "requests": []})
MODEL = "claude-haiku-5-5"


def _brief(**kw):
    base = dict(slot_function="lead", skill="draft", packet="p", goal="g", purpose="u", context="c", done_when="d")
    return Brief(**(base | kw))


def _msg(text="", usage=None, stop="end_turn", blocks=None, details=None):
    content = blocks if blocks is not None else [types.SimpleNamespace(type="thinking", thinking=""),
                                                 types.SimpleNamespace(type="text", text=text)]
    u = None if usage is False else types.SimpleNamespace(**(usage or {"input_tokens": 100, "output_tokens": 20}))
    return types.SimpleNamespace(content=content, usage=u, stop_reason=stop, stop_details=details)


class Client:
    """Stands in for anthropic.Anthropic: keeps each request and answers from a function."""

    def __init__(self, answer):
        self.requests = []
        outer = self

        class Messages:
            @staticmethod
            def create(**kw):
                outer.requests.append(kw)
                return answer(kw)

        self.messages = Messages()


def _adapter(answer=lambda kw: _msg(GOOD), **kw):
    client = Client(answer)
    return AnthropicAdapter("", MODEL, client=client, **kw), client


def _sim_answer(kw):
    """The simulated reader behind a Messages-shaped reply, with thinking tokens in the usage."""
    u = json.loads(kw["messages"][0]["content"])
    brief = Brief(slot_function=u["function"], skill=u["skill"], packet=u["packet"], goal=u["goal"], purpose=u["purpose"],
                  context=u["context"], done_when=u["done_when"], channel_id=u["channel_id"] or "", isolated=u["isolated"],
                  tools=u["tools"], success_criteria=u["success_criteria"], mode=u["mode"])
    text = json.dumps(asdict(SimModel().act(brief)))
    chars = len(kw["system"]) + len(kw["messages"][0]["content"])
    return _msg(text, {"input_tokens": -(-chars // 4), "output_tokens": -(-len(text) // 4) + 30,
                       "output_tokens_details": types.SimpleNamespace(thinking_tokens=30)})


# --- the request ---


def test_request_has_no_temperature_and_caps_the_reply():
    a, c = _adapter(effort="low")
    a.act(_brief(max_reply_tokens=900))
    req = c.requests[0]
    assert "temperature" not in req
    assert req["max_tokens"] == 900
    assert req["output_config"] == {"effort": "low"}
    assert req["system"].startswith("You are the lead agent")
    assert [m["role"] for m in req["messages"]] == ["user"]


def test_reply_cap_has_a_default_and_a_ceiling():
    a, c = _adapter()
    a.act(_brief())
    a.act(_brief(max_reply_tokens=10**6))
    assert [r["max_tokens"] for r in c.requests] == [DEFAULT_MAX_REPLY, MAX_REPLY_CEILING]
    assert "output_config" not in c.requests[0]


def test_an_unknown_effort_is_refused():
    with pytest.raises(InvariantError, match="TASKORG_MODEL_EFFORT"):
        AnthropicAdapter("", MODEL, effort="extreme", client=Client(lambda kw: None))


def test_size_estimate_counts_the_system_prompt():
    a, _ = _adapter()
    b = _brief(packet="x" * 400)
    assert a.estimate_tokens(b) > (400 + len(a._payload(b)["system"])) // 4


# --- the reply ---


def test_usage_counts_cache_reads_and_records_thinking():
    a, _ = _adapter(lambda kw: _msg(GOOD, {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 7,
                                            "cache_creation_input_tokens": None,
                                            "output_tokens_details": types.SimpleNamespace(thinking_tokens=30)}))
    a.act(_brief())
    assert a.last_usage == {"prompt_tokens": 107, "completion_tokens": 50, "thinking_tokens": 30}


def test_missing_usage_is_estimated_and_says_so():
    a, _ = _adapter(lambda kw: _msg(GOOD, usage=False))
    a.act(_brief())
    assert a.last_usage["estimated"] is True and a.last_usage["prompt_tokens"] > 100


def test_only_text_blocks_make_the_reply():
    blocks = [types.SimpleNamespace(type="thinking", thinking='{"claim": "not this"}'),
              types.SimpleNamespace(type="text", text=GOOD)]
    a, _ = _adapter(lambda kw: _msg(blocks=blocks))
    assert a.act(_brief()).claim == "PASS ANSWER: 1"


def test_a_refusal_is_a_live_failure_and_its_tokens_count():
    a, _ = _adapter(lambda kw: _msg("", stop="refusal", details=types.SimpleNamespace(category="cyber")))
    with pytest.raises(InvariantError) as e:
        a.act(_brief())
    assert e.value.code == "LIVE" and "declined" in e.value.message and "cyber" in e.value.message
    assert a.last_usage["prompt_tokens"] == 100


class APIStatusError(Exception):
    def __init__(self, status):
        super().__init__("rate limited")
        self.status_code, self.message = status, "rate limited"


class APITimeoutError(Exception):
    pass


@pytest.mark.parametrize("exc, text", [
    (APIStatusError(429), "returned 429: rate limited"),
    (APITimeoutError("x"), "too slow"),
    (ConnectionError("down"), "ConnectionError: down"),
])
def test_sdk_errors_become_live_failures(exc, text):
    def boom(kw):
        raise exc
    a, _ = _adapter(boom)
    with pytest.raises(InvariantError) as e:
        a.act(_brief())
    assert e.value.code == "LIVE" and text in e.value.message


# --- configuration ---


class FakeSDK:
    def __init__(self):
        self.made = []

    def Anthropic(self, **kw):  # noqa: N802 - the SDK's name
        self.made.append(kw)
        return Client(lambda kw: _msg(GOOD))

    def DefaultHttpxClient(self, **kw):  # noqa: N802
        return ("http", kw)


@pytest.fixture
def sdk(monkeypatch):
    fake = FakeSDK()
    monkeypatch.setattr(anthropic_live, "_sdk", lambda: fake)
    for k in ("TASKORG_ANTHROPIC_KEY", "TASKORG_ANTHROPIC_BASE", "TASKORG_MODEL_EFFORT", "TASKORG_MODEL_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TASKORG_MODEL_NAME", MODEL)
    return fake


def test_the_key_comes_only_from_taskorg_anthropic_key(sdk, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-another-tool")
    with pytest.raises(InvariantError, match="TASKORG_ANTHROPIC_KEY"):
        AnthropicAdapter.from_env()
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "sk-genet")
    # The live adapter's endpoint must never receive this key.
    monkeypatch.setenv("TASKORG_MODEL_BASE", "https://other-provider.example/v1")
    a = AnthropicAdapter.from_env()
    made = sdk.made[-1]
    assert made["api_key"] == "sk-genet" and made["base_url"] == "https://api.anthropic.com"
    assert made["http_client"] == ("http", {"follow_redirects": False})
    assert a.api_key == "" and "sk-genet" not in json.dumps(a.tape_header())


def test_plain_http_to_another_host_is_refused(sdk, monkeypatch):
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "sk-genet")
    monkeypatch.setenv("TASKORG_ANTHROPIC_BASE", "http://api.example.com")
    with pytest.raises(InvariantError, match="https"):
        AnthropicAdapter.from_env()
    assert sdk.made == []


def test_effort_and_timeout_come_from_the_environment(sdk, monkeypatch):
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "sk-genet")
    monkeypatch.setenv("TASKORG_MODEL_EFFORT", "LOW")
    a = AnthropicAdapter.from_env()
    assert a.effort == "low" and sdk.made[-1]["timeout"] == 60
    monkeypatch.setenv("TASKORG_MODEL_TIMEOUT", "0")
    with pytest.raises(InvariantError, match="TASKORG_MODEL_TIMEOUT"):
        AnthropicAdapter.from_env()


def test_a_missing_sdk_says_how_to_install(monkeypatch):
    real = builtins.__import__

    def no_sdk(name, *a, **k):
        if name == "anthropic":
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_sdk)
    with pytest.raises(InvariantError, match=r"taskorg\[anthropic\]"):
        AnthropicAdapter("k", MODEL)


# --- the real SDK, against a local endpoint ---


def _serve(handler):
    class Server(ThreadingHTTPServer):
        def server_bind(self):  # no reverse DNS on 127.0.0.1
            socketserver.TCPServer.server_bind(self)
            self.server_name, self.server_port = self.server_address[:2]

    srv = Server(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _handler(seen, status=200, location=None):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
            reply = json.dumps({"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                                "content": [{"type": "text", "text": GOOD}], "stop_reason": "end_turn",
                                "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 3}}).encode()
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *a):
            pass

    return H


def test_the_real_sdk_sends_the_key_and_no_temperature():
    pytest.importorskip("anthropic")
    seen = []
    srv = _serve(_handler(seen))
    try:
        a = AnthropicAdapter("sk-test", MODEL, timeout=10, base_url=f"http://127.0.0.1:{srv.server_port}", effort="low")
        assert a.act(_brief(max_reply_tokens=500)).claim == "PASS ANSWER: 1"
    finally:
        srv.shutdown()
    assert seen[0]["path"] == "/v1/messages" and seen[0]["auth"] == "Bearer sk-test"
    assert "temperature" not in seen[0]["body"] and seen[0]["body"]["max_tokens"] == 500
    assert a.last_usage == {"prompt_tokens": 5, "completion_tokens": 3}


def test_the_real_sdk_follows_no_redirect():
    pytest.importorskip("anthropic")
    elsewhere = []
    other = _serve(_handler(elsewhere))
    seen = []
    srv = _serve(_handler(seen, status=307, location=f"http://127.0.0.1:{other.server_port}/v1/messages"))
    try:
        a = AnthropicAdapter("sk-test", MODEL, timeout=10, base_url=f"http://127.0.0.1:{srv.server_port}")
        with pytest.raises(InvariantError) as e:
            a.act(_brief())
    finally:
        srv.shutdown()
        other.shutdown()
    assert e.value.code == "LIVE" and "307" in e.value.message
    assert len(seen) == 1 and elsewhere == []


# --- tapes ---

SUITE = dict(seed=7, per_family=1, families=("lookup", "breadth"))


def _compare(factory, strategies=("single", "always", "genet"), **kw):
    return run_comparison(build_suite(**SUITE), factory, strategies=strategies, **kw)


def _same(r):
    return (r.task_id, r.strategy, r.answer, r.correct, r.calls, r.tokens, r.workers, r.status, r.code)


def test_a_replay_gives_the_recorded_results_with_no_client(tmp_path):
    client = Client(_sim_answer)
    header = AnthropicAdapter("", MODEL, effort="low", client=client).tape_header()
    rec = tape.Recorder(tmp_path / "t.jsonl", header)

    def live():
        a = AnthropicAdapter("", MODEL, effort="low", client=client)
        a.tape = rec
        return a

    recorded = _compare(live)
    rec.close()
    player = tape.Player(tmp_path / "t.jsonl")
    replayed = _compare(lambda: tape.replay_adapter(player))
    assert [_same(r) for r in replayed] == [_same(r) for r in recorded]
    assert any(r.workers for r in recorded)  # tool results and sub-agents are on the tape too
    assert player.misses == 0 and player.served == rec.count == len(client.requests)
    assert not any(r.tokens_estimated for r in replayed)


def test_a_changed_request_misses_and_is_counted(tmp_path):
    a, _ = _adapter()
    a.tape = tape.Recorder(tmp_path / "t.jsonl", a.tape_header())
    a.act(_brief())
    a.tape.close()
    player = tape.Player(tmp_path / "t.jsonl")
    b = tape.replay_adapter(player)
    assert b.act(_brief()).claim == "PASS ANSWER: 1"
    with pytest.raises(InvariantError) as e:
        b.act(_brief(goal="a different goal"))
    assert e.value.code == "LIVE" and e.value.message.startswith("replay:")
    assert (player.served, player.misses) == (1, 1) and b.last_usage == {}


def test_the_reply_cap_is_not_part_of_the_request_key():
    k = tape.request_key
    assert k({"a": 1, "max_tokens": 5}, "max_tokens") == k({"a": 1, "max_tokens": 9}, "max_tokens")
    assert k({"a": 1, "max_tokens": 5}, "max_tokens") != k({"a": 2, "max_tokens": 5}, "max_tokens")


def test_a_recorded_error_replays_as_that_error_with_its_usage(tmp_path):
    a, _ = _adapter(lambda kw: _msg("", stop="refusal"))
    a.tape = tape.Recorder(tmp_path / "t.jsonl", a.tape_header())
    with pytest.raises(InvariantError):
        a.act(_brief())
    a.tape.close()
    b = tape.replay_adapter(tape.Player(tmp_path / "t.jsonl"))
    with pytest.raises(InvariantError) as e:
        b.act(_brief())
    assert e.value.code == "LIVE" and "declined" in e.value.message
    assert b.last_usage["prompt_tokens"] == 100


def test_identical_requests_get_their_replies_in_order_then_the_last(tmp_path):
    answers = iter(["PASS ANSWER: 1", "PASS ANSWER: 2"])
    a, _ = _adapter(lambda kw: _msg(GOOD.replace("PASS ANSWER: 1", next(answers))))
    a.tape = tape.Recorder(tmp_path / "t.jsonl", a.tape_header())
    a.act(_brief())
    a.act(_brief())
    a.tape.close()
    player = tape.Player(tmp_path / "t.jsonl")
    b = tape.replay_adapter(player)
    assert [b.act(_brief()).claim for _ in range(3)] == ["PASS ANSWER: 1", "PASS ANSWER: 2", "PASS ANSWER: 2"]
    assert player.repeated == 1


def test_a_tape_is_never_written_over(tmp_path):
    a, _ = _adapter()
    tape.Recorder(tmp_path / "t.jsonl", a.tape_header()).close()
    with pytest.raises(InvariantError, match="already exists"):
        tape.Recorder(tmp_path / "t.jsonl", a.tape_header())


def test_a_tape_holds_no_key(sdk, monkeypatch, tmp_path):
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "sk-genet-secret")
    a = AnthropicAdapter.from_env()
    a.tape = tape.Recorder(tmp_path / "t.jsonl", a.tape_header())
    a.act(_brief())
    a.tape.close()
    assert "sk-genet-secret" not in (tmp_path / "t.jsonl").read_text()


def test_an_openai_compatible_tape_replays_too(tmp_path, monkeypatch):
    live = LiveAdapter("https://endpoint.invalid", "sk-x", "some-model")

    def post(payload):
        live.last_usage = {"prompt_tokens": 9, "completion_tokens": 4}
        return GOOD

    monkeypatch.setattr(live, "_post", post)
    live.tape = tape.Recorder(tmp_path / "t.jsonl", live.tape_header())
    live.act(_brief(max_reply_tokens=300))
    live.tape.close()
    b = tape.replay_adapter(tape.Player(tmp_path / "t.jsonl"))
    assert b.name == "replay:live" and b.act(_brief(max_reply_tokens=50)).claim == "PASS ANSWER: 1"
    assert b.last_usage == {"prompt_tokens": 9, "completion_tokens": 4}


def _tape(tmp_path, *lines):
    p = tmp_path / "t.jsonl"
    p.write_text("".join(line + "\n" for line in lines))
    return p


HEADER = json.dumps({"tape": 1, "adapter": "anthropic", "model": MODEL, "models": {}, "effort": None,
                     "max_reply_param": "max_tokens"})


def _line(**over):
    return json.dumps({"key": "a" * 64, "request": {}, "reply": GOOD, "usage": {}, "error": None} | over)


@pytest.mark.parametrize("lines, text", [
    ((json.dumps({"tape": 2, "adapter": "anthropic", "model": MODEL}),), "no valid header"),
    ((json.dumps({"tape": 1, "adapter": "other", "model": MODEL}),), "no valid header"),
    ((HEADER, "not json", _line()), "line 2 is not JSON"),
    ((HEADER, _line(key="short")), "line 2 is not a recorded exchange"),
    ((HEADER, _line(reply=None, error={"code": "ROSTER", "message": "x"})), "line 2 is not a recorded exchange"),
    ((HEADER, _line(usage={"prompt_tokens": -1})), "line 2 is not a recorded exchange"),
    ((HEADER, _line(reply=GOOD, error={"code": "LIVE", "message": "x"})), "line 2 is not a recorded exchange"),
])
def test_a_damaged_tape_is_refused(tmp_path, lines, text):
    with pytest.raises(InvariantError, match=text):
        tape.Player(_tape(tmp_path, *lines))


def test_a_partial_last_line_is_dropped(tmp_path):
    player = tape.Player(_tape(tmp_path, HEADER, _line(), _line()[:40]))
    assert sum(len(v) for v in player._replies.values()) == 1


# --- spending ---


def _trial(prompt, completion):
    return TrialResult(task_id="t", family="f", strategy="s", repeat=0, expected="1", answer="1", correct=True,
                       answer_right=True, status="complete", code="", calls=1, tokens=prompt + completion,
                       prompt_tokens=prompt, completion_tokens=completion, tokens_estimated=False, latency_s=0.0, workers=0)


def test_the_spend_cap_stops_at_the_cap_and_before_a_trial_that_could_pass_it():
    stop = spend_cap(1.0, price_in=1.0, price_out=2.0)  # $1 and $2 per million tokens
    assert stop([]) == ""
    assert stop([_trial(300_000, 0)]) == ""  # $0.30 spent; another like it ends at $0.60
    assert "next trial could cost $0.4000" in stop([_trial(300_000, 0), _trial(200_000, 100_000)])
    assert "spent of $1.00" in stop([_trial(600_000, 200_000)])


def test_a_comparison_stops_on_its_rule_and_keeps_what_ran():
    res = _compare(SimModel, stop_when=lambda done: "enough" if len(done) == 2 else "")
    assert len(res) == 2


def test_ctrl_c_keeps_the_trials_already_run():
    made = []

    def factory():
        made.append(1)
        if len(made) == 3:
            raise KeyboardInterrupt
        return SimModel()

    assert len(_compare(factory)) == 2


def test_the_cli_records_replays_and_keeps_to_the_cap(tmp_path, monkeypatch, capsys):
    client = Client(_sim_answer)
    real = cli.pick_adapter
    monkeypatch.setattr(cli, "pick_adapter",
                        lambda name: AnthropicAdapter("", MODEL, effort="low", client=client) if name == "anthropic" else real(name))
    common = ["compare", "--per-family", "1", "--families", "lookup,breadth", "--strategies", "single,genet"]
    t, rec, rep = tmp_path / "t.jsonl", tmp_path / "rec.json", tmp_path / "rep.json"
    assert cli.main([*common, "--adapter", "anthropic", "--record", str(t), "--out", str(rec)]) == 0
    assert cli.main([*common, "--replay", str(t), "--out", str(rep)]) == 0
    assert "0 requests the tape does not have" in capsys.readouterr().out
    a, b = json.loads(rec.read_text()), json.loads(rep.read_text())
    assert [r["answer"] for r in a["results"]] == [r["answer"] for r in b["results"]]
    assert b["config"]["adapter"] == "replay" and b["config"]["replayed"] == "anthropic" and b["config"]["model"] == MODEL
    header = json.loads(t.read_text().splitlines()[0])
    assert header["compare"]["strategies"] == ["single", "genet"] and header["effort"] == "low"
    capped = tmp_path / "capped.json"
    assert cli.main([*common, "--replay", str(t), "--price-in", "1000", "--price-out", "1000", "--max-spend", "0.5",
                     "--out", str(capped)]) == 0
    c = json.loads(capped.read_text())
    assert c["config"]["stopped_after"] == len(c["results"]) == 1 and c["config"]["max_spend"] == 0.5


@pytest.mark.parametrize("extra, text", [
    (["--adapter", "sim", "--max-spend", "1"], "--max-spend needs"),
    (["--adapter", "sim", "--record", "{tmp}/t.jsonl"], "needs a model adapter"),
    (["--record", "{tmp}/a.jsonl", "--replay", "{tmp}/b.jsonl"], "not both"),
])
def test_the_cli_refuses_a_setup_that_would_waste_a_run(tmp_path, capsys, extra, text):
    args = [x.replace("{tmp}", str(tmp_path)) for x in extra]
    assert cli.main(["compare", "--per-family", "1", "--out", str(tmp_path / "o.json"), *args]) == 1
    assert text in capsys.readouterr().out
    assert not (tmp_path / "t.jsonl").exists() and not (tmp_path / "o.json").exists()


# --- what the model sees of the workspace ---


def test_tool_results_name_files_relative_to_the_workspace(tmp_path):
    root = tmp_path / "ws"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "a.md").write_text("alpha revenue 5\n")
    tb = Toolbox(roots=[root])
    assert tb.read("sub/a.md").startswith("[read sub/a.md]\n")
    assert "sub/a.md:1: " in tb.retrieve("alpha revenue")
    assert tb.observe().splitlines()[1] == "sub/a.md"
    seen = tb.retrieve("alpha") + tb.observe() + tb.read("sub/a.md") + tb.retrieve("alpha nothing")
    assert str(tmp_path) not in seen and str(tmp_path.resolve()) not in seen


def test_a_name_two_roots_share_stays_absolute(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.md").write_text("one\n")
    (b / "x.md").write_text("two\n")
    tb = Toolbox(roots=[a, b])
    shown = tb.observe().splitlines()[1:]
    second = str((b / "x.md").resolve())
    assert shown == ["x.md", second]
    assert tb.read(shown[0]).endswith("one\n") and tb.read(second).endswith("two\n")
