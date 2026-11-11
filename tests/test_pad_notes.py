"""Long notes for a test at a real call limit (build_suite's pad, compare --pad-notes). The 7-8 November sweep found one
agent right on 1 of 12 where its call limit was 8,000 tokens, and every split on 8 to 11. But 8,000 is our own limit, and
each note is about 2,000 characters: the limit bit on twenty notes together. Padding grows each note with neutral sections
while the questions, the figures and each note's own paragraphs stay as they were, so the same questions can be asked
where a question's notes pass Loong's 100,000-token limit."""

from __future__ import annotations

import json
import re
from pathlib import Path

from taskorg.cli import main
from taskorg.suite import PAD, build_suite

SWEEP = dict(seed=113, per_family=3, families=("aggregate", "breadth"), entities=20, distractors=6)


def test_padding_keeps_the_questions_the_figures_and_every_paragraph():
    plain, padded = build_suite(**SWEEP), build_suite(**SWEEP, pad=30_000)
    assert [(t.question, t.answer, t.kind) for t in plain.tasks] == [(t.question, t.answer, t.kind) for t in padded.tasks]
    assert {n: vars(c) for n, c in plain.companies.items()} == {n: vars(c) for n, c in padded.companies.items()}
    for name, text in plain.corpus.items():
        grown = padded.corpus[name]
        assert len(grown) >= 30_000 and grown.startswith("\n\n".join(text.split("\n\n")[:2]))
        assert all(para in grown for para in text.rstrip("\n").split("\n\n"))


def test_unpadded_suites_are_as_before_and_padding_is_the_same_each_time():
    assert build_suite(**SWEEP).corpus == build_suite(**SWEEP, pad=0).corpus
    assert build_suite(**SWEEP, pad=12_000).corpus == build_suite(**SWEEP, pad=12_000).corpus
    short = build_suite(**SWEEP)
    assert build_suite(**SWEEP, pad=100).corpus == short.corpus  # a note already that long is left as it is


def test_no_padded_sentence_answers_or_looks_like_an_answer():
    assert not [s for s in PAD if re.search(r"revenue|sales|churn|\bQ[1-4]\b|quarter|FY20", s, re.IGNORECASE)]
    plain, padded = build_suite(**SWEEP), build_suite(**SWEEP, pad=20_000)
    money = re.compile(r"revenue|sales|churn", re.IGNORECASE)

    def figures(text):
        paras = [p for p in text.split("\n\n") if p and not p.startswith(("#", "Region:"))]
        return sorted(s for p in paras for s in re.split(r"(?<=\.) ", p.strip()) if money.search(s))

    for name in plain.corpus:
        # Every sentence that names a revenue, sales or churn figure is one the note already had.
        assert figures(padded.corpus[name]) == figures(plain.corpus[name]) != []


def test_compare_takes_the_padding_and_puts_it_on_the_record(tmp_path: Path, capsys):
    base = ["compare", "--dry-run", "--seed", "113", "--per-family", "1", "--families", "aggregate", "--entities", "20"]
    assert main(base) == 0 and "pad_notes" not in json.loads(capsys.readouterr().out)
    assert main(base + ["--pad-notes", "30000"]) == 0 and json.loads(capsys.readouterr().out)["pad_notes"] == 30_000
    corpus = tmp_path / "c"
    assert main(["compare", "--seed", "113", "--per-family", "1", "--families", "aggregate", "--entities", "4",
                 "--pad-notes", "5000", "--strategies", "single", "--corpus", str(corpus),
                 "--out", str(tmp_path / "o.json")]) == 0
    assert all(len(p.read_text()) >= 5_000 for p in corpus.glob("*.md"))
    capsys.readouterr()
    assert main(["compare", "--benchmark", "hotpot", "--questions", str(tmp_path / "q.jsonl"), "--pad-notes", "5000",
                 "--out", str(tmp_path / "h.json")]) != 0
    assert "not a benchmark" in capsys.readouterr().out
