"""The real LiveAdapter against a fake OpenAI-compatible endpoint on localhost."""

import json
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.live import LiveAdapter
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


class FakeModel(BaseHTTPRequestHandler):
    """Answers like a compliant model. Records every request it sees."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen.append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "model": body["model"],
            "system": body["messages"][0]["content"],
            "user": json.loads(body["messages"][1]["content"]),
        })
        if self.server.mode == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom: upstream exploded")
            return
        if self.server.mode == "slow":
            time.sleep(2)
        if self.server.mode == "null":
            payload = json.dumps({"choices": [{"message": {"content": None}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        user = json.loads(body["messages"][1]["content"])
        fn, mode = user["function"], user["mode"]
        requests = []
        if fn == "lead" and mode == "plan":
            requests = [t for t in user["context"].split() if t.startswith("subtask:")]
            claim = "Read: two independent notes." if requests else "Read: a single agent is enough."
        elif fn == "lead":
            claim = "Product covering " + "; ".join(user["success_criteria"])
        elif fn == "verifier":
            claim = "PASS"
        else:
            claim = f"[{user['channel_id']}] sub-agent result"
        art = {"claim": claim, "evidence": [], "uncertainty": "fake", "channel_id": "anything",
               "context_update": f"after {fn} {user['channel_id']}", "requests": requests}
        payload = json.dumps({
            "choices": [{"message": {"content": "```json\n" + json.dumps(art) + "\n```"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class QuickServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind does a reverse-DNS lookup that can stall for seconds.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


@pytest.fixture
def fake_model():
    server = QuickServer(("127.0.0.1", 0), FakeModel)
    server.seen, server.mode = [], "ok"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _adapter(server, timeout=5, **kw):
    return LiveAdapter(f"http://127.0.0.1:{server.server_port}/v1", "test-key", "base-model", timeout=timeout, **kw)


def test_run_over_http_splits_and_merges(fake_model, tmp_path: Path):
    m = new_run("http-1", "Answer two notes", "Do not mix", "Integrated")
    adapter = _adapter(fake_model, models={"reason": "lead-model"})
    result = Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget.for_tier("open")).run_task(
        m, context="subtask:note-a=must_not_mix subtask:note-b=must_not_mix")
    assert result.split is True
    assert m.status.value == "complete"
    assert all(not c["tokens_estimated"] for c in m.calls)
    assert sum(c["prompt_tokens"] for c in m.calls) == 100 * len(m.calls)
    assert {s["path"] for s in fake_model.seen} == {"/v1/chat/completions"}
    assert {s["auth"] for s in fake_model.seen} == {"Bearer test-key"}
    plan = next(s for s in fake_model.seen if s["user"]["mode"] == "plan")
    assert plan["model"] == "lead-model" and "lead agent of a small team" in plan["system"]
    workers = [s for s in fake_model.seen if s["user"]["function"] == "worker"]
    assert {w["user"]["channel_id"] for w in workers} == {"note-a", "note-b"}
    for w in workers:
        sibling = "note-b" if w["user"]["channel_id"] == "note-a" else "note-a"
        assert f"after worker {sibling}" not in w["user"]["context"] + w["user"]["packet"]
    assert diagnose(m)["health"] == "ok"


def test_http_error_is_live_with_detail(fake_model, tmp_path: Path):
    fake_model.mode = "error"
    m = new_run("http-2", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=_adapter(fake_model)).run_task(m, context="one")
    assert e.value.code == "LIVE"
    assert "500" in e.value.message and "boom" in e.value.message
    assert m.status.value == "abort"


def test_timeout_is_live(fake_model, tmp_path: Path):
    fake_model.mode = "slow"
    m = new_run("http-3", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=_adapter(fake_model, timeout=1)).run_task(m, context="one")
    assert e.value.code == "LIVE"
    assert m.status.value == "abort"


def test_null_content_is_live(fake_model, tmp_path: Path):
    fake_model.mode = "null"
    m = new_run("http-4", "E", "P", "S")
    with pytest.raises(InvariantError) as e:
        Engine(MemoryStore(tmp_path), adapter=_adapter(fake_model)).run_task(m, context="one")
    assert e.value.code == "LIVE"
