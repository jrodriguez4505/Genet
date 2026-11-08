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
[ "$1" = -I ] && exit "${{STUB_GATE:-0}}"
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


WHOLE = ["whole-s%d-%d" % (seed, size) for seed in (106, 107, 108, 109, 110) for size in (10, 20)]


def test_the_whole_run_is_the_plan_it_shows(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    out = _session(tmp_path, env, f"{KEY}\ny\n", "whole")
    calls = _calls(log)
    assert len(calls) == 10 and "about $2.05" in out and "$3.35 in all" in out and "Done." in out and KEY not in out
    for name, call in zip(WHOLE, calls):
        seed, size = name.split("-s")[1].split("-")
        assert "compare" in call and "--adapter anthropic" in call
        assert f"--seed {seed} " in call and f"--entities {size} " in call and "--context 8000" in call and "--tool-rounds 4" in call
        # The sentence is on in every run, and the rule and the reason are left at their defaults, on.
        assert "--author-rule headed" in call and "--verify-rule" not in call and "--no-rework-reason" not in call
        assert f"--record data/tapes/{name}.jsonl" in call and f"--out data/compare/{name}.json" in call
        if size == "10":
            assert "--per-family 6" in call and "--strategies always-told,genet " in call and "--max-spend 0.35 " in call
        else:
            assert "--families aggregate,breadth --per-family 3" in call and "--strategies single,always-told,genet " in call and "--max-spend 0.32 " in call
    assert all(c.endswith(f"key={KEY}") and KEY not in c.split(" key=")[0] for c in calls)


RERUN = ["rerun-s%d-%d" % (seed, size) for seed in (107, 108, 109, 110) for size in (10, 20)] + ["rerun-s112-20"]


def test_the_rerun_is_the_plan_it_shows(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    out = _session(tmp_path, env, f"{KEY}\ny\n", "rerun")
    calls = _calls(log)
    assert len(calls) == 9 and "about $1.82" in out and "$3.00 in all" in out and "Done." in out and KEY not in out
    for name, call in zip(RERUN, calls):
        seed, size = name.split("-s")[1].split("-")
        assert "compare" in call and "--adapter anthropic" in call
        assert f"--seed {seed} " in call and f"--entities {size} " in call and "--context 8000" in call and "--tool-rounds 4" in call
        assert "--author-rule headed" in call and "--verify-rule" not in call and "--no-rework-reason" not in call
        assert f"--record data/tapes/{name}.jsonl" in call and f"--out data/compare/{name}.json" in call
        if size == "10":
            assert "--per-family 6" in call and "--strategies always-told,genet " in call and "--max-spend 0.35 " in call
        else:
            assert "--families aggregate,breadth --per-family 3" in call and "--strategies single,always-told,genet " in call and "--max-spend 0.32 " in call
    assert all(c.endswith(f"key={KEY}") and KEY not in c.split(" key=")[0] for c in calls)


def test_the_gap_rule_run_is_the_plan_it_shows_and_needs_a_y(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "gaprule") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "gaprule")
    calls = _calls(log)
    assert len(calls) == 1 and "about $0.42" in out and "before $0.50" in out and "Done." in out and KEY not in out
    call = calls[0]
    assert "merge-bench" in call and "--rules both,named " in call and "--max-spend 0.50 " in call and "--adapter anthropic" in call
    assert ",".join(f"data/tapes/{name}.jsonl" for name in RERUN) in call
    assert "--record data/tapes/gaprule-merges.jsonl" in call and "--out data/compare/gaprule-merges.json" in call
    assert call.endswith(f"key={KEY}") and KEY not in call.split(" key=")[0]
    # Done once, it is not paid for twice.
    assert "gaprule-merges: already done" in _session(tmp_path, env, f"{KEY}\ny\n", "gaprule") and len(_calls(log)) == 1


def test_the_aside_run_is_two_steps_and_the_second_waits_on_the_first(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "aside") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "aside")
    calls = _calls(log)
    assert len(calls) == 3 and "about $0.54" in out and "before $0.30" in out and "before $0.45" in out and "Done." in out
    first, gate, second = calls
    assert "merge-bench" in first and "--rules aside " in first and "--max-spend 0.30 " in first and "--adapter anthropic" in first
    assert ",".join(f"data/tapes/{name}.jsonl" for name in RERUN) in first
    assert "--record data/tapes/aside-insample.jsonl" in first and "--out data/compare/aside-insample.json" in first
    assert gate.startswith("args=-I -")
    held = HELD + ["whole-s106-10", "whole-s106-20", "whole-s107-10"]
    assert "--rules aside " in second and "--max-spend 0.45 " in second
    assert ",".join(f"data/tapes/{name}.jsonl" for name in held) in second
    assert "--record data/tapes/aside-heldout.jsonl" in second and "--out data/compare/aside-heldout.json" in second
    assert all(c.endswith(f"key={KEY}") and KEY not in c.split(" key=")[0] for c in calls) and KEY not in out
    # Done once, neither step is paid for twice; only the check between them, which reads two files, runs again.
    again = _session(tmp_path, env, f"{KEY}\ny\n", "aside")
    assert "aside-insample: already done" in again and "aside-heldout: already done" in again
    assert [c.split(" key=")[0] for c in _calls(log)[3:]] == ["args=-I -"]


