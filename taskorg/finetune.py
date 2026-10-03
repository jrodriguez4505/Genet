"""Fine-tune the *policy head*, not Grok.

xAI does not expose a public custom-fine-tune job for Grok weights.
This module:

1. Writes an SFT JSONL a third-party trainer can consume later.
2. Fine-tunes the local logistic head on that corpus (this machine, no GPU).
3. Parses a live-model JSON action into PolicyDecision. The kernel still
   refuses roster writes.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import InvariantError
from .imitate import ImitationPolicy, fit, synthesize
from .policy import ACTIONS, BoardState, PolicyDecision, clamp


SYSTEM = (
    "You are Genet's policy head. Propose one action. "
    "Never change the roster. Never spawn. "
    "Return ONLY JSON: "
    '{"action":"HOLD|INSPECT|ACTIVATE_SKILL|CHANGE_METHOD|PROPOSE_CHANNEL|REVISE_GOAL|STOP",'
    '"confidence":0-1,"channel_id":"","named_failure":"","rationale_id":""}'
)


def board_prompt(state: BoardState) -> str:
    feats = {k: state.features.get(k) for k in (
        "worker_count", "context_sufficient", "allow_split", "allow_adapt",
        "world_files", "world_channels", "replan_open", "status_active",
        "open_reviews",
    )}
    extras = {k: state.extras.get(k) for k in ("goal", "purpose", "method", "tier", "status")}
    return json.dumps({"features": feats, "run": extras}, sort_keys=True)


def sft_row(state: BoardState, action: str) -> dict:
    if action not in ACTIONS:
        raise InvariantError("SCHEMA", f"sft label not an action: {action}")
    assistant = json.dumps({
        "action": action,
        "confidence": 1.0,
        "channel_id": "",
        "named_failure": "",
        "rationale_id": "sft-gold",
    })
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": board_prompt(state)},
            {"role": "assistant", "content": assistant},
        ],
        "label": action,
        "vector": state.vector,
    }


def build_corpus(n: int = 240) -> list[dict]:
    return [sft_row(state, label) for state, label in synthesize(n)]


def write_jsonl(path: Path, rows: list[dict] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = rows if rows is not None else build_corpus()
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            slim = {"messages": row["messages"], "label": row["label"]}
            fh.write(json.dumps(slim) + "\n")
    return path


def parse_action_json(text: str) -> PolicyDecision:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise InvariantError("SCHEMA", "policy model returned no JSON")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise InvariantError("SCHEMA", f"policy JSON invalid: {e}") from e
    if not isinstance(data, dict):
        raise InvariantError("SCHEMA", "policy JSON is not an object")
    action = str(data.get("action") or "").strip().upper()
    if action not in ACTIONS:
        raise InvariantError("SCHEMA", f"policy action illegal: {action}")
    # Missing confidence defaults to 0.5; a stated 0.0 stays 0.0 and clamps to HOLD.
    raw_conf = data.get("confidence")
    try:
        confidence = 0.5 if raw_conf is None else float(raw_conf)
    except (TypeError, ValueError) as e:
        raise InvariantError("SCHEMA", f"policy confidence not a number: {raw_conf!r}") from e
    return PolicyDecision(
        action=action,
        confidence=confidence,
        rationale_id=str(data.get("rationale_id") or "live-policy"),
        channel_id=str(data.get("channel_id") or ""),
        named_failure=str(data.get("named_failure") or ""),
        method=str(data.get("method") or ""),
        skill=str(data.get("skill") or ""),
    )


class LivePolicy:
    """Uses an LLM as proposer. Still cannot write the roster."""

    threshold = 0.35
    name = "live-policy"

    def __init__(self, complete):
        """complete(system, user) -> str. Injected so tests need no key."""
        self.complete = complete

    def act(self, state: BoardState) -> PolicyDecision:
        text = self.complete(SYSTEM, board_prompt(state))
        return clamp(parse_action_json(text), self.threshold)


def fine_tune_head(rows: list[dict] | None = None) -> ImitationPolicy:
    """Local SFT of the logistic head on the Genet corpus. No GPU."""
    rows = rows if rows is not None else build_corpus()
    pairs = []
    for row in rows:
        state = BoardState(
            features={},
            vector=list(row["vector"]),
            extras={},
        )
        pairs.append((state, row["label"]))
    # vectors-only BoardState lacks feature dict; gold already applied as label
    return ImitationPolicy(fit(pairs, steps=350, lr=0.35))
