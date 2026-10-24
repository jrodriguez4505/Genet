"""Untrusted input stays bounded: the model endpoint, model output, workspace files and saved runs.

Each test is one attack. The endpoint is a fake on localhost; nothing leaves the machine.
"""

import json
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from taskorg import live, tools
from taskorg.adapters import Brief, ModelAdapter
from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.live import LiveAdapter, check_base_url
from taskorg.loop import MAX_TOOL_REQUESTS, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.persist import load_run, save_run
from taskorg.reads import attach_reads
from taskorg.tools import Toolbox

GOOD = json.dumps({"claim": "ok", "evidence": [], "uncertainty": "", "channel_id": "c", "context_update": "", "requests": []})
BRIEF = Brief(slot_function="lead", skill="draft", channel_id=None, goal="g", purpose="p", context="c", done_when="d",
              packet="", isolated=False, mode="work", tools=[], success_criteria=[])


# --- a fake endpoint that answers however the test says ---


class Scripted(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.server.seen.append({"path": self.path, "auth": self.headers.get("Authorization")})
        self.server.answer(self)

    def do_GET(self):
        self.server.seen.append({"path": self.path, "auth": self.headers.get("Authorization")})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


class QuickServer(ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)  # no reverse-DNS stall
        self.server_name, self.server_port = self.server_address[:2]


def _serve(answer):
    server = QuickServer(("127.0.0.1", 0), Scripted)
    server.seen, server.answer = [], answer
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def servers():
    made = []

    def make(answer):
        made.append(_serve(answer))
        return made[-1]

    yield make
    for s in made:
        s.shutdown()
        s.server_close()


def _send(h, status=200, body=b"", headers=()):
    h.send_response(status)
    for k, v in headers:
        h.send_header(k, v)
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _completion(content: str, usage=None) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}], "usage": usage or {}}).encode()


def _url(server):
    return f"http://127.0.0.1:{server.server_port}/v1"


def _act(server, timeout=5):
    return LiveAdapter(_url(server), "sk-test-secret", "m", timeout=timeout).act(BRIEF)


# --- the API key ---


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_a_redirect_is_refused_and_the_key_stays_home(servers, code):
    other = servers(lambda h: None)
    first = servers(lambda h: _send(h, code, headers=[("Location", _url(other) + "/steal")]))
    with pytest.raises(InvariantError) as e:
        _act(first)
    assert e.value.code == "LIVE" and "redirect" in str(e.value)
    assert other.seen == []  # the other host is never contacted
    assert first.seen[0]["auth"] == "Bearer sk-test-secret"


def test_the_key_is_never_copied_onto_a_redirected_request(servers, monkeypatch):
    """Second line of defense: even an opener that follows redirects does not carry the key."""
    import urllib.request

    monkeypatch.setattr(live, "_OPENER", urllib.request.build_opener())
    other = servers(lambda h: None)
    first = servers(lambda h: _send(h, 302, headers=[("Location", _url(other) + "/steal")]))
    with pytest.raises(InvariantError):
        _act(first)
    assert other.seen and other.seen[0]["auth"] is None


@pytest.mark.parametrize("base", [
    "https://api.example.com/v1",
    "http://127.0.0.1:8000/v1",
    "http://localhost:11434/v1",
    "http://[::1]:8000/v1",
])
def test_base_urls_that_keep_the_key_off_the_network_in_clear_text(base):
    assert check_base_url(base) == base


@pytest.mark.parametrize("base", [
    "http://api.example.com/v1",
    "http://192.168.1.20:8000/v1",
    "file:///etc/passwd",
    "ftp://example.com/v1",
    "api.example.com/v1",
    "https:///v1",
])
def test_base_urls_that_would_expose_the_key_are_refused(base):
    with pytest.raises(InvariantError) as e:
        LiveAdapter(base, "k", "m")
    assert e.value.code == "LIVE"


def test_plain_http_off_this_machine_needs_an_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("TASKORG_MODEL_ALLOW_HTTP", "1")
    assert check_base_url("http://192.168.1.20:8000/v1")


def test_the_refusal_does_not_echo_credentials_in_the_url():
    with pytest.raises(InvariantError) as e:
        check_base_url("http://user:hunter2@api.example.com/v1")
    assert "hunter2" not in str(e.value) and "user" not in str(e.value)


# --- the endpoint's reply ---


def test_an_oversized_response_is_refused_without_reading_it_all(servers, monkeypatch):
    monkeypatch.setattr(live, "MAX_RESPONSE_BYTES", 10_000)
    server = servers(lambda h: _send(h, body=_completion("A" * 200_000)))
    with pytest.raises(InvariantError) as e:
        _act(server)
    assert "over 10000 bytes" in str(e.value)