def test_the_aside_run_stops_after_a_first_step_that_misses(tmp_path: Path):
    log, env = _held_tree(tmp_path, STUB_GATE="3")
    out = _session(tmp_path, env, f"{KEY}\ny\n", "aside")
    calls = _calls(log)
    assert len(calls) == 2 and "step 2 was not run" in out and "aside-heldout" not in " ".join(calls)


GAPCHECK = ["rerun-s108-10", "rerun-s108-20", "rerun-s109-10", "rerun-s109-20", "rerun-s110-10", "rerun-s112-20",
            "heldout-s101-10", "heldout-s102-10", "heldout-s103-10", "heldout-s103-20", "heldout-s105-10"]


def test_the_gap_check_run_replays_each_tape_three_times_and_needs_a_y(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "gapcheck") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "gapcheck")
    calls = _calls(log)
    assert len(calls) == 33 and "about $0.15" in out and "before $0.03" in out and "Done." in out and KEY not in out
    names = [f"gapcheck-r{r}-{tape}" for r in (1, 2, 3) for tape in GAPCHECK]
    for name, call in zip(names, calls):
        tape = name.split("-", 2)[2]
        seed, size = tape.rsplit("-s", 1)[1].split("-")
        assert "compare" in call and "--adapter anthropic" in call and "--max-spend 0.03 " in call
        assert "--gap-check --then-live" in call and f"--replay data/tapes/{tape}.jsonl" in call
        assert f"--record data/tapes/{name}.jsonl" in call and f"--out data/compare/{name}.json" in call
        assert f"--seed {seed} " in call and f"--entities {size} " in call and "--context 8000 --tool-rounds 4" in call
        # Each tape with the settings it was recorded under.
        assert ("--author-rule headed" in call) == tape.startswith("rerun") and ("--no-rework-reason" in call) == tape.startswith("heldout")
        assert call.endswith(f"key={KEY}") and KEY not in call.split(" key=")[0]
    # Done once, nothing is paid for twice.
    again = _session(tmp_path, env, f"{KEY}\ny\n", "gapcheck")
    assert again.count("already done") == 33 and len(_calls(log)) == 33


def test_the_sonnet_run_is_two_steps_each_with_its_own_y(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "sonnet") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\nn\n", "sonnet")
    calib, gate = _calls(log)
    assert "on claude-sonnet-5-5" in out and "Step 2 not run." in out and KEY not in out
    assert "--price-in 2 --price-out 10 --max-spend 1.50 " in calib and "--seed 108 " in calib and "--per-family 1 " in calib
    assert "--entities 20 " in calib and "--strategies always-told,genet " in calib and "--author-rule headed" in calib
    assert "--record data/tapes/sonnet-calib.jsonl" in calib and gate.startswith("args=-I -")
    out = _session(tmp_path, env, f"{KEY}\ny\ny\n", "sonnet")
    ten, twenty = _calls(log)[3:]
    assert "sonnet-calib: already done" in out and "Done." in out
    for call, size, strategies in ((ten, "10", "always-told,genet"), (twenty, "20", "single,always-told,genet")):
        # The rerun's settings for seed 108, so each trial pairs with Haiku's.
        assert f"--entities {size} " in call and f"--strategies {strategies} " in call and "--seed 108 " in call
        assert "--price-in 2 --price-out 10 --max-spend 6.00 " in call and "--context 8000 --tool-rounds 4 --author-rule headed" in call
        assert f"--record data/tapes/sonnet-s108-{size}.jsonl" in call and call.endswith(f"key={KEY}")


