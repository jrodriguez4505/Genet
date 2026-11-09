"""The head-to-head's pieces (docs/HEAD_TO_HEAD.md): paged reads, per-question workspaces, the benchmark loaders,
text grading, the raw client's caps and tapes, and the judge. All offline: small files made here, fake clients."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskorg import benchmarks, compare
from taskorg.errors import InvariantError
from taskorg.judge import judge_rows
from taskorg.rawcall import ContextFull, RawClient, RawPlayer, RawTape, Spend, estimate_tokens, request_key
from taskorg.suite import Suite, Task, grade, normalize_text, text_f1
from taskorg.tools import READ_CAP, Toolbox, pages

from bench_fake import BenchFake


# --- paging ---

def _ws(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def test_pages_cut_at_a_line_break_in_the_last_fifth():
    text = "a" * 900 + "\n" + "b" * 500
    assert pages(text, 1000) == [(0, 901), (901, 1401)]


def test_pages_cut_at_the_size_when_no_break_is_near():
    text = "x" * 2500
    assert pages(text, 1000) == [(0, 1000), (1000, 2000), (2000, 2500)]


def test_a_paged_read_gives_page_one_then_any_page(tmp_path):
    root = _ws(tmp_path, {"long.txt": "line\n" * 2000})
    box = Toolbox(roots=[root], page_chars=2000)
    first = box.run("read:long.txt")
    assert first.startswith("[read long.txt page 1 of 5]") and first.endswith("read:long.txt@2 for the next]")
    last = box.run("read:long.txt@5")
    assert last.startswith("[read long.txt page 5 of 5]") and last.endswith("the last page]")
    assert "has 5 page(s)" in box.run("read:long.txt@9")


def test_a_paged_read_of_a_short_file_is_whole_and_counts_as_held(tmp_path):
    root = _ws(tmp_path, {"short.txt": "only this"})
    box, have = Toolbox(roots=[root], page_chars=2000), set()
    assert box.read("short.txt", have) == "[read short.txt]\nonly this"
    assert box.read("short.txt", have).endswith("already in full above")


def test_a_page_of_a_long_file_is_never_held(tmp_path):
    root = _ws(tmp_path, {"long.txt": "line\n" * 2000})
    box, have = Toolbox(roots=[root], page_chars=2000), set()
    box.read("long.txt", have)
    assert not have
    assert "page 1 of" in box.read("long.txt", have)


def test_a_file_named_with_an_at_sign_wins_over_a_page(tmp_path):
    root = _ws(tmp_path, {"q@2": "the file itself", "q": "line\n" * 2000})
    assert Toolbox(roots=[root], page_chars=2000).run("read:q@2") == "[read q@2]\nthe file itself"


def test_unpaged_reads_are_as_before(tmp_path):
    root = _ws(tmp_path, {"long.txt": "line\n" * 2000})
    box = Toolbox(roots=[root])
    assert box.run("read:long.txt").endswith(f"[truncated at {READ_CAP} of 10000 chars]")
    assert box.run("read:long.txt@2") == "[read long.txt@2] not found in the workspace"


@pytest.mark.parametrize("bad", [999, 64_001, 2.5, "4000"])
def test_a_page_size_out_of_range_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        Toolbox(roots=[tmp_path], page_chars=bad)


def test_a_scoped_toolbox_keeps_its_pages(tmp_path):
    root = _ws(tmp_path, {"long.txt": "line\n" * 2000})
    box = Toolbox(roots=[root], page_chars=2000)
    assert box.scoped([root / "long.txt"]).page_chars == 2000


def test_sizes_count_whole_files_only_when_paged(tmp_path):
    root = _ws(tmp_path, {"long.txt": "x" * 40_000})
    assert Toolbox(roots=[root]).file_sizes() == [READ_CAP // 4]
    assert Toolbox(roots=[root], page_chars=16_000).file_sizes() == [10_000]
    assert list(Toolbox(roots=[root], page_chars=16_000).material("long").values()) == [10_000]
    assert list(Toolbox(roots=[root]).material("long").values()) == [READ_CAP // 4]


# --- tasks with their own workspace and words ---

def test_text_grading_normalises_as_hotpotqa_does():
    task = Task(id="t", family="f", question="?", answer="The Beatles", kind="text")
    assert grade("beatles.", task) and grade("THE  BEATLES", task)
    assert not grade("The Rolling Stones", task)
    assert normalize_text("An Apple, the pie!") == "apple pie"
    assert text_f1("yes", "no") == 0.0 and text_f1("the red car", "red car") == 1.0
    assert 0 < text_f1("red car park", "red car") < 1


def test_a_judged_task_is_never_graded_right_here():
    assert not grade("anything", Task(id="t", family="f", question="?", answer="anything", kind="judge"))


def test_a_task_runs_in_its_own_workspace_with_its_own_words(tmp_path):
    suite = Suite(seed=0, companies={}, tasks=[
        Task(id="q1", family="f", question="What is in a?", answer="rehearsal", kind="text", workspace="q1",
             context="Own context. The files: a.txt.", purpose="Own purpose. End with ANSWER: <x>",
             done_when="Own done-when."),
    ], corpus={"q1/a.txt": "alpha\n", "q2/b.txt": "beta\n"})
    root = suite.write_corpus(tmp_path / "c")
    seen = []

    class Spy(BenchFake):
        def act(self, brief):
            seen.append(brief)
            return super().act(brief)

    r = compare.run_trial(suite.tasks[0], "single", Spy(), root, budget=compare.comparison_budget(20, 8000), page_chars=2000)
    assert r.answer == "rehearsal" and r.correct
    packets = " ".join(b.packet for b in seen)
    assert "Own context." in packets
    assert {b.purpose for b in seen} == {"Own purpose. End with ANSWER: <x>"} and {b.done_when for b in seen} == {"Own done-when."}
    assert "b.txt" not in packets  # the other question's files are not in this workspace
    assert compare.task_context(suite.tasks[0]) == "Own context. The files: a.txt."


def test_genet_stays_single_where_the_files_fit_and_splits_where_they_do_not(tmp_path):
    files = {f"q/{n}.txt": ("figure line\n" * 3000) for n in ("alpha", "beta", "gamma")}
    task = Task(id="q", family="f", question="Which is largest?", answer="rehearsal", kind="text", workspace="q",
                context="The files: alpha.txt, beta.txt, gamma.txt.", purpose="End with ANSWER: <x>", done_when="ANSWER")
    suite = Suite(seed=0, companies={}, tasks=[task], corpus=files)
    root = suite.write_corpus(tmp_path / "c")
    big = compare.run_trial(task, "genet", BenchFake(), root, budget=compare.comparison_budget(40, 40_000), page_chars=8000)
    roomy = compare.run_trial(task, "genet", BenchFake(), root, budget=compare.comparison_budget(40, 400_000), page_chars=8000)
    assert big.workers == 3 and big.refused == 0
    assert roomy.workers == 0 and roomy.refused == 3


# --- the benchmark files ---

def _loong_rows():
    rows = []
    for level, docs in ((1, ["Acme Corp"]), (2, ["Acme Corp", "Beta Inc"]), (3, ["Beta Inc", "Gamma LLC"]), (4, ["2023-form10-k"])):
        for n in range(12):
            rows.append({"id": f"{level}{n:02d}aaaa-x", "type": "financial", "language": "en", "set": 1 + n % 2,
                         "level": level, "doc": docs, "question": f"Q{level}-{n}?", "instruction": "Answer it.",
                         "answer": {"high": ["Acme Corp"]} if level == 3 else f"A{level}-{n}",
                         "prompt_template": "{docs}\n\n{instruction}\n\n{question}"})
    rows.append({"id": "zh000000", "type": "financial", "language": "zh", "set": 1, "level": 1, "doc": ["Acme Corp"],
                 "question": "?", "instruction": "", "answer": "", "prompt_template": ""})
    rows.append({"id": "set3aaaa", "type": "financial", "language": "en", "set": 3, "level": 1, "doc": ["Acme Corp"],
                 "question": "?", "instruction": "", "answer": "", "prompt_template": ""})
    rows.append({"id": "twofiling", "type": "financial", "language": "en", "set": 1, "level": 1, "doc": ["Twin Co"],
                 "question": "?", "instruction": "", "answer": "", "prompt_template": ""})
    return rows


@pytest.fixture
def loong_docs(tmp_path):
    d = tmp_path / "financial"
    d.mkdir()
    for name in ("2024-Acme Corp-j.txt", "2024-Beta Inc-j.txt", "2024-Gamma LLC-j.txt", "2023-form10-k.txt",
                 "2024-Twin Co-j.txt", "2024-Twin Co-n.txt"):
        (d / name).write_text(f"{name}\nfigures\n")
    return d


def test_the_loong_sample_is_fixed_by_its_seed_and_takes_the_planned_pool(loong_docs):
    rows = _loong_rows()
    one, two = benchmarks.loong_sample(rows, loong_docs), benchmarks.loong_sample(rows, loong_docs)
    assert one == two and len(one["main"]) == 40 and len(one["calibration"]) == 4
    assert not set(one["main"]) & set(one["calibration"])
    assert {"zh000000", "set3aaaa", "twofiling"}.isdisjoint(one["main"] + one["calibration"])
    assert benchmarks.loong_sample(rows, loong_docs, seed=7) != one


def test_a_level_too_small_for_the_plan_is_an_error(loong_docs):
    rows = [r for r in _loong_rows() if not (r["level"] == 4 and r["id"] > "405")]
    with pytest.raises(benchmarks.BenchmarkError, match="level 4"):
        benchmarks.loong_sample(rows, loong_docs)


def test_a_loong_question_gets_its_filings_by_name_and_says_so(loong_docs):
    row = next(r for r in _loong_rows() if r["level"] == 2)
    task, corpus = benchmarks.loong_task(row, loong_docs)
    assert sorted(corpus) == [f"{task.workspace}/acme-corp.txt", f"{task.workspace}/beta-inc.txt"]
    assert "The files: acme-corp.txt, beta-inc.txt." in task.context and "Answer it." in task.context
    assert task.kind == "judge" and task.family == "loong-comparison"
    clustered = benchmarks.loong_task(next(r for r in _loong_rows() if r["level"] == 3), loong_docs)[0]
    assert json.loads(clustered.answer) == {"high": ["Acme Corp"]}


def test_a_filing_name_that_finds_two_files_is_an_error(loong_docs):
    row = next(r for r in _loong_rows() if r["id"] == "twofiling")
    with pytest.raises(benchmarks.BenchmarkError, match="matches 2"):
        benchmarks.loong_files(row, loong_docs)


def test_a_hotpot_question_gets_one_file_a_paragraph(tmp_path):
    row = {"id": "5a8b57f25542995d1e6f1371", "type": "comparison", "question": "Who is older?", "answer": "Ann",
           "context": {"title": ["Ann Lee", "Bob", "Ann Lee"], "sentences": [["Ann was born.", " In 1900."], ["Bob."], ["Other."]]}}
    task, corpus = benchmarks.hotpot_task(row)
    assert corpus[f"{task.workspace}/ann-lee.txt"] == "Ann Lee\nAnn was born. In 1900.\n"
    assert f"{task.workspace}/ann-lee-2.txt" in corpus
    assert "The files: ann-lee.txt, bob.txt, ann-lee-2.txt." in task.context
    assert task.kind == "text" and task.family == "hotpot-comparison"


def test_the_judge_prompt_and_score_read_as_loong_reads_them():
    row = {"prompt_template": "{docs}\n\n{instruction}\n\n{question}", "question": "Q?", "instruction": "I."}
    assert benchmarks.loong_judge_question(row) == "\n\nI.\n\nQ?"
    prompt = benchmarks.judge_prompt("Q?", "gold", "mine")
    assert "[Question]\nQ?" in prompt and "[Gold Answer]\ngold" in prompt and "\nmine\n[The End of" in prompt
    assert benchmarks.judge_score("Evidence...\nRating: [[100]]") == 100.0
    assert benchmarks.judge_score("Rating: [85]") == 85.0
    assert benchmarks.judge_score("no rating") is None


def test_a_bad_jsonl_line_is_named(tmp_path):
    (tmp_path / "q.jsonl").write_text('{"a": 1}\nnot json\n')
    with pytest.raises(benchmarks.BenchmarkError, match="line 2"):
        benchmarks.read_jsonl(tmp_path / "q.jsonl")


# --- the raw client ---

class _SDK:
    """A fake Anthropic client: replies with text, or raises what it is given."""

    def __init__(self, text="ok", raise_=None, stop="end_turn"):
        self.text, self.raise_, self.stop, self.sent = text, raise_, stop, []
        self.messages = self

    def create(self, **params):
        from anthropic.types import Message, TextBlock, Usage

        self.sent.append(params)
        if self.raise_:
            raise self.raise_
        return Message(id="m", type="message", role="assistant", model=params["model"], stop_reason=self.stop,
                       stop_sequence=None, content=[TextBlock(type="text", text=self.text)],
                       usage=Usage(input_tokens=1000, output_tokens=100))


def _params(text="hello", **more):
    return {"model": "claude-haiku-5-5", "max_tokens": 64_000, "messages": [{"role": "user", "content": text}]} | more


def test_a_request_is_sent_as_genet_sends_its_own():
    sdk = _SDK()
    RawClient(call_limit=20_000, sdk_client=sdk).messages.create(**_params(temperature=0.2, top_p=0.9, stream=False))
    sent = sdk.sent[0]
    assert "temperature" not in sent and "top_p" not in sent and "stream" not in sent
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] == min(20_000 - estimate_tokens(sent), 16_000)


def test_a_request_past_the_call_limit_is_refused_in_words_crewai_reads_as_a_full_context():
    sdk = _SDK()
    with pytest.raises(ContextFull) as e:
        RawClient(call_limit=3_000, sdk_client=sdk).messages.create(**_params("x" * 8_000))
    assert "maximum context length" in str(e.value) and e.value.code == "BUDGET" and not sdk.sent


def test_a_trial_stops_at_its_calls_and_spend_stops_every_trial():
    sdk = _SDK()
    client = RawClient(call_limit=20_000, sdk_client=sdk, spend=Spend(default=(1.0, 1.0)), max_spend=0.0021)
    client.begin_trial(max_calls=2, max_tokens=10**9, max_seconds=60)
    client.messages.create(**_params())
    client.messages.create(**_params())
    with pytest.raises(InvariantError, match="2 calls are used"):
        client.messages.create(**_params())
    stats = client.end_trial()
    assert len(stats["calls"]) == 2 and stats["calls"][0]["prompt_tokens"] == 1000
    with pytest.raises(InvariantError, match="spend cap"):
        client.messages.create(**_params())  # 2 calls of 1,100 tokens at $1 a million: $0.0022 of $0.0021
    assert len(sdk.sent) == 2


def test_an_sdk_error_and_a_refusal_are_live_failures_and_on_the_tape(tmp_path):
    tape = RawTape(tmp_path / "t.jsonl", {"adapter": "anthropic-raw"})
    with pytest.raises(InvariantError, match="LIVE"):
        RawClient(call_limit=20_000, sdk_client=_SDK(raise_=RuntimeError("boom")), tape=tape).messages.create(**_params())
    with pytest.raises(InvariantError, match="declined"):
        RawClient(call_limit=20_000, sdk_client=_SDK(stop="refusal"), tape=tape).messages.create(**_params())
    tape.close()
    lines = [json.loads(x) for x in (tmp_path / "t.jsonl").read_text().splitlines()]
    assert lines[0]["raw_tape"] == 1 and [e["error"]["code"] for e in lines[1:]] == ["LIVE", "LIVE"]


def test_a_tape_replays_the_same_message_and_counts_a_miss(tmp_path):
    tape = RawTape(tmp_path / "t.jsonl", {"adapter": "anthropic-raw"})
    live = RawClient(call_limit=20_000, sdk_client=_SDK(text="first"), tape=tape)
    sent = live.messages.create(**_params())
    tape.close()
    player = RawPlayer(tmp_path / "t.jsonl")
    again = RawClient(call_limit=20_000, player=player).messages.create(**_params())
    assert again.content[0].text == sent.content[0].text == "first"
    with pytest.raises(InvariantError, match="no reply"):
        RawClient(call_limit=20_000, player=player).messages.create(**_params("something else"))
    assert player.misses == 1 and player.served == 1


def test_a_tape_is_never_written_over(tmp_path):
    RawTape(tmp_path / "t.jsonl", {}).close()
    with pytest.raises(InvariantError, match="already exists"):
        RawTape(tmp_path / "t.jsonl", {})


def test_the_reply_cap_is_not_part_of_the_request_key():
    assert request_key(_params(max_tokens=1)) == request_key(_params(max_tokens=2))
    assert request_key(_params("a")) != request_key(_params("b"))


def test_a_client_needs_an_sdk_or_a_tape_not_both(tmp_path):
    with pytest.raises(ValueError):
        RawClient(call_limit=1000)


def test_token_counts_are_local():
    sdk = _SDK()
    n = RawClient(call_limit=20_000, sdk_client=sdk).beta.messages.count_tokens(**_params())
    assert n.input_tokens == estimate_tokens(_params()) and not sdk.sent


# --- the judge ---

def test_the_judge_scores_each_answer_once_blind_to_who_gave_it():
    loong = [{"id": "abcdef12-0", "prompt_template": "{docs}{instruction} {question}", "question": "Q?",
              "instruction": "I.", "answer": "gold"}]
    sdk = _SDK(text="Fine.\nRating: [[100]]")
    results = [
        {"task_id": "loong-abcdef12", "strategy": "genet", "answer": "gold", "expected": "gold", "status": "complete"},
        {"task_id": "loong-abcdef12", "strategy": "crewai", "answer": "gold", "expected": "gold", "status": "abort"},
        {"task_id": "loong-abcdef12", "strategy": "single", "answer": None, "expected": "gold", "status": "abort"},
        {"task_id": "hotpot-1", "strategy": "single", "answer": "x", "status": "complete"},
    ]
    out = judge_rows(results, loong, RawClient(call_limit=16_000, sdk_client=sdk, effort=None), "claude-sonnet-5-5")
    assert len(sdk.sent) == 1 and "genet" not in json.dumps(sdk.sent) and "crewai" not in json.dumps(sdk.sent)
    assert [r.get("judge_score") for r in out] == [100.0, 100.0, 0.0, None]
    assert [r.get("correct") for r in out[:3]] == [True, False, False]
    assert out[1]["answer_right"] and "judge_score" not in out[3]


# --- the command line ---

def _hotpot_file(tmp_path):
    rows = [{"id": f"5a{n}000000", "type": t, "question": f"Q{n}?", "answer": "rehearsal",
             "context": {"title": [f"T{n}a", f"T{n}b"], "sentences": [["One."], ["Two."]]}}
            for n, t in enumerate(("bridge", "comparison"))]
    path = tmp_path / "hotpot.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_compare_runs_a_benchmark_and_says_so_in_its_config(tmp_path, capsys):
    from taskorg.cli import main

    out = tmp_path / "r.json"
    assert main(["compare", "--adapter", "stub", "--benchmark", "hotpot", "--questions", str(_hotpot_file(tmp_path)),
                 "--strategies", "single", "--page-chars", "4000", "--max-seconds", "60", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["config"]["benchmark"] == "hotpot" and data["config"]["page_chars"] == 4000
    assert data["config"]["task_ids"] == ["hotpot-5a000000", "hotpot-5a100000"] and data["config"]["families"] is None
    assert len(data["results"]) == 2


def test_a_generated_suite_run_names_no_benchmark_keys(tmp_path, capsys):
    from taskorg.cli import main

    assert main(["compare", "--adapter", "stub", "--dry-run", "--per-family", "1"]) == 0
    config = json.loads(capsys.readouterr().out)
    assert not {"benchmark", "page_chars", "max_seconds", "task_ids"} & set(config)


@pytest.mark.parametrize("argv, words", [
    (["--benchmark", "loong", "--questions", "q.jsonl"], "needs --docs"),
    (["--benchmark", "hotpot"], "needs --questions"),
    (["--page-chars", "70000"], "at most 64,000"),
])
def test_compare_refuses_a_benchmark_it_cannot_load(argv, words, capsys):
    from taskorg.cli import main

    assert main(["compare", "--adapter", "stub", "--dry-run", *argv]) != 0
    assert words in capsys.readouterr().out  # the CLI reports a halt as JSON on stdout


def test_the_judge_command_scores_from_a_tape_with_no_key(tmp_path, capsys, monkeypatch):
    from taskorg.cli import main

    monkeypatch.delenv("TASKORG_ANTHROPIC_KEY", raising=False)
    loong = tmp_path / "loong.jsonl"
    loong.write_text(json.dumps({"id": "abcdef12-0", "prompt_template": "{docs}{instruction} {question}",
                                 "question": "Q?", "instruction": "I.", "answer": "gold"}) + "\n")
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"results": [{"task_id": "loong-abcdef12", "strategy": "genet", "answer": "gold",
                                                "expected": "gold", "status": "complete"}]}))
    tape = RawTape(tmp_path / "judge.jsonl", {"adapter": "anthropic-raw"})
    RawClient(call_limit=16_000, sdk_client=_SDK(text="Rating: [[100]]"), tape=tape, effort=None).messages.create(
        model="claude-sonnet-5-5", max_tokens=1024,
        messages=[{"role": "user", "content": benchmarks.judge_prompt("I. Q?", "gold", "gold")}])
    tape.close()
    out = tmp_path / "judged.json"
    assert main(["h2h-judge", "--results", str(results), "--questions", str(loong), "--replay", str(tmp_path / "judge.jsonl"),
                 "--out", str(out)]) == 0
    row = json.loads(out.read_text())["results"][0]
    assert row["judge_score"] == 100.0 and row["correct"]
    assert "| genet | 1 | 1 | 1 | 100.0 |" in capsys.readouterr().out