def test_a_response_that_drips_in_is_cut_off_at_the_timeout(servers):
    def drip(h):
        h.send_response(200)
        h.send_header("Content-Length", "1000")
        h.end_headers()
        for _ in range(40):
            try:
                h.wfile.write(b" ")
                h.wfile.flush()
            except OSError:
                return
            time.sleep(0.1)

    server = servers(drip)
    started = time.monotonic()
    with pytest.raises(InvariantError) as e:
        _act(server, timeout=1)
    assert "too slow" in str(e.value)
    assert time.monotonic() - started < 3


def test_an_error_body_is_read_only_as_far_as_the_message_needs(servers):
    server = servers(lambda h: _send(h, 500, body=b"E" * 5_000_000))
    with pytest.raises(InvariantError) as e:
        _act(server)
    assert "returned 500" in str(e.value) and len(str(e.value)) < 400


@pytest.mark.parametrize("body", [
    b"[" * 200_000,                                                                      # nesting too deep
    ('{"choices":[{"message":{"content":%s}}],"usage":{"prompt_tokens":%s}}' % (json.dumps(GOOD), "9" * 5000)).encode(),
    b"\xff\xfe not utf-8",
])
def test_a_malformed_body_stops_the_call_cleanly(servers, body):
    server = servers(lambda h: _send(h, body=body))
    with pytest.raises(InvariantError) as e:
        _act(server)
    assert e.value.code == "LIVE"


@pytest.mark.parametrize("content", [
    '{"claim": ' + "[" * 200_000 + "]" * 200_000 + "}",
    '{"claim": "x", "evidence": [' + "9" * 5000 + "]}",
])
def test_malformed_model_json_is_a_schema_error_not_a_crash(servers, content):
    server = servers(lambda h: _send(h, body=_completion(content)))
    with pytest.raises(InvariantError) as e:
        _act(server)
    assert e.value.code == "SCHEMA"


# --- what one model reply can make the kernel do ---


class Reports(ModelAdapter):
    """Reports whatever usage the test hands it."""

    name = "reports"

    def __init__(self, usage, requests=None):
        self.usage, self.requests, self.briefs = usage, requests or [], []

    def act(self, brief):
        self.briefs.append(brief)
        self.last_usage = dict(self.usage)
        reqs = []
        if brief.mode == "work" and self.requests:  # the working call, where reading is allowed
            reqs, self.requests = self.requests, []
        return Artifact(claim="PASS ANSWER: 1", evidence=[], uncertainty="", channel_id="c", context_update="", requests=reqs)


@pytest.mark.parametrize("bad", [-10**9, True, "100", 12.5, None, [3]])
def test_a_reported_token_count_that_is_not_a_count_is_ignored(tmp_path: Path, bad):
    m = new_run("usage-1", "g", "p", "d")
    adapter = Reports({"prompt_tokens": bad, "completion_tokens": bad})
    try:
        Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget.for_tier("open")).run_single(
            m, context="c", operator_question="?")
    except InvariantError:
        pass  # the stand-in model does not satisfy the verifier; the calls are still on the record
    assert m.calls
    assert all(c["prompt_tokens"] >= 1 and c["completion_tokens"] >= 1 for c in m.calls)
    assert all(c["tokens_estimated"] for c in m.calls)


def test_an_oversized_brief_is_never_sent(tmp_path: Path):
    m = new_run("big-1", "g", "p", "d")
    adapter = Reports({})
    budget = Budget(max_calls=5, max_tokens=100_000, max_tokens_per_call=1000, tier="open")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=adapter, budget=budget).run_single(m, context="x" * 20_000, operator_question="?")
    assert "not sent" in str(e.value)
    assert adapter.briefs == [] and m.calls == []