def test_the_sonnet_run_stops_after_a_calibration_that_finds_a_problem(tmp_path: Path):
    log, env = _held_tree(tmp_path, STUB_GATE="3")
    out = _session(tmp_path, env, f"{KEY}\ny\ny\n", "sonnet")
    assert len(_calls(log)) == 2 and "Results: data/compare/sonnet-calib.json" in out and "Done." not in out


def test_the_second_sonnet_seed_is_seed_110_with_the_reruns_settings(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "sonnettwo") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "sonnettwo")
    ten, twenty = _calls(log)
    assert "on claude-sonnet-5-5" in out and "about $5.40" in out and "Done." in out and KEY not in out
    for call, size, strategies in ((ten, "10", "always-told,genet"), (twenty, "20", "single,always-told,genet")):
        assert f"--entities {size} " in call and f"--strategies {strategies} " in call and "--seed 110 " in call
        assert "--price-in 2 --price-out 10 --max-spend 6.00 " in call and "--context 8000 --tool-rounds 4 --author-rule headed" in call
        assert f"--record data/tapes/sonnet-s110-{size}.jsonl" in call and call.endswith(f"key={KEY}")


def test_the_agent_count_sweep_runs_both_seeds_at_both_limits_on_haiku(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "agents") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "agents")
    calls = _calls(log)
    assert len(calls) == 4 and "on claude-haiku-5-5" in out and "about $2.20" in out and "Done." in out
    for call, (seed, cap) in zip(calls, [(s, c) for s in (113, 114) for c in (8000, 64000)]):
        assert f"--seed {seed} " in call and f"--context {cap} " in call and "--max-calls 80" in call
        assert "--strategies single,split-2,split-4,split-10,split-20,always-told,genet " in call
        assert "--entities 20 " in call and "--price-in 0.10 --price-out 0.50 --max-spend 1.50 " in call
        assert f"--record data/tapes/agents-s{seed}-{cap}.jsonl" in call and call.endswith(f"key={KEY}")


def _env_stub(tmp_path: Path, log: Path):
    """The held stand-in, also logging the cache and verifier-model settings each run had."""
    stub = tmp_path / "python"
    stub.write_text(stub.read_text().replace('echo "args=$* key=', 'echo "cache=${TASKORG_MODEL_CACHE:-} verify=${TASKORG_MODEL_NAME_VERIFY:-} args=$* key='))


def test_the_cache_run_turns_caching_on_for_the_sweeps_64000_questions(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    _env_stub(tmp_path, log)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "cache") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "cache")
    calls = _calls(log)
    assert len(calls) == 2 and "on claude-haiku-5-5" in out and "about $0.25" in out and "Done." in out
    for call, seed in zip(calls, (113, 114)):
        assert call.startswith("cache=1 verify= args=") and f"--seed {seed} " in call and "--context 64000 " in call
        assert "--strategies single,split-4,genet " in call and "--max-spend 0.50 " in call
        assert f"--record data/tapes/cache-s{seed}-64000.jsonl" in call and call.endswith(f"key={KEY}")


def test_the_mixed_run_has_sonnet_check_and_prices_it_as_sonnet(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    _env_stub(tmp_path, log)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "mixed") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\n", "mixed")
    calls = _calls(log)
    assert len(calls) == 4 and "on claude-haiku-5-5" in out and "about $2.20" in out and "Done." in out
    for call, (seed, size, cap) in zip(calls, [(108, 10, "1.20"), (108, 20, "0.70"), (110, 10, "1.20"), (110, 20, "0.70")]):
        assert call.startswith("cache= verify=claude-sonnet-5-5 args=") and f"--seed {seed} " in call
        assert f"--entities {size} " in call and "--strategies always-told,genet " in call and f"--max-spend {cap} " in call
        assert "--price-in 0.10 --price-out 0.50 " in call and "--price claude-sonnet-5-5=2/10" in call
        assert "--context 8000 --tool-rounds 4 --author-rule headed" in call
        assert f"--record data/tapes/mixed-s{seed}-{size}.jsonl" in call and call.endswith(f"key={KEY}")


