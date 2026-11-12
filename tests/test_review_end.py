"""The verifier's view marks where the product's text ends (11 November 2026). After the product the kernel puts the
evidence it gave, its quote check and the sources, and a verifier read them as the product's own: of the 28 failures on
the Loong tapes that said the ANSWER line was not last, 26 were of products whose own text ends with it
(docs/LIVE_TESTS.md). Every run names the view; a tape from before names nothing, and replays under the view as it was.
compare --marked-review --then-live measures the mark on such a tape from each trial's first verifier call."""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from taskorg import cli, compare, merge_bench, verify_bench
from taskorg.budget import Budget
from taskorg.cli import _as_recorded, main
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import QUOTE_ARM, REVIEW_ARM, REVIEW_END, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.tools import Toolbox

CLAIM = "Basic EPS was $0.19 for the quarter.\nANSWER: $0.19"


def _product(*evidence):
    return Artifact(claim=CLAIM, evidence=list(evidence), uncertainty="none", channel_id="lead-merge", context_update="")


def _brief(tmp_path, product, **engine):
    (tmp_path / "dawson.txt").write_text("Basic income per share $ 0.19\n")
    e = Engine(MemoryStore(tmp_path / "s"), toolbox=Toolbox(roots=[tmp_path]), budget=Budget(max_tokens_per_call=100_000),
               **engine)
    run = new_run("r", goal="What was Dawson's basic EPS? dawson.txt", purpose="p", done_when="End with ANSWER: <x>")
    return e._verifier_brief(run, product).packet


def test_the_verifier_sees_where_the_products_text_ends(tmp_path):
    assert Engine(MemoryStore(tmp_path / "e")).review_end is True
    with_evidence = _brief(tmp_path, _product('dawson.txt:1: "Basic income per share $ 0.19"'))
    assert f"{CLAIM}\n{REVIEW_END}\nEVIDENCE GIVEN WITH IT\n- dawson.txt:1:" in with_evidence
    assert REVIEW_ARM in with_evidence  # what a replay of a tape from before goes live on
    # With no evidence the kernel's sections still follow the product, so the end is marked there too.
    assert f"{CLAIM}\n{REVIEW_END}\n" in _brief(tmp_path, _product())
    # The view as it was: the claim, then the evidence, with nothing between.
    old = _brief(tmp_path, _product('dawson.txt:1: "Basic income per share $ 0.19"'), review_end=False)
    assert REVIEW_END not in old and f"{CLAIM}\nEVIDENCE GIVEN WITH IT\n" in old


def test_the_merge_bench_reads_the_product_up_to_the_mark(tmp_path):
    for end in (True, False):
        packet = _brief(tmp_path, _product('dawson.txt:1: "Basic income per share $ 0.19"'), review_end=end)
        assert merge_bench._PRODUCT.search(packet).group(1) == CLAIM


def test_every_run_names_the_view_and_hands_it_to_every_trial(tmp_path, monkeypatch, capsys):
    seen = []
    trial = compare.run_trial

    def spy(*a, **k):
        seen.append((k.get("verify") or {}).get("review_end"))
        return trial(*a, **k)

    monkeypatch.setattr(compare, "run_trial", spy)
    out = tmp_path / "r.json"
    assert main(["compare", "--adapter", "stub", "--per-family", "1", "--families", "lookup", "--strategies", "single,genet",
                 "--out", str(out)]) == 0
    assert json.loads(out.read_text())["config"]["review_end"] is True and seen and set(seen) == {True}
    capsys.readouterr()
    assert main(["verify-bench", "--dry-run", "--questions", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["review_end"] is True


def test_the_verify_bench_hands_its_view_to_each_review(monkeypatch):
    seen = []
    monkeypatch.setattr(verify_bench, "review_trial", lambda *a, **k: seen.append(k["review_end"]) or None)
    one = (SimpleNamespace(id="aggregate-1"), 0, SimpleNamespace(kind="clean"))
    monkeypatch.setattr(verify_bench, "products", lambda suite, arms: [one])
    monkeypatch.setattr(verify_bench, "corpus_for", lambda built, root, where: root)

    class Suite:
        def write_corpus(self, path):
            return path

    for end in (True, False):
        verify_bench.run_bench(Suite(), lambda: None, setups=("independent-layered",), budget_factory=Budget,
                               review_end=end)
    assert seen == [True, False]


def test_a_tape_from_before_replays_under_the_view_as_it_was(capsys):
    config = {"review_end": True}
    _as_recorded({"strategies": ["single"]}, config)
    assert config["review_end"] is False and "verifier saw no mark where the product's text ends" in capsys.readouterr().err
    config = {"review_end": True}
    _as_recorded({"strategies": ["single"], "review_end": True}, config)
    assert config == {"review_end": True}


def _goes_live(tmp_path, monkeypatch, recorded, config):
    from test_rework_reads import _Haiku

    tape = tmp_path / "t.jsonl"
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "claude-haiku-5-5", "effort": "low",
                                "compare": recorded}) + "\n")
    monkeypatch.setattr(cli, "pick_adapter", lambda name: _Haiku())
    args = argparse.Namespace(replay=str(tape), record=str(tmp_path / "l.jsonl"), adapter="anthropic", gap_check=False,
                              rework_reads=False, rework_keeps=False, fixed_quotes=False, marked_review=True)
    factory, _, recorder = cli._continuing_source(args, config, "compare", "COMPARE")
    recorder.close()
    return factory, json.loads((tmp_path / "l.jsonl").read_text().splitlines()[0])["compare"]


def test_the_mark_is_measured_from_each_trials_first_verifier_call(tmp_path, monkeypatch, capsys):
    config = {"review_end": True}
    factory, header = _goes_live(tmp_path, monkeypatch, {"strategies": ["genet-reads"]}, config)
    assert factory().tape.arm == REVIEW_ARM != QUOTE_ARM
    assert config["review_end"] is True and header["review_end"] is True
    assert "goes on live under the verifier's view with the product's end marked" in capsys.readouterr().err
    with pytest.raises(InvariantError, match="not one"):
        _goes_live(tmp_path, monkeypatch, {"review_end": True}, {"review_end": True})
    assert main(["compare", "--dry-run", "--marked-review", "--per-family", "1"]) != 0
    assert "each needs --then-live" in capsys.readouterr().out


def test_a_verify_bench_review_takes_its_view(tmp_path):
    from test_verify_checks import Capture, _suite

    from taskorg.compare import comparison_budget

    suite = _suite(1)
    root = suite.write_corpus(tmp_path / "c")
    task, variant, built = verify_bench.products(suite)[0]
    for end in (True, False):
        cap = Capture()
        verify_bench.review_trial(task, built, verify_bench.DEFAULT_SETUPS[0], cap, root,
                                  budget=comparison_budget(4, 200_000), variant=variant, review_end=end)
        packet = next(b.packet for b in cap.briefs if b.slot_function == "verifier")
        assert (REVIEW_END in packet) is end


def test_the_verify_bench_command_hands_its_view_on(tmp_path, monkeypatch, capsys):
    seen = []
    bench = verify_bench.run_bench

    def spy(*a, **k):
        seen.append(k["review_end"])
        return bench(*a, **k)

    monkeypatch.setattr(verify_bench, "run_bench", spy)
    assert main(["verify-bench", "--adapter", "stub", "--questions", "1", "--out", str(tmp_path / "v.json")]) == 0
    assert seen == [True] and json.loads((tmp_path / "v.json").read_text())["config"]["review_end"] is True
