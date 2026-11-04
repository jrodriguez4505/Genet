"""A live session: one key entry, and every run still waits for its own y.

The scripts run for real here, with a stand-in for Python that logs what it was asked and whether it had the key.
No model is called.
"""

import shutil
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-not-a-real-key-for-this-test"


def _tree(tmp_path: Path) -> tuple[Path, dict]:
    (tmp_path / "scripts").mkdir()
    for name in ("team_runs.sh", "live_session.sh"):
        shutil.copy(ROOT / "scripts" / name, tmp_path / "scripts" / name)
    log = tmp_path / "python.log"
    stub = tmp_path / "python"
    stub.write_text(f'#!/bin/bash\necho "args=$* key=${{TASKORG_ANTHROPIC_KEY:-none}}" >> "{log}"\n'
                    'case "$1" in -I) cat >/dev/null; echo "smoke: complete"; exit 0 ;; esac\n'
                    'echo "saved stub"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return log, {"PATH": "/usr/bin:/bin", "PYTHON": str(stub), "GENET_SESSION_ONCE": "1"}


def _calls(log: Path) -> list[str]:
    lines = log.read_text().splitlines() if log.exists() else []
    return [line for line in lines if "import anthropic" not in line]


def _session(tmp_path: Path, env: dict, answers: str, *args: str) -> str:
    done = subprocess.run(["bash", "scripts/live_session.sh", *args], cwd=tmp_path, env=env, input=answers, text=True,
                          capture_output=True, timeout=60)
    return done.stdout + done.stderr


def test_an_approved_run_gets_the_key_once_entered_and_never_shows_it(tmp_path: Path):
    log, env = _tree(tmp_path)
    out = _session(tmp_path, env, f"{KEY}\ny\n", "second")
    calls = _calls(log)
    assert "Asked to run: second" in out and "about $0.06" in out and f"{len(KEY)} characters" in out
    assert len(calls) == 1 and "--max-spend 0.10" in calls[0] and "--record" in calls[0]
    # The run has the key in its environment, and nowhere else.
    assert calls[0].endswith(f"key={KEY}") and KEY not in calls[0].split(" key=")[0]
    assert KEY not in out


def test_nothing_runs_or_is_spent_without_a_y(tmp_path: Path):
    log, env = _tree(tmp_path)
    for answer in ("n", ""):
        out = _session(tmp_path, env, f"{KEY}\n{answer}\n", "second")
        assert "Not run." in out and _calls(log) == []  # no smoke test either: it spends


def test_no_key_runs_nothing(tmp_path: Path):
    log, env = _tree(tmp_path)
    assert "No key entered" in _session(tmp_path, env, "\ny\n", "second")
    assert _calls(log) == []


def test_a_mode_it_does_not_know_runs_nothing(tmp_path: Path):
    log, env = _tree(tmp_path)
    assert "Nothing was run" in _session(tmp_path, env, f"{KEY}\ny\n", "wipe")
    assert _calls(log) == []


def test_a_request_is_a_mode_read_once_and_a_stale_one_is_dropped(tmp_path: Path):
    log, env = _tree(tmp_path)
    (tmp_path / "data").mkdir()
    request = tmp_path / "data" / ".live-request"
    request.write_text("second\n")  # left from an earlier sitting
    p = subprocess.Popen(["bash", "scripts/live_session.sh"], cwd=tmp_path, env=env, text=True, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        p.stdin.write(f"{KEY}\n")
        p.stdin.flush()
        while "Waiting for a run" not in p.stdout.readline():
            pass
        time.sleep(1.5)
        assert not request.exists() and _calls(log) == []
        # Anything but a mode's letters is dropped from a request, so it cannot reach a command.
        request.write_text("sec;ond$(touch pwned)\n")
        p.stdin.write("n\n")
        p.stdin.close()
        out = p.stdout.read()
        p.wait(timeout=30)
    finally:
        p.kill()
    assert not (tmp_path / "pwned").exists() and _calls(log) == [] and not request.exists()
    assert "Nothing was run" in out or "Not run." in out


def test_outside_a_session_the_key_in_the_environment_is_not_enough(tmp_path: Path):
    """Only a live session skips the key prompt and the smoke test."""
    log, env = _tree(tmp_path)
    env.pop("GENET_SESSION_ONCE")
    env["TASKORG_ANTHROPIC_KEY"] = "from-the-environment"
    done = subprocess.run(["bash", "scripts/team_runs.sh", "second"], cwd=tmp_path, env=env, input=f"1\n{KEY}\nn\n", text=True,
                          capture_output=True, timeout=60)
    assert "Key received" in done.stdout and "Smoke test" in done.stdout
    calls = _calls(log)
    assert any("--families lookup" in c and c.endswith(f"key={KEY}") for c in calls)


HELD = ["heldout-s%d-%d" % (seed, size) for seed in (101, 102, 103, 104, 105) for size in (10, 20)]


def _held_tree(tmp_path: Path, **stub_env) -> tuple[Path, dict]:
    """A stand-in for Python that writes the results a run would, and whatever the test says it should."""
    log, env = _tree(tmp_path)
    stub = tmp_path / "python"
    stub.write_text(f'''#!/bin/bash
echo "args=$* key=${{TASKORG_ANTHROPIC_KEY:-none}}" >> "{log}"
out=""; while [ $# -gt 0 ]; do [ "$1" = --out ] && out=$2; shift; done
case "$out" in
  "") ;;
  *"${{STUB_DIES:-none}}.json") echo "crashed" ;;
  *"${{STUB_STOPS:-none}}.json") echo \'{{"config": {{"stopped_after": 3}}}}\' > "$out" ;;
  *) echo \'{{"config": {{}}}}\' > "$out" ;;
esac
''')
    return log, env | stub_env


def _held(tmp_path: Path, env: dict, answers: str = f"{KEY}\ny\n") -> str:
    return _session(tmp_path, env, answers, "heldout")


def test_the_held_out_run_is_the_plan_it_shows(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    out = _held(tmp_path, env)
    calls = _calls(log)
    assert len(calls) == 12 and "about $2.50" in out and "Done." in out and KEY not in out
    # Every seed at both sizes, all three strategies, the rule on, capped and taped.
    for name, call in zip(HELD, calls):
        seed, size = name.split("-s")[1].split("-")
        assert f"--seed {seed} " in call and f"--entities {size} " in call and "--verify-rule both" in call
        assert "--strategies single,always-told,genet" in call and "--context 8000" in call and "--tool-rounds 4" in call
        assert f"--max-spend {'0.42' if size == '10' else '0.20'} " in call
        assert f"--record data/tapes/{name}.jsonl" in call and f"--out data/compare/{name}.json" in call
        assert ("--per-family 6" if size == "10" else "--families aggregate,breadth --per-family 3") in call
    merges, built = calls[10], calls[11]
    assert "merge-bench" in merges and "--rules none,both" in merges and "--max-spend 0.85" in merges
    assert ",".join(f"data/tapes/{name}.jsonl" for name in HELD) in merges
    assert "verify-bench" in built and "--seed 101 " in built and "independent-layered,independent-both" in built and "--max-spend 0.15" in built
    # The run has the key in its environment, and nowhere else.
    assert all(c.endswith(f"key={KEY}") and KEY not in c.split(" key=")[0] for c in calls)


def test_the_refine_run_is_the_plan_it_shows(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    out = _session(tmp_path, env, f"{KEY}\ny\n", "refine")
    calls = _calls(log)
    assert len(calls) == 2 and "about $0.17" in out and "Done." in out and KEY not in out
    heading, rework = calls
    assert "verify-bench" in heading and "--seed 111 " in heading and "--arms heading" in heading and "independent-layered,independent-both" in heading
    assert "--questions 6" in heading and "--entities 20" in heading and "--max-spend 0.15" in heading and "--record data/tapes/refine-heading.jsonl" in heading
    assert "rework-bench" in rework and "--max-spend 0.15" in rework and "--record data/tapes/refine-rework.jsonl" in rework
    assert ",".join(f"data/tapes/{name}.jsonl" for name in HELD) in rework
    assert all(c.endswith(f"key={KEY}") and KEY not in c.split(" key=")[0] for c in calls)


def test_the_refine_run_needs_a_y_and_goes_on_from_what_finished(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "refine") and _calls(log) == []
    (tmp_path / "t").mkdir()
    log, env = _held_tree(tmp_path / "t", STUB_DIES="refine-rework")
    out = _session(tmp_path / "t", env, f"{KEY}\ny\n", "refine")
    assert "refine-rework did not finish" in out and "scripts/team_runs.sh refine" in out and len(_calls(log)) == 2
    out = _session(tmp_path / "t", env | {"STUB_DIES": "none"}, f"{KEY}\ny\n", "refine")
    assert "refine-heading: already done" in out and "Done." in out and len(_calls(log)) == 3


def test_the_held_out_run_needs_a_y(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _held(tmp_path, env, f"{KEY}\nn\n") and _calls(log) == []


def test_the_held_out_run_stops_at_the_first_run_that_stops_and_goes_on_from_there(tmp_path: Path):
    for stub in ({"STUB_STOPS": "heldout-s102-10"}, {"STUB_DIES": "heldout-s102-10"}):
        (tmp_path / "t").mkdir()
        log, env = _held_tree(tmp_path / "t", **stub)
        out = _held(tmp_path / "t", env)
        assert len(_calls(log)) == 3 and "Done." not in out
        if "STUB_STOPS" in stub:
            # A run that stopped itself is not run again, whatever it was stopped by, and it stops the rest.
            assert "heldout-s102-10 stopped early" in out
            again = _held(tmp_path / "t", env)
            assert again.count("already done") == 3 and "heldout-s102-10 stopped early" in again and len(_calls(log)) == 3
        else:
            assert "heldout-s102-10 did not finish" in out
            # A run that left nothing is run again, and what finished is not. The tape it left is kept.
            tape = tmp_path / "t" / "data" / "tapes" / "heldout-s102-10.jsonl"
            tape.write_text("what it spent\n")
            out = _held(tmp_path / "t", env | {"STUB_DIES": "none"})
            calls = _calls(log)
            assert len(calls) == 13 and "Done." in out and out.count("already done") == 2
            assert "heldout-s102-10" in calls[3] and "heldout-s101" not in calls[3]
            kept = list((tmp_path / "t" / "data" / "tapes").glob("heldout-s102-10-cut-*.jsonl"))
            assert len(kept) == 1 and kept[0].read_text() == "what it spent\n" and not tape.exists()
        shutil.rmtree(tmp_path / "t")
