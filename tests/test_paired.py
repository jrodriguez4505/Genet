"""Two arms on the same questions, with their noise (taskorg.paired, and `taskorg paired`). A live comparison here is 12
to 54 questions an arm, so a difference of a few right answers can be chance. Read again on 11 November, every right or
wrong difference in the live tests so far was within it; what held was splitting where one call could not hold the work
(right 1 of 12 for one agent, 8 to 11 split, p at most 0.01) and the tokens a question against CrewAI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskorg.cli import main
from taskorg.paired import boot_range, exact_right, judged_right, paired, sign_p


def test_the_sign_test_is_exact_and_two_sided():
    assert sign_p(0, 0) == 1.0 and sign_p(3, 3) == 1.0
    assert sign_p(5, 0) == sign_p(0, 5) == 2 / 32
    assert sign_p(9, 0) == 2 / 512
    assert sign_p(5, 1) == pytest.approx(2 * 7 / 64)  # the split rule on the 54: +5 / -1
    assert sign_p(11, 1) < 0.01 < sign_p(4, 2)


def test_the_bootstrap_range_is_seeded_and_holds_the_mean():
    diffs = [10, -4, 7, 0, 25, -12, 3]
    lo, hi = boot_range(diffs)
    assert (lo, hi) == boot_range(diffs) and lo <= sum(diffs) / len(diffs) <= hi and lo < hi
    assert boot_range([5, 5, 5]) == (5, 5) and boot_range([]) == (0.0, 0.0)


def _r(right=True, done=True, tokens=100, score=None):
    r = {"status": "complete" if done else "abort", "correct": right, "tokens": tokens}
    return r | ({"judge_score": score} if score is not None else {})


def test_only_the_questions_where_the_arms_differ_count():
    first = {1: _r(True), 2: _r(False), 3: _r(False), 4: _r(True, done=False), 5: _r(True)}
    second = {1: _r(True, tokens=300), 2: _r(True), 3: _r(True), 4: _r(True), 6: _r(True)}
    p = paired(first, second, right=exact_right, wrong=lambda r: r["status"] == "complete" and not r["correct"])
    assert p.questions == 4  # 5 and 6 are in one arm only
    assert (p.right.before, p.right.after, p.right.gained, p.right.lost) == (1, 4, 3, 0)
    assert (p.wrong.before, p.wrong.after, p.wrong.gained, p.wrong.lost) == (2, 0, 0, 2)
    assert p.tokens == 50 and p.right.noise  # 3 of 3 is still within noise: p = 0.25
    lines = p.lines("a", "b")
    assert lines[0] == "b against a, 4 questions:" and "right 1 -> 4 (+3 / -0 questions; p = 0.25)  within noise" in lines[1]


def test_a_right_finish_needs_a_finished_run():
    assert judged_right(_r(score=80)) and not judged_right(_r(score=79)) and not judged_right(_r(done=False, score=95))
    assert exact_right(_r(True)) and not exact_right(_r(True, done=False))


def _results(path: Path, rows: list[dict]) -> str:
    path.write_text(json.dumps({"results": rows}))
    return str(path)


def test_the_command_pairs_two_arms_and_says_which_differences_are_noise(tmp_path: Path, capsys):
    rows = []
    for i in range(12):
        rows.append({"strategy": "single", "task_id": f"q{i}", "status": "complete", "correct": i == 0, "tokens": 1000})
        rows.append({"strategy": "split-4", "task_id": f"q{i}", "status": "complete", "correct": i < 11, "tokens": 1000 + i})
    both = _results(tmp_path / "sweep.json", rows)
    assert main(["paired", f"{both}:single", f"{both}:split-4"]) == 0
    out = capsys.readouterr().out
    assert "sweep:split-4 against sweep:single, 12 questions:" in out
    assert "right 1 -> 11 (+10 / -0 questions; p = 0.00)\n" in out and "wrong 11 -> 1" in out
    # A file of two strategies needs one named; a file of one does not.
    assert main(["paired", both, f"{both}:split-4"]) != 0 and "name one as" in capsys.readouterr().out
    one = _results(tmp_path / "one.json", [r for r in rows if r["strategy"] == "single"])
    assert main(["paired", one, f"{both}:split-4"]) == 0
    assert main(["paired", f"{both}:genet", one]) != 0 and "has no strategy genet" in capsys.readouterr().out


def test_judged_results_are_graded_by_their_scores(tmp_path: Path, capsys):
    a = _results(tmp_path / "a.json", [{"strategy": "genet", "task_id": "q", "status": "complete", "correct": False,
                                        "judge_score": 90, "tokens": 5}])
    b = _results(tmp_path / "b.json", [{"strategy": "genet", "task_id": "q", "status": "complete", "correct": False,
                                        "judge_score": 10, "tokens": 5}])
    assert main(["paired", a, b]) == 0 and "right 1 -> 0" in capsys.readouterr().out
    assert main(["paired", a, b, "--grading", "exact"]) == 0 and "right 0 -> 0" in capsys.readouterr().out
    other = _results(tmp_path / "c.json", [{"strategy": "genet", "task_id": "z", "status": "complete", "tokens": 1}])
    assert main(["paired", a, other]) != 0 and "share no question" in capsys.readouterr().out
