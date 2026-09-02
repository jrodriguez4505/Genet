"""N3: sparse reward on bench-shaped boards. Illegal spawn is terminal loss."""

from __future__ import annotations

from dataclasses import dataclass

from .budget import Budget
from .factory import element_at_rest
from .gates import World
from .imitate import ImitationPolicy, LogisticHead, _softmax
from .models import Status
from .policy import BoardState, PolicyDecision, StubPolicy, apply_decision, encode_board


ILLEGAL = -5.0
OK = 1.0
COST = -0.1


def scenario(name: str):
    if name == "crawl":
        m = element_at_rest("rl-crawl", "Summarize the paragraph", "One source", "One sentence")
        m.attach_budget(Budget.for_pace("crawl"))
        m.picture.context_sufficient = True
        return m, {"allow_channel": False, "expect": "HOLD"}
    if name == "exists":
        m = element_at_rest("rl-exists", "Write the summary file", "Do not duplicate work", "File exists once")
        m.attach_budget(Budget.for_pace("run"))
        m.picture.context_sufficient = True
        m.world = World(existing_files=["summary.md"], existing_channels=["summary"])
        return m, {"allow_channel": False, "expect": "HOLD"}
    if name == "thin":
        m = element_at_rest("rl-thin", "task", "purpose", "done")
        m.attach_budget(Budget.for_pace("crawl"))
        m.picture.context_sufficient = False
        return m, {"allow_channel": False, "expect": "INSPECT"}
    if name == "dead":
        m = element_at_rest("rl-dead", "Draft an outline", "Reach the reader", "Outline fits")
        m.attach_budget(Budget.for_pace("walk"))
        m.picture.context_sufficient = True
        m.report_plan_wrong("First outline assumed experts")
        return m, {"allow_channel": False, "expect": "CHANGE_METHOD"}
    if name == "open-run":
        m = element_at_rest("rl-open", "Answer two notes", "Do not mix sources", "Integrated")
        m.attach_budget(Budget.for_pace("run"))
        m.picture.context_sufficient = True
        return m, {"allow_channel": True, "expect": "HOLD"}
    raise ValueError(name)


SCENARIOS = ("crawl", "exists", "thin", "dead", "open-run")


def reward(mission, decision: PolicyDecision, meta: dict) -> float:
    if mission.picture.worker_count() > 0:
        return ILLEGAL
    if decision.action == "PROPOSE_CHANNEL" and not meta.get("allow_channel"):
        return ILLEGAL
    expect = meta.get("expect")
    if expect and decision.action == expect:
        return OK
    if decision.action == "STOP" and mission.status != Status.ACTIVE:
        return OK
    if decision.action == "HOLD" and not meta.get("allow_channel"):
        return 0.4
    return COST


@dataclass
class Episode:
    name: str
    action: str
    reward: float
    workers: int
    illegal: bool


def step(policy, name: str) -> Episode:
    mission, meta = scenario(name)
    state = encode_board(mission)
    decision = policy.act(state)
    if decision.action == "PROPOSE_CHANNEL" and not decision.channel_id:
        decision = PolicyDecision(
            "PROPOSE_CHANNEL",
            confidence=decision.confidence,
            rationale_id=decision.rationale_id,
            channel_id="summary" if name == "exists" else "source-b",
            named_failure="open seam",
        )
    apply_decision(mission, decision)
    r = reward(mission, decision, meta)
    illegal = r <= ILLEGAL + 0.01 or mission.picture.worker_count() > 0
    return Episode(
        name=name,
        action=decision.action,
        reward=r,
        workers=mission.picture.worker_count(),
        illegal=illegal,
    )


def evaluate(policy, rounds: int = 1) -> dict:
    eps = []
    for _ in range(rounds):
        for name in SCENARIOS:
            eps.append(step(policy, name))
    n = max(1, len(eps))
    return {
        "n": n,
        "mean_reward": round(sum(e.reward for e in eps) / n, 3),
        "illegal_rate": round(sum(1 for e in eps if e.illegal) / n, 3),
        "mean_workers": round(sum(e.workers for e in eps) / n, 3),
        "by_action": {a: sum(1 for e in eps if e.action == a) for a in ("HOLD", "INSPECT", "CHANGE_METHOD", "PROPOSE_CHANNEL", "STOP")},
    }


def _policy_gradient(head: LogisticHead, state: BoardState, action: str, advantage: float, lr: float = 0.05) -> None:
    labels = list(head.labels)
    if action not in labels:
        return
    x = head._x(state.vector)
    probs = _softmax(head.logits(state.vector))
    truth = labels.index(action)
    for c, name in enumerate(labels):
        indicator = 1.0 if c == truth else 0.0
        g = (indicator - probs[c]) * advantage
        for i in range(len(x)):
            head.weights[i][c] += lr * g * x[i]


def train(episodes: int = 80) -> tuple[ImitationPolicy, dict]:
    """Start from imitation, nudge with sparse reward. Never a reason to grow Who."""
    pol = ImitationPolicy.train_default()
    for i in range(episodes):
        name = SCENARIOS[i % len(SCENARIOS)]
        mission, meta = scenario(name)
        state = encode_board(mission)
        decision = pol.act(state)
        if decision.action == "PROPOSE_CHANNEL" and not decision.channel_id:
            decision = PolicyDecision(
                "PROPOSE_CHANNEL",
                confidence=decision.confidence,
                channel_id="source-b",
                named_failure="open",
            )
        apply_decision(mission, decision)
        r = reward(mission, decision, meta)
        baseline = 0.2
        _policy_gradient(pol.head, state, decision.action, r - baseline)
    return pol, evaluate(pol, rounds=3)


def compare_to_stub() -> dict:
    learned, learned_eval = train(60)
    stub_eval = evaluate(StubPolicy(), rounds=3)
    return {
        "stub": stub_eval,
        "learned": learned_eval,
        "illegal_not_worse": learned_eval["illegal_rate"] <= stub_eval["illegal_rate"] + 1e-9,
        "workers_not_worse": learned_eval["mean_workers"] <= stub_eval["mean_workers"] + 1e-9,
    }
