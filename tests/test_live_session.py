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
