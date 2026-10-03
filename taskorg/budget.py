from __future__ import annotations

import time
from dataclasses import dataclass, field


TIERS = {
    "tight": dict(
        max_calls=4, max_tokens=4_000, max_seconds=30.0, max_tokens_per_call=1_500,
        allow_split=False, allow_adapt=False,
    ),
    "normal": dict(
        max_calls=8, max_tokens=15_000, max_seconds=60.0, max_tokens_per_call=2_500,
        allow_split=False, allow_adapt=True,
    ),
    "open": dict(
        max_calls=12, max_tokens=50_000, max_seconds=120.0, max_tokens_per_call=4_000,
        allow_split=True, allow_adapt=True,
    ),
}


@dataclass
class Budget:
    """Hard stop. Not a suggestion in a prompt."""

    max_calls: int = 12
    max_tokens: int = 50_000
    max_seconds: float = 120.0
    max_tokens_per_call: int = 4_000
    allow_split: bool = True
    allow_adapt: bool = True
    tier: str = "open"
    started_at: float = field(default_factory=time.time)

    def elapsed(self) -> float:
        return time.time() - self.started_at

    @classmethod
    def for_tier(cls, tier: str) -> "Budget":
        key = (tier or "tight").strip().lower()
        if key not in TIERS:
            raise ValueError(f"tier must be tight|normal|open, got {tier}")
        spec = dict(TIERS[key])
        spec["tier"] = key
        return cls(**spec)
