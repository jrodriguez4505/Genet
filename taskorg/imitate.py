"""N2: imitate a labeled board. Tiny logistic head. No GPU."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .budget import Budget
from .factory import element_at_rest
from .gates import World
from .policy import (
    ACTIONS,
    FEATURE_NAMES,
    BoardState,
    PolicyDecision,
    StubPolicy,
    clamp,
    encode_board,
    replay_log,
)


LABELS = ("HOLD", "INSPECT", "CHANGE_METHOD", "PROPOSE_CHANNEL", "STOP")


def gold_label(state: BoardState) -> str:
    """Hard labels the classifier must hit. Roster growth is never the gold on crawl or on an existing file."""
    if state.get("status_active") < 1.0:
        return "STOP"
    if state.get("context_sufficient") < 1.0:
        return "INSPECT"
    if state.get("plan_wrong_open") >= 1.0:
        return "CHANGE_METHOD"
    if state.get("world_files") >= 1.0 or state.get("world_channels") >= 1.0:
        return "HOLD"
    if state.get("allow_split") < 1.0:
        return "HOLD"
    if state.get("remaining_calls") <= 0:
        return "STOP"
    return "HOLD"


def _mission_for(features: dict) -> BoardState:
    pace = "run" if features.get("allow_split") else ("walk" if features.get("allow_adapt") else "crawl")
    m = element_at_rest("syn", "Write a note", "Do not redo work", "Done")
    m.attach_budget(Budget.for_pace(pace))
    m.picture.context_sufficient = bool(features.get("context_sufficient"))
    if features.get("world_files") or features.get("world_channels"):
        m.world = World(
            existing_files=["notes/already.txt"] * int(features.get("world_files") or 1),
            existing_channels=["source-a"] * int(features.get("world_channels") or 1),
        )
    if features.get("plan_wrong_open"):
        m.report_plan_wrong("first method is dead")
    if features.get("status_active") == 0:
        from .models import Status

        m.status = Status.COMPLETE
    return encode_board(m)


def synthesize(n: int = 160) -> list[tuple[BoardState, str]]:
    """Cover the invariant corners, then jitter."""
    corners = [
        {"context_sufficient": 0, "allow_split": 0, "allow_adapt": 0},
        {"context_sufficient": 1, "allow_split": 0, "allow_adapt": 0},
        {"context_sufficient": 1, "allow_split": 0, "allow_adapt": 1},
        {"context_sufficient": 1, "allow_split": 1, "allow_adapt": 1},
        {"context_sufficient": 1, "allow_split": 0, "world_files": 1},
        {"context_sufficient": 1, "allow_split": 1, "world_files": 1, "world_channels": 1},
        {"context_sufficient": 1, "plan_wrong_open": 1, "allow_adapt": 1},
        {"context_sufficient": 1, "status_active": 0},
        {"context_sufficient": 1, "allow_split": 0, "world_channels": 1},
        {"context_sufficient": 0, "allow_split": 1, "world_files": 1},
    ]
    rows: list[tuple[BoardState, str]] = []
    for raw in corners:
        feats = {
            "context_sufficient": 0,
            "allow_split": 0,
            "allow_adapt": 0,
            "world_files": 0,
            "world_channels": 0,
            "plan_wrong_open": 0,
            "status_active": 1,
        }
        feats.update(raw)
        state = _mission_for(feats)
        rows.append((state, gold_label(state)))
    i = 0
    while len(rows) < n:
        base = dict(corners[i % len(corners)])
        i += 1
        base.setdefault("context_sufficient", 1)
        base.setdefault("status_active", 1)
        state = _mission_for(base)
        rows.append((state, gold_label(state)))
    return rows


def _softmax(logits: list[float]) -> list[float]:
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps) or 1.0
    return [e / s for e in exps]


def _standardize(vector: list[float], mean: list[float], std: list[float]) -> list[float]:
    out = []
    for i, v in enumerate(vector):
        s = std[i] if i < len(std) and std[i] > 1e-6 else 1.0
        m = mean[i] if i < len(mean) else 0.0
        out.append((v - m) / s)
    return out


@dataclass
class LogisticHead:
    weights: list[list[float]]
    labels: tuple[str, ...] = LABELS
    feature_names: tuple[str, ...] = FEATURE_NAMES
    mean: list[float] | None = None
    std: list[float] | None = None

    def _x(self, vector: list[float]) -> list[float]:
        if self.mean and self.std:
            return _standardize(vector, self.mean, self.std) + [1.0]
        return list(vector) + [1.0]

    def logits(self, vector: list[float]) -> list[float]:
        x = self._x(vector)
        out = []
        for k in range(len(self.labels)):
            out.append(sum(x[i] * self.weights[i][k] for i in range(len(x))))
        return out

    def predict_proba(self, vector: list[float]) -> list[float]:
        return _softmax(self.logits(vector))

    def predict(self, vector: list[float]) -> tuple[str, float]:
        probs = self.predict_proba(vector)
        idx = max(range(len(probs)), key=lambda i: probs[i])
        return self.labels[idx], probs[idx]


def _balance(rows: list[tuple[BoardState, str]]) -> list[tuple[BoardState, str]]:
    buckets: dict[str, list] = {name: [] for name in LABELS}
    for state, y in rows:
        if y in buckets:
            buckets[y].append((state, y))
    target = max((len(v) for v in buckets.values()), default=1)
    out = []
    for name, items in buckets.items():
        if not items:
            continue
        for i in range(target):
            out.append(items[i % len(items)])
    return out


def fit(rows: list[tuple[BoardState, str]], steps: int = 400, lr: float = 0.4) -> LogisticHead:
    labels = LABELS
    d = len(FEATURE_NAMES)
    k = len(labels)
    rows = _balance(rows)
    mean = [0.0] * d
    for state, _ in rows:
        for i, v in enumerate(state.vector):
            mean[i] += v
    n_all = max(1, len(rows))
    mean = [m / n_all for m in mean]
    var = [0.0] * d
    for state, _ in rows:
        for i, v in enumerate(state.vector):
            var[i] += (v - mean[i]) ** 2
    std = [(v / n_all) ** 0.5 for v in var]
    w = [[0.0 for _ in range(k)] for _ in range(d + 1)]
    index = {name: i for i, name in enumerate(labels)}
    for _ in range(steps):
        grad = [[0.0 for _ in range(k)] for _ in range(d + 1)]
        n = 0
        for state, y in rows:
            if y not in index:
                continue
            n += 1
            x = _standardize(state.vector, mean, std) + [1.0]
            logits = [sum(x[i] * w[i][c] for i in range(d + 1)) for c in range(k)]
            p = _softmax(logits)
            truth = index[y]
            for c in range(k):
                err = p[c] - (1.0 if c == truth else 0.0)
                for i in range(d + 1):
                    grad[i][c] += x[i] * err
        if not n:
            break
        for i in range(d + 1):
            for c in range(k):
                w[i][c] -= lr * (grad[i][c] / n)
    return LogisticHead(weights=w, labels=labels, mean=mean, std=std)


class ImitationPolicy:
    threshold = 0.35
    name = "imitation"

    def __init__(self, head: LogisticHead):
        self.head = head

    def act(self, state: BoardState) -> PolicyDecision:
        action, conf = self.head.predict(state.vector)
        return PolicyDecision(action, confidence=conf, rationale_id="imitation")

    @classmethod
    def train_default(cls) -> "ImitationPolicy":
        rows = synthesize(180)
        return cls(fit(rows))


def confusion(rows: list[tuple[BoardState, str]], policy) -> dict:
    labels = list(LABELS)
    matrix = {a: {b: 0 for b in labels} for a in labels}
    correct = 0
    for state, y in rows:
        pred = policy.act(state).action
        if y not in matrix:
            continue
        if pred not in matrix[y]:
            matrix[y][pred] = matrix[y].get(pred, 0)
        if pred in matrix[y]:
            matrix[y][pred] += 1
        if pred == y:
            correct += 1
    n = max(1, len(rows))
    return {"n": len(rows), "accuracy": round(correct / n, 3), "matrix": matrix}


def vs_stub(rows: list[tuple[BoardState, str]]) -> dict:
    stub = StubPolicy()
    agree = 0
    for state, _ in rows:
        if stub.act(state).action == gold_label(state):
            agree += 1
    return {"n": len(rows), "stub_vs_gold": round(agree / max(1, len(rows)), 3)}


def dump(head: LogisticHead, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "labels": list(head.labels),
        "feature_names": list(head.feature_names),
        "weights": head.weights,
        "mean": head.mean,
        "std": head.std,
    }, indent=2), encoding="utf-8")
    return path


def load(path: Path) -> LogisticHead:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return LogisticHead(
        weights=raw["weights"],
        labels=tuple(raw["labels"]),
        feature_names=tuple(raw.get("feature_names") or FEATURE_NAMES),
        mean=raw.get("mean"),
        std=raw.get("std"),
    )


def traces_from_engine(tmp: Path) -> list[dict]:
    """Run stub engine once per pace and label the log. No live key."""
    from .loop import Engine
    from .memory_store import MemoryStore

    store = MemoryStore(tmp)
    store.write_doctrine("standing", "one body first")
    out = []
    m = element_at_rest("im-crawl", "Complete the default task", "Keep purpose", "Done")
    Engine(store, budget=Budget.for_pace("crawl")).run_standing_order(
        m,
        look_update="One source. Picture is enough.",
        operator_why="Could this have been one body?",
    )
    out.extend(replay_log([{"event": e.event, "detail": e.detail} for e in m.log]))
    return out
