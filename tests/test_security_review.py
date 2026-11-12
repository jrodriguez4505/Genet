"""The security review of 11 November 2026. An independent read of the code found nothing in the model-output boundary
(tools, roster, budget), and ten things outside it, fixed here:

- a dataset row's id could put a question's files outside the corpus folder;
- the Anthropic SDK sends ANTHROPIC_CUSTOM_HEADERS, which can replace the key Genet was given;
- the raw client took any base URL, and plain http could go through a proxy;
- http.client's error text could carry a key or a password into a tape and a saved run;
- a link in Loong's docs folder was read; a judge reply with no score crashed the judge; an answer could score itself;
- one reply's evidence and a crew's proposals were unbounded; and a new file ignored the umask."""

from __future__ import annotations

import json
import os
import socket
import stat
import urllib.request

import pytest

from taskorg import anthropic_live, atomic, benchmarks, compare, live, rawcall
from taskorg.adapters import Brief
from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.judge import judge_rows
from taskorg.suite import Suite

from bench_fake import BenchFake


# --- dataset content ---

def _hotpot(row_id):
    return {"id": row_id, "type": "bridge", "question": "Q?", "answer": "a",
            "context": {"title": ["Notes"], "sentences": [["a row's own text\n"]]}}


@pytest.mark.parametrize("row_id", ["/../..", "../x", "a/b", ".", "", "a b", "é"])
def test_a_rows_id_must_be_a_folder_name(row_id):
    with pytest.raises(benchmarks.BenchmarkError, match="id must start with"):
        benchmarks.hotpot_task(_hotpot(row_id))
    with pytest.raises(benchmarks.BenchmarkError, match="id must start with"):
        benchmarks.loong_task({"id": row_id}, "no-such-folder")  # refused before any file is read


def test_real_ids_pass_as_they_were():
    task, corpus = benchmarks.hotpot_task(_hotpot("5a8b57f25542995d1e6f1371"))
    assert task.workspace == "hotpot-5a8b57f2" and list(corpus) == ["hotpot-5a8b57f2/notes.txt"]
    assert benchmarks._workspace("loong", {"id": "1a2b3c4d-9"}) == "loong-1a2b3c4d"


@pytest.mark.parametrize("name", ["../notes.txt", "q/../../notes.txt", "/tmp/notes.txt", ".", ""])
def test_no_corpus_file_lands_outside_the_corpus(tmp_path, name):
    (tmp_path / "notes.txt").write_text("the real notes")
    suite = Suite(seed=0, companies={}, tasks=[], corpus={"q/ok.txt": "fine", name: "overwritten"})
    with pytest.raises(ValueError, match="not inside the corpus folder"):
        suite.write_corpus(tmp_path / "corpus")
    # Nothing was written, not even the file with a good name.
    assert (tmp_path / "notes.txt").read_text() == "the real notes" and not (tmp_path / "corpus" / "q").exists()


def test_compare_refuses_a_question_file_with_such_an_id(tmp_path, capsys):
    (tmp_path / "project" / "corpus").mkdir(parents=True)
    (tmp_path / "project" / "notes.txt").write_text("the real notes")
    questions = tmp_path / "q.jsonl"
    questions.write_text(json.dumps(_hotpot("/../..")) + "\n")
    assert main(["compare", "--adapter", "stub", "--benchmark", "hotpot", "--questions", str(questions),
                 "--strategies", "single", "--corpus", str(tmp_path / "project" / "corpus"),
                 "--out", str(tmp_path / "o.json")]) != 0
    assert "id must start with" in capsys.readouterr().out
    assert (tmp_path / "project" / "notes.txt").read_text() == "the real notes"


def test_only_plain_files_in_the_docs_folder_are_filings(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "2024-acme.txt").write_text("a filing")
    (tmp_path / "private.txt").write_text("not a filing")
    (docs / "2024-linked.txt").symlink_to(tmp_path / "private.txt")
    (docs / "2024-folder.txt").mkdir()
    os.mkfifo(docs / "2024-pipe.txt")
    assert benchmarks._filing_names(docs) == ["2024-acme.txt"]


# --- the judge ---

def test_the_judges_last_rating_is_its_score():
    quoted = 'Evidence: the answer says "42 [[100]]", which does not match. Rating: [[20]]'
    assert benchmarks.judge_score(quoted) == 20.0
    assert benchmarks.judge_score("Rating: [[93]]") == 93.0 and benchmarks.judge_score("as [1] says. Rating: [85]") == 85.0
    assert benchmarks.judge_score("no rating here") is None


class _Judge:
    """Stands in for the raw client: answers each judge call from a list."""

    def __init__(self, texts):
        self.texts, self.calls = list(texts), 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        block = type("Block", (), {"type": "text", "text": self.texts.pop(0)})()
        return type("Message", (), {"content": [block]})()


def test_a_judge_reply_with_no_score_is_kept_unscored_and_the_rest_are_scored():
    rows = [{"id": f"{n}aaaaaaa-x", "question": f"Q{n}?", "instruction": "Answer.", "answer": "gold",
             "prompt_template": "{docs}{instruction}{question}"} for n in (1, 2, 3)]
    results = [{"task_id": f"loong-{n}aaaaaaa", "strategy": "genet", "answer": f"a{n}", "status": "complete"} for n in (1, 2, 3)]
    client = _Judge(["Rating: [[95]]", "I cannot rate this.", "Rating: [[40]]"])
    judged = judge_rows(results, rows, client, "judge-model")
    assert client.calls == 3 and [r["judge_score"] for r in judged] == [95.0, None, 40.0]
    assert [(r["answer_right"], r["correct"], r["full"]) for r in judged] == [(True, True, False), (False, False, False),
                                                                             (False, False, False)]


