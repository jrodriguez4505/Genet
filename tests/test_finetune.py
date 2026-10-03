import json
from pathlib import Path

from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.finetune import (
    LivePolicy,
    build_corpus,
    fine_tune_head,
    parse_action_json,
    write_jsonl,
)
from taskorg.gates import World
from taskorg.policy import encode_board


def test_sft_rows_are_chat_json():
    rows = build_corpus(20)
    assert len(rows) == 20
    row = rows[0]
    roles = [m["role"] for m in row["messages"]]
    assert roles == ["system", "user", "assistant"]
    body = json.loads(row["messages"][2]["content"])
    assert body["action"] in {"HOLD", "INSPECT", "CHANGE_METHOD", "STOP", "PROPOSE_CHANNEL"}
    assert "SPAWN" not in json.dumps(row)


def test_write_jsonl(tmp_path: Path):
    rows = build_corpus(8)
    path = write_jsonl(tmp_path / "sft.jsonl", rows)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(rows)
    parsed = json.loads(lines[0])
    assert "messages" in parsed
    assert "vector" not in parsed


def test_parse_rejects_spawn():
    try:
        parse_action_json('{"action":"SPAWN","confidence":1}')
    except InvariantError as e:
        assert e.code == "SCHEMA"
    else:
        raise AssertionError("SPAWN must not parse")


def test_live_policy_uses_injected_complete():
    def complete(_sys, _user):
        return '{"action":"HOLD","confidence":0.9,"rationale_id":"teacher"}'

    pol = LivePolicy(complete)
    m = element_at_rest("ft1", "task", "purpose", "done")
    m.attach_budget(Budget.for_pace("crawl"))
    m.picture.context_sufficient = True
    dec = pol.act(encode_board(m))
    assert dec.action == "HOLD"


def test_finetuned_head_keeps_invariants():
    pol = fine_tune_head(build_corpus(160))
    crawl = element_at_rest("ft2", "task", "purpose", "done")
    crawl.attach_budget(Budget.for_pace("crawl"))
    crawl.picture.context_sufficient = True
    assert pol.act(encode_board(crawl)).action != "PROPOSE_CHANNEL"

    exists = element_at_rest("ft3", "Write summary", "Do not duplicate", "Once")
    exists.attach_budget(Budget.for_pace("run"))
    exists.picture.context_sufficient = True
    exists.world = World(existing_files=["summary.md"], existing_channels=["summary"])
    assert pol.act(encode_board(exists)).action == "HOLD"
