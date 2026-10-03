"""Runs saved before the 0.2 rename still load, translated to the current names."""

import json
from pathlib import Path

from taskorg.diagnostics import diagnose
from taskorg.persist import load_run, save_run

OLD = {
    "id": "so-001",
    "status": "complete",
    "picture": {
        "who_head_id": "head-1",
        "slots": [
            {"id": "head-1", "function": "head", "skill": "draft", "channel_id": None, "tools": ["write"]},
            {"id": "w-a", "function": "worker", "skill": "execute", "channel_id": "a", "tools": ["write"]},
            {"id": "why-1", "function": "why", "hot_qual": "assault", "channel_id": None, "tools": ["write"]},
        ],
        "primary": "head-1",
        "effect": "Summarize",
        "success_criteria": ["default task"],
        "tempo": "mission",
        "decision_points": ["look"],
        "current_picture": "now",
        "step_off_picture": "before",
        "end_state": "done",
        "purpose": "p",
        "method": "m",
    },
    "notes": {"plan-wrong": {"id": "plan-wrong", "body": "b", "status": "closed", "response": "CHANGE_METHOD", "reason": "r", "kind": "plan_wrong"}},
    "artifacts": [{"claim": "c", "evidence": [], "uncertainty": "", "channel_id": "a", "delta_to_picture": "d", "requests": []}],
    "deltas": [{"claim": "c", "evidence": [], "uncertainty": "", "channel_id": "a", "net": "element"},
               {"claim": "c", "evidence": [], "uncertainty": "", "channel_id": "out", "net": "out"}],
    "open_nets": ["element", "up", "out"],
    "who_open": ["head-1", "why-1"],
    "log": [{"event": "mission_open", "detail": {}, "ts": 1.0}],
    "calls": [],
    "budget": {"pace": "crawl", "max_calls": 4, "max_tokens": 4000, "max_seconds": 30, "max_tokens_per_call": 1500,
               "allow_split": False, "allow_adapt": False},
}


def test_old_saved_run_loads_with_new_names(tmp_path: Path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps(OLD))
    run = load_run(path)
    assert run.state.lead_id == "head-1" and run.state.goal == "Summarize" and run.state.context == "now"
    assert run.state.initial_context == "before" and run.state.done_when == "done"
    assert [s.function for s in run.state.slots] == ["lead", "worker", "reviewer"]
    assert run.state.slots[2].skill == "execute"  # oldest files used other skill names
    assert run.notes["plan-wrong"].kind == "replan"
    assert run.artifacts[0].context_update == "d"
    assert [d.stream for d in run.deltas] == ["merge", "report"]
    assert run.open_streams == ["merge", "escalate", "report"]
    assert run.budget.tier == "tight"
    assert diagnose(run)["tier"]["name"] == "tight"


def test_saved_runs_use_the_new_format(tmp_path: Path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps(OLD))
    again = save_run(load_run(path), tmp_path / "new.json")
    saved = json.loads(again.read_text())
    assert saved["format"] == 2 and "state" in saved and "picture" not in saved
    assert load_run(again).state.goal == "Summarize"