def test_one_reply_runs_at_most_a_handful_of_tools(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    for i in range(30):
        (ws / f"n{i}.md").write_text(f"note {i}")
    asks = [f"read:n{i}.md" for i in range(30)] + ["read:n0.md"] * 500
    m = new_run("tools-1", "g", "p", "d")
    adapter = Reports({}, requests=asks)
    try:
        Engine(MemoryStore(tmp_path / "s"), adapter=adapter, budget=Budget.for_tier("open"),
               toolbox=Toolbox(roots=[ws])).run_task(m, context="c")
    except InvariantError:
        pass  # the verifier's verdict does not matter here
    assert sum(1 for e in m.log if e.event == "tool") == MAX_TOOL_REQUESTS  # 530 asks, 30 distinct, 8 run
    work = [b for b in adapter.briefs if b.mode == "work"]
    assert f"{30 - MAX_TOOL_REQUESTS} more tool requests not run" in work[1].packet


# --- the workspace sandbox ---


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / ".git").mkdir(parents=True)
    (ws / "docs").mkdir()
    (ws / "docs" / "a.md").write_text("public note")
    (ws / ".env").write_text("TASKORG_MODEL_KEY=sk-live-secret")
    (ws / ".git" / "config").write_text("url = https://token@github.com/x")
    (ws / "env-link.md").symlink_to(ws / ".env")
    return ws


@pytest.mark.parametrize("request_", ["read:.env", "read:.git/config", "read:docs/../.env", "read:env-link.md", "observe:.git"])
def test_hidden_files_stay_hidden_from_every_tool(workspace: Path, request_):
    out = Toolbox(roots=[workspace]).run(request_)
    assert "secret" not in out and "token" not in out
    assert "not found" in out


def test_search_and_listing_skip_hidden_files(workspace: Path):
    box = Toolbox(roots=[workspace])
    assert box.retrieve("sk-live-secret").endswith("no matches") and ".env" not in box.observe()
    assert box.read("docs/a.md").endswith("public note")


def test_an_attached_file_is_readable_even_when_hidden(workspace: Path):
    """The operator named it with --read, so it is not a model's guess."""
    box = Toolbox(roots=[workspace], files=[workspace / ".env"])
    assert "sk-live-secret" in box.read(".env")


def test_a_root_inside_a_hidden_directory_still_works(tmp_path: Path):
    root = tmp_path / ".config" / "project"
    root.mkdir(parents=True)
    (root / "a.md").write_text("fine")
    assert Toolbox(roots=[root]).read("a.md").endswith("fine")


def test_the_walk_is_bounded_however_large_the_tree(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools, "VISIT_CAP", 50)
    for d in range(20):
        sub = tmp_path / f"d{d:02}"
        sub.mkdir()
        for f in range(20):
            (sub / f"f{f:02}.md").write_text("x")
    assert len(list(Toolbox(roots=[tmp_path])._walk())) <= 50 + 20


def test_one_search_scans_a_bounded_amount_of_text(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools, "SCAN_CHARS_CAP", 1000)
    for i in range(10):
        (tmp_path / f"f{i}.md").write_text("needle " * 100)
    assert "[stopped after scanning" in Toolbox(roots=[tmp_path]).retrieve("needle")


def test_a_long_note_does_not_slow_the_material_estimate(tmp_path: Path):
    (tmp_path / "a.md").write_text("x" * 40)
    box = Toolbox(roots=[tmp_path])
    started = time.monotonic()
    assert box.material("zz", "a" * 1_000_000) is None
    assert time.monotonic() - started < 1
    assert box.material("zz", "read a.md") == {str((tmp_path / "a.md").resolve()): 10}
    assert box.material("zz", "x " * 1500 + "a.md") is None  # past NOTE_CAP


def test_attached_reads_keep_only_the_cap(tmp_path: Path):
    big = tmp_path / "big.log"
    big.write_text("y" * 50_000)
    m = new_run("reads-1", "g", "p", "d")
    store = MemoryStore(tmp_path / "s")
    attach_reads(store, m, [str(big)], cap=100)
    assert store.working_facts("reads-1")["reads"][0]["chars"] == 100


# --- saved runs ---


def test_a_saved_run_cannot_widen_a_slots_tools(tmp_path: Path):
    m = new_run("saved-1", "g", "p", "d")
    path = save_run(m, tmp_path / "r.json")
    raw = json.loads(path.read_text())
    for s in raw["state"]["slots"]:
        s["tools"] = ["read", "retrieve", "observe", "spawn"]
    path.write_text(json.dumps(raw))
    loaded = load_run(path)
    for slot in loaded.state.slots:
        assert set(slot.tools) <= set(tools_for(slot.skill))


def tools_for(skill):
    from taskorg.models import SKILL_TOOLS
    return SKILL_TOOLS[skill]


@pytest.mark.parametrize("text", ["{}", "[]", '{"state": 3}', "[" * 100_000, '{"id": "x", "state": {"lead_id": "l", "slots": [{"id": "s", "function": "boss"}]}}'])
def test_a_malformed_run_file_is_refused_cleanly(tmp_path: Path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(InvariantError) as e:
        load_run(path)
    assert e.value.code == "PERSIST"