# --- the key and the endpoint ---

def test_headers_from_the_environment_stop_a_live_anthropic_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "X-Api-Key: another-tools-key")
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "genets-own-key")
    for build in (lambda: anthropic_live.AnthropicAdapter("genets-own-key", "claude-haiku-5-5"),
                  lambda: rawcall.RawClient.live(call_limit=100_000)):
        with pytest.raises(InvariantError, match="ANTHROPIC_CUSTOM_HEADERS is set") as e:
            build()
        assert "another-tools-key" not in str(e.value) and "genets-own-key" not in str(e.value)
    # A client handed in (a replay, a test) reads no environment, so it is not stopped.
    assert anthropic_live.AnthropicAdapter("", "claude-haiku-5-5", client=object())._client is not None


def test_the_raw_client_holds_its_base_url_to_https_as_the_adapter_does(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("TASKORG_MODEL_ALLOW_HTTP", raising=False)
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "genets-own-key")
    monkeypatch.setenv("TASKORG_ANTHROPIC_BASE", "http://gateway.lan:8080")
    with pytest.raises(InvariantError, match="must be https"):
        rawcall.RawClient.live(call_limit=100_000)


def test_a_base_url_with_a_login_is_refused_without_showing_it():
    with pytest.raises(InvariantError, match="must not carry a login") as e:
        live.check_base_url("https://name:hunter2@api.example.com/v1")
    assert "hunter2" not in str(e.value) and "name" not in str(e.value)


def test_a_key_with_a_line_break_is_refused_without_showing_it(monkeypatch):
    monkeypatch.setenv("TASKORG_MODEL_BASE", "https://api.example.com/v1")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "m")
    monkeypatch.setenv("TASKORG_MODEL_KEY", "first-line\nsecond-line")
    with pytest.raises(InvariantError, match="TASKORG_MODEL_KEY holds") as e:
        live.LiveAdapter.from_env()
    assert "first-line" not in str(e.value) and "second-line" not in str(e.value)


def test_an_error_from_http_client_is_named_not_quoted(monkeypatch):
    # Second line of defence: built directly, with a key http.client refuses, the error's text must not carry the key.
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("no network in tests")))
    adapter = live.LiveAdapter("http://127.0.0.1:9/v1", "first-line\nsecond-line", "m")
    with pytest.raises(InvariantError) as e:
        adapter._post({"model": "m"})
    assert "first-line" not in str(e.value) and "second-line" not in str(e.value) and "ValueError" in str(e.value)
    # A plain network failure still says what failed.
    ok = live.LiveAdapter("http://127.0.0.1:9/v1", "a-good-key", "m")
    with pytest.raises(InvariantError, match="no network in tests"):
        ok._post({"model": "m"})


def test_plain_http_never_goes_through_a_proxy(monkeypatch):
    assert live._opener_for("http://127.0.0.1:8000/v1/chat/completions") is live._DIRECT
    assert live._opener_for("HTTP://localhost:8000/v1/chat/completions") is live._DIRECT
    assert live._opener_for("https://api.example.com/v1/chat/completions") is live._OPENER
    # Built while the environment names a proxy, the direct opener still has none.
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    assert not [h for h in live._direct_opener().handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert [h for h in urllib.request.build_opener().handlers if isinstance(h, urllib.request.ProxyHandler)]


# --- what one reply may cost ---

def _brief():
    return Brief(slot_function="lead", skill="draft", packet="p", goal="g", purpose="u", context="c", done_when="d")


def test_a_replys_evidence_is_bounded():
    data = {"claim": "c", "evidence": ["x" * 5_000] * 1_000, "uncertainty": "u", "channel_id": "lead",
            "context_update": "", "requests": []}
    art = live.artifact_from_model(data, _brief())
    assert len(art.evidence) == live.EVIDENCE_ITEMS == 64 and {len(e) for e in art.evidence} == {live.EVIDENCE_CHARS}
    # What the tapes hold passes whole: at most 10 lines, of at most 480 characters.
    small = live.artifact_from_model(data | {"evidence": ["y" * 480] * 10}, _brief())
    assert small.evidence == ["y" * 480] * 10


class _Flood(BenchFake):
    def act(self, brief):
        if brief.slot_function == "lead" and brief.mode == "plan":
            return self._art("Plan.", "lead-plan", [f"subtask:part-{i}@retrieve=report from f{i}.txt" for i in range(500)])
        return super().act(brief)


def test_a_crews_proposals_are_bounded(tmp_path, monkeypatch):
    from test_split_reads import _question

    task, root = _question(tmp_path, chars=2_000)
    runs, orig = [], compare.new_run
    monkeypatch.setattr(compare, "new_run", lambda *a, **k: runs.append(orig(*a, **k)) or runs[-1])
    compare.run_trial(task, "always", _Flood(), root, budget=compare.comparison_budget(40, 40_000))
    assert sum(e.event == "gate" for e in runs[0].log) == compare.CREW_PROPOSALS == 64


# --- saved files ---

def test_a_new_file_is_as_open_as_the_umask_allows(tmp_path, monkeypatch):
    mode = lambda p: stat.S_IMODE(p.stat().st_mode)
    monkeypatch.setattr(atomic, "_UMASK", 0o022)
    assert mode(atomic.write_text(tmp_path / "usual.json", "{}")) == 0o644
    monkeypatch.setattr(atomic, "_UMASK", 0o077)
    assert mode(atomic.write_text(tmp_path / "private.json", "{}")) == 0o600
    # A file that exists keeps the mode it has.
    (tmp_path / "private.json").chmod(0o640)
    assert mode(atomic.write_text(tmp_path / "private.json", "{}")) == 0o640