def test_the_opus_run_calibrates_then_waits_for_a_second_y(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "opus") and _calls(log) == []
    out = _session(tmp_path, env, f"{KEY}\ny\nn\n", "opus")
    calib, gate = _calls(log)
    assert "on claude-opus-5-5" in out and "Step 2 not run." in out and KEY not in out
    assert "--price-in 4 --price-out 20 --max-spend 2.50 " in calib and "--seed 108 " in calib and "--per-family 1 " in calib
    assert gate.startswith("args=-I - 4 20")
    out = _session(tmp_path, env, f"{KEY}\ny\ny\n", "opus")
    ten, twenty = _calls(log)[3:]
    assert "opus-calib: already done" in out and "Done." in out
    for call, size, strategies in ((ten, "10", "always-told,genet"), (twenty, "20", "single,always-told,genet")):
        assert f"--entities {size} " in call and f"--strategies {strategies} " in call and "--seed 108 " in call
        assert "--price-in 4 --price-out 20 --max-spend 8.00 " in call and "--context 8000 --tool-rounds 4 --author-rule headed" in call
        assert f"--record data/tapes/opus-s108-{size}.jsonl" in call and call.endswith(f"key={KEY}")


def test_the_sonnet_sweep_runs_both_seeds_at_8000_on_sonnet(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    out = _session(tmp_path, env, f"{KEY}\ny\n", "sonnetsweep")
    calls = _calls(log)
    assert len(calls) == 2 and "on claude-sonnet-5-5" in out and "about $9.40" in out and "Done." in out
    for call, seed in zip(calls, (113, 114)):
        assert f"--seed {seed} " in call and "--context 8000 " in call and "--max-calls 80" in call
        assert "--strategies single,split-4,split-10,split-20,genet " in call
        assert "--price-in 2 --price-out 10 --max-spend 6.00 " in call
        assert f"--record data/tapes/sonnetsweep-s{seed}-8000.jsonl" in call and call.endswith(f"key={KEY}")


def test_other_runs_stay_on_haiku(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    out = _session(tmp_path, env, f"{KEY}\ny\n", "gaprule")
    assert "on claude-haiku-5-5" in out and "--price-in 0.10 --price-out 0.50 " in _calls(log)[0]


def test_the_rerun_needs_a_y_and_goes_on_from_what_finished(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "rerun") and _calls(log) == []
    (tmp_path / "t").mkdir()
    log, env = _held_tree(tmp_path / "t", STUB_DIES="rerun-s108-10")
    out = _session(tmp_path / "t", env, f"{KEY}\ny\n", "rerun")
    assert "rerun-s108-10 did not finish" in out and "scripts/team_runs.sh rerun" in out and len(_calls(log)) == 3
    out = _session(tmp_path / "t", env | {"STUB_DIES": "none"}, f"{KEY}\ny\n", "rerun")
    assert out.count("already done") == 2 and "Done." in out and len(_calls(log)) == 10


def test_the_whole_run_needs_a_y_and_goes_on_from_what_finished(tmp_path: Path):
    log, env = _held_tree(tmp_path)
    assert "Not run." in _session(tmp_path, env, f"{KEY}\nn\n", "whole") and _calls(log) == []
    (tmp_path / "t").mkdir()
    log, env = _held_tree(tmp_path / "t", STUB_DIES="whole-s107-10")
    out = _session(tmp_path / "t", env, f"{KEY}\ny\n", "whole")
    assert "whole-s107-10 did not finish" in out and "scripts/team_runs.sh whole" in out and len(_calls(log)) == 3
    out = _session(tmp_path / "t", env | {"STUB_DIES": "none"}, f"{KEY}\ny\n", "whole")
    assert out.count("already done") == 2 and "Done." in out and len(_calls(log)) == 11


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
