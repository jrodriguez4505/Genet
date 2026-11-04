"""The merge bench: the verifier's requests from a tape, reviewed again under each rule.

What it takes from a tape, and how it counts, can be checked with a tape written here and a stand-in verifier.
What a real verifier does with each rule is for a live run.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from taskorg import checks, merge_bench as mb
from taskorg.adapters import ModelAdapter
from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.models import Artifact
from taskorg.suite import build_suite

SETTINGS = {"seed": 7, "per_family": 1, "families": ["aggregate", "breadth"], "entities": 10, "distractors": 6, "filed": 0,
            "context_tokens": 8_000, "verify_view": "independent"}


def _sent(function, mode, goal, packet="p"):
    return {"function": function, "skill": "reason", "channel_id": "", "goal": goal, "purpose": "u", "context": "c",
            "done_when": "d", "isolated": True, "tools": [], "success_criteria": ["ANSWER:"], "mode": mode, "packet": packet}


def _row(sent, reply="{}", error=None):
    return {"key": "k", "request": {"model": "m", "max_tokens": 4_000, "messages": [{"role": "user", "content": json.dumps(sent)}]},
            "reply": reply, "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "error": error, "latency_s": 1.0}


def _packet(product, evidence="- group-a: \"something\""):
    return (f"PRODUCT UNDER REVIEW (the lead's current product)\n{product}\nEVIDENCE GIVEN WITH IT\n{evidence}\n"
            f"VERIFIER RULE: claim MUST start.\n{checks.SOURCES_HEAD}\n(picked: x)\n[read a.md]\ntext\n{checks.SOURCE_RULE}")


def _verdict(word):
    return json.dumps({"claim": f"{word}. Because.", "evidence": [], "uncertainty": "", "channel_id": "", "context_update": "", "requests": []})


def _tape(tmp_path: Path, settings=None, name="t.jsonl"):
    """A tape of three trials: a split that passes a right answer and fails a wrong one, a lead who worked alone, and
    a split that fails a right answer it doubts."""
    suite = build_suite(seed=7, per_family=1, families=("aggregate", "breadth"), entities=10, distractors=6)
    a, b = suite.tasks[0], suite.tasks[1]
    rows = [
        _row(_sent("lead", "plan", a.question)),
        _row(_sent("worker", "work", a.question)),
        _row(_sent("lead", "integrate", a.question)),
        _row(_sent("verifier", "verify", a.question, _packet(f"The total. ANSWER: {a.answer}")), _verdict("PASS")),
        _row(_sent("verifier", "verify", a.question, _packet("Another total. ANSWER: 1.0")), _verdict("FAIL")),
        # Worked alone on the same goal: not a merge, though sub-agents came before it on the tape.
        _row(_sent("lead", "work", a.question)),
        _row(_sent("verifier", "verify", a.question, _packet(f"Alone. ANSWER: {a.answer}")), _verdict("PASS")),
        _row(_sent("lead", "plan", b.question)),
        _row(_sent("worker", "work", b.question)),
        _row(_sent("verifier", "verify", b.question, _packet(f"Figures are unconfirmed. ANSWER: {b.answer}")), _verdict("FAIL")),
        # No sources were opened, and a reply it cannot read.
        _row(_sent("verifier", "verify", b.question, f"PRODUCT UNDER REVIEW (x)\nNo sources. ANSWER: {b.answer}\nVERIFIER RULE"), _verdict("PASS")),
        _row(_sent("verifier", "verify", b.question, _packet(f"Cut off. ANSWER: {b.answer}")), "{\"claim\": \"PA"),
        _row(_sent("verifier", "verify", b.question, _packet(f"Failed call. ANSWER: {b.answer}")), None, error="boom"),
    ]
    path = tmp_path / name
    head = {"tape": 1, "adapter": "anthropic", "model": "m", "models": {}, "compare": settings or SETTINGS}
    path.write_text("\n".join(json.dumps(r) for r in [head, *rows]) + "\n")
    return path, a, b


class Says(ModelAdapter):
    name = "says"

    def __init__(self, word=lambda brief: "PASS", usage=(100, 50)):
        self.word, self.briefs = word, []
        self.last_usage = {"prompt_tokens": usage[0], "completion_tokens": usage[1]}

    def act(self, brief):
        self.briefs.append(brief)
        word = self.word(brief)
        if word == "BROKEN":
            raise InvariantError("SCHEMA", "model JSON invalid")
        return Artifact(claim=f"{word}. Because.", evidence=[], uncertainty="", channel_id="", context_update="", requests=[])


def test_it_takes_only_reviews_of_a_merge_with_sources_open(tmp_path: Path):
    path, a, b = _tape(tmp_path)
    merges = mb.merges_from(path)
    assert [(m.row, m.task_id, m.right, m.doubt, m.recorded) for m in merges] == [
        (4, a.id, True, False, "PASS"),
        (5, a.id, False, False, "FAIL"),
        (10, b.id, True, True, "FAIL"),
        (12, b.id, True, False, "OTHER"),
    ]
    assert all(m.cap == 8_000 and m.tape == "t" for m in merges)
    # The brief as it was sent.
    m = merges[0]
    assert m.brief.slot_function == "verifier" and m.brief.goal == a.question and m.brief.mode == "verify"
    assert m.brief.success_criteria == ["ANSWER:"] and checks.SOURCE_RULE in m.brief.packet


def test_a_tape_of_another_view_or_no_comparison_gives_nothing(tmp_path: Path):
    shared, _, _ = _tape(tmp_path, SETTINGS | {"verify_view": "shared"}, "s.jsonl")
    assert mb.merges_from(shared) == []
    plain = tmp_path / "p.jsonl"
    plain.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m"}) + "\n")
    assert mb.merges_from(plain) == []


def test_each_rule_adds_its_words_after_the_source_rule(tmp_path: Path):
    m = mb.merges_from(_tape(tmp_path)[0])[0]
    assert mb.with_rule(m.brief, "none").packet == m.brief.packet
    told = mb.with_rule(m.brief, "told").packet
    assert checks.SOURCE_RULE + checks.SAMPLE_RULE in told and checks.HEADING_RULE not in told
    assert checks.SOURCE_RULE + checks.HEADING_RULE in mb.with_rule(m.brief, "headed").packet
    assert checks.SOURCE_RULE + checks.SAMPLE_RULE + checks.HEADING_RULE in mb.with_rule(m.brief, "both").packet
    assert m.brief.packet.count(checks.SOURCE_RULE) == 1 and checks.SAMPLE_RULE not in m.brief.packet


def test_a_review_keeps_the_reply_within_the_cap_and_reads_the_verdict(tmp_path: Path):
    m = mb.merges_from(_tape(tmp_path)[1 - 1])[0]
    adapter = Says()
    r = mb.review(m, "told", adapter)
    sent = adapter.briefs[0]
    assert sent.max_reply_tokens == 8_000 - adapter.estimate_tokens(mb.with_rule(m.brief, "told"))
    assert checks.SAMPLE_RULE in sent.packet
    assert (r.verdict, r.tokens, r.prompt_tokens, r.rule, r.right) == ("PASS", 150, 100, "told", True) and r.reason == "PASS. Because."
    assert mb.review(m, "none", Says(lambda b: "FAIL")).verdict == "FAIL"
    assert mb.review(m, "none", Says(lambda b: "Perhaps")).verdict == "OTHER"
    broken = mb.review(m, "none", Says(lambda b: "BROKEN"))
    assert broken.verdict == "ERROR" and broken.code == "SCHEMA"


def test_the_bench_runs_every_merge_under_every_rule_in_order(tmp_path: Path):
    merges = mb.merges_from(_tape(tmp_path)[0])
    lines = []
    for workers in (1, 4):
        done = mb.run_bench(merges, Says, workers=workers, progress=lines.append)
        assert [(r.row, r.rule) for r in done] == [(m.row, rule) for m in merges for rule in mb.RULES]
    assert len(lines) == 2 * len(merges) * 4
    assert [r.repeat for r in mb.run_bench(merges[:1], Says, rules=("none",), repeats=2)] == [0, 1]


@pytest.mark.parametrize("workers", [1, 4])
def test_a_spend_cap_counts_the_reviews_under_way(tmp_path: Path, workers):
    merges = mb.merges_from(_tape(tmp_path)[0])
    seen = []

    def stop(results):
        seen.append(len(results))
        return "cap" if len(results) >= 3 else ""

    done = mb.run_bench(merges, Says, workers=workers, stop_when=stop)
    # Reviews under way count at the largest so far, so it stops before more than three could have been paid for.
    assert 3 <= len(done) < 16 and max(seen) >= 3
    if workers == 1:
        assert len(done) == 3


def test_the_summary_compares_rules_product_by_product(tmp_path: Path):
    merges = mb.merges_from(_tape(tmp_path)[0])
    # Today's rule fails what it failed when recorded. The other stops it, and breaks one that passed.
    today = lambda brief: "FAIL" if "unconfirmed" in brief.packet or "Another" in brief.packet else "PASS"
    told = lambda brief: "FAIL" if "The total" in brief.packet or "Another" in brief.packet else "PASS"
    results = mb.run_bench(merges, lambda: Says(lambda b: (told if checks.SAMPLE_RULE in b.packet else today)(b)), rules=("none", "told"))
    s = mb.summarize(results, price_in=1.0, price_out=2.0)["rules"]
    assert s["none"]["right_failed"] == [1, 3] and s["told"]["right_failed"] == [1, 3]
    assert s["none"]["was_fail"] == [1, 1] and s["told"]["was_fail"] == [0, 1]
    assert s["none"]["was_pass"] == [0, 1] and s["told"]["was_pass"] == [1, 1]
    assert s["none"]["doubt"] == [1, 1] and s["none"]["no_doubt"] == [0, 2]
    assert s["none"]["wrong_caught"] == [1, 1] and s["none"]["errors"] == 0
    assert s["none"]["cost_total"] == round(4 * (100 * 1.0 + 50 * 2.0) / 1e6, 4)
    text = mb.render({"rules": s})
    assert "| told | 1 of 3 | 0 of 1 | 1 of 1 | 0 of 1 | 1 of 2 | 1 of 1 | 0 | 150 | $0.0008 |" in text
    assert "cost" not in mb.render(mb.summarize(results)).splitlines()[2]
    odd = mb.summarize(mb.run_bench(merges, lambda: Says(lambda b: "Perhaps"), rules=("none",)))["rules"]["none"]
    assert odd["errors"] == 4 and odd["right_failed"] == [0, 3]


def test_the_cli_reviews_and_refuses_what_it_cannot_do(tmp_path: Path, capsys):
    path, _, _ = _tape(tmp_path)
    capsys.readouterr()
    assert main(["merge-bench", "--tapes", str(path), "--dry-run", "--out", str(tmp_path / "d.json")]) == 0
    config = json.loads(capsys.readouterr().out)
    assert config["merges"] == 4 and config["right"] == 3 and config["recorded_fail"] == 1 and config["reviews"] == 16
    out = tmp_path / "m.json"
    assert main(["merge-bench", "--tapes", str(path), "--rules", "none,both", "--workers", "2", "--out", str(out)]) == 0
    saved = json.loads(out.read_text())
    assert saved["config"]["reviews"] == 8 and len(saved["results"]) == 8 and set(saved["summary"]["rules"]) == {"none", "both"}
    capsys.readouterr()
    empty = tmp_path / "e.jsonl"
    empty.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m"}) + "\n")
    for bad in (["--tapes", str(path), "--rules", "loud"], ["--tapes", str(path), "--rules", ""], ["--tapes", str(tmp_path / "no.jsonl")],
                ["--tapes", ""], ["--tapes", str(empty)], ["--tapes", str(path), "--price-in", "1"],
                ["--tapes", str(path), "--max-spend", "1"], ["--tapes", str(path), "--record", "a", "--replay", "b"]):
        assert main(["merge-bench", *bad, "--out", str(tmp_path / "x.json")]) == 1
        assert json.loads(capsys.readouterr().out)["code"] == "MERGE_BENCH"


def test_every_rule_is_the_same_brief_whichever_rule_a_tape_was_recorded_under(tmp_path: Path):
    """The held-out runs record under the rule. Today's rule must then be today's, with no sentence left or said twice."""
    m = mb.merges_from(_tape(tmp_path)[0])[0]
    plain = {rule: mb.with_rule(m.brief, rule).packet for rule in mb.RULES}
    for recorded in mb.RULES:
        brief = mb.with_rule(m.brief, recorded)
        assert {rule: mb.with_rule(brief, rule).packet for rule in mb.RULES} == plain
    assert checks.SAMPLE_RULE not in plain["none"] and checks.HEADING_RULE not in plain["none"]
    assert plain["both"].count(checks.SAMPLE_RULE) == 1 and plain["both"].count(checks.HEADING_RULE) == 1
    # A packet with no source rule goes as it came.
    bare = replace(m.brief, packet="no rule here")
    assert mb.with_rule(bare, "both").packet == "no rule here"


def test_a_tape_recorded_under_the_rule_still_gives_its_merges(tmp_path: Path):
    path, a, b = _tape(tmp_path, SETTINGS | {"verify_rule": "both"}, "both.jsonl")
    lines = path.read_text().splitlines()
    said = checks.SOURCE_RULE + checks.SAMPLE_RULE + checks.HEADING_RULE
    path.write_text("\n".join(line.replace(json.dumps(checks.SOURCE_RULE)[1:-1], json.dumps(said)[1:-1]) for line in lines) + "\n")
    merges = mb.merges_from(path)
    assert [(m.task_id, m.right, m.recorded) for m in merges] == [(a.id, True, "PASS"), (a.id, False, "FAIL"), (b.id, True, "FAIL"), (b.id, True, "OTHER")]
    assert all(said in m.brief.packet for m in merges)
    adapter = Says()
    mb.review(merges[0], "none", adapter)
    assert checks.SAMPLE_RULE not in adapter.briefs[0].packet and checks.HEADING_RULE not in adapter.briefs[0].packet


def test_the_summary_counts_where_two_rules_part(tmp_path: Path):
    merges = mb.merges_from(_tape(tmp_path)[0])  # right: The total, unconfirmed, Cut off. Wrong: Another
    # Today fails the doubted right answer and the wrong one. The rule passes the doubted one, fails the first right
    # one, and has no verdict on the last.
    def word(brief):
        if checks.SAMPLE_RULE in brief.packet:
            return ("FAIL" if "The total" in brief.packet or "Another" in brief.packet else
                    "Perhaps" if "Cut off" in brief.packet else "PASS")
        return "FAIL" if "unconfirmed" in brief.packet or "Another" in brief.packet else "PASS"

    results = mb.run_bench(merges, lambda: Says(word), rules=("none", "both"))
    summary = mb.summarize(results)
    assert summary["paired"] == {"both": {
        "right": {"first_failed_only": 1, "rule_failed_only": 1, "both_failed": 0, "both_passed": 0},
        "wrong": {"first_failed_only": 0, "rule_failed_only": 0, "both_failed": 1, "both_passed": 0},
    }}
    text = mb.render(summary)
    assert "Right answers, none against both: none alone failed 1, both alone failed 1, both failed 0, both passed 0." in text
    assert "Wrong answers, none against both: none alone failed 0, both alone failed 0, both failed 1, both passed 0." in text
    # Only a right answer today alone fails, and a wrong one the rule alone passes, in each direction.
    results = mb.run_bench(merges[:2], lambda: Says(lambda b: "PASS" if checks.SAMPLE_RULE in b.packet else "FAIL"), rules=("none", "both"))
    paired = mb.summarize(results)["paired"]["both"]
    assert paired["right"]["first_failed_only"] == 1 and paired["wrong"]["first_failed_only"] == 1 and paired["right"]["both_passed"] == 0
    # One rule has nothing to set against, and repeats pair with their own repeat.
    assert mb.summarize(mb.run_bench(merges[:1], Says, rules=("none",)))["paired"] == {}
    twice = mb.run_bench(merges[:1], lambda: Says(), rules=("none", "both"), repeats=2)
    assert mb.summarize(twice)["paired"]["both"]["right"]["both_passed"] == 2
