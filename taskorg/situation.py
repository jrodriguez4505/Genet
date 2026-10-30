"""The shared situation, kernel side: decision points, forecasts and abort criteria (team design part 8).

At each decision point the kernel forecasts what the rest of the run needs, from what its calls have cost
so far, checks the run's abort criteria against it, and records both. A forecast is the kernel's, never a
model's. An abort criterion is one of a fixed list that code can test. Free text cannot be tested, so it
is refused.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .errors import InvariantError

# Where the loop stops to check: after the plan is judged, after the sub-agents report, after the verdict.
DECISION_POINTS = ("plan", "reports", "verdict")
# Each criterion, and whether it takes a value.
ABORT_CRITERIA = {"forecast_short": False, "parts_failed": True}


def parse_abort(raw) -> list[str]:
    """Abort criteria from the fixed list: forecast_short, or parts_failed:N with N from 1 to 9999."""
    out: list[str] = []
    for item in raw or []:
        text = str(item).strip()
        if not text:
            continue
        name, sep, value = text.partition(":")
        takes = ABORT_CRITERIA.get(name)
        whole = value.isascii() and value.isdigit() and len(value) <= 4 and int(value) >= 1
        if not ((takes is False and not sep) or (takes is True and whole)):
            raise InvariantError("ABORT", f"abort criterion {text[:80]!r} is not one the kernel can test; "
                                          "use forecast_short or parts_failed:N")
        normal = name if takes is False else f"{name}:{int(value)}"
        if normal not in out:
            out.append(normal)
    return out


@dataclass
class Forecast:
    """What the rest of the run needs at a decision point, against what its budget has left.

    calls: one for each call the rest of the loop must make, at the least. tokens: those calls at what this
    run's calls have cost on average so far. Working calls carry files and run larger than a plan, so the
    forecast is a floor: it errs toward going on, never toward stopping a run that could finish.
    """

    at: str
    calls: int
    tokens: int
    calls_left: int | None
    tokens_left: int | None

    @property
    def short(self) -> bool:
        return (self.calls_left is not None and self.calls > self.calls_left) or (
            self.tokens_left is not None and self.tokens > self.tokens_left)

    def line(self) -> str:
        left = ("no budget set" if self.calls_left is None
                else f"{self.calls_left} calls and about {self.tokens_left:,} tokens left")
        return f"{self.at}: the rest needs at least {self.calls} calls and about {self.tokens:,} tokens; {left}"

    def as_dict(self) -> dict:
        return asdict(self) | {"short": self.short}


def forecast(run, at: str, calls: int) -> Forecast:
    used_calls, used_tokens = run.usage()
    per_call = used_tokens // used_calls if used_calls else 0
    b = run.budget
    return Forecast(
        at=at,
        calls=calls,
        tokens=calls * per_call,
        calls_left=(b.max_calls - used_calls) if b else None,
        tokens_left=(b.max_tokens - used_tokens) if b else None,
    )


def failed_parts(run) -> int:
    return sum(1 for e in run.log if e.event == "part_failed")


def met(run, fc: Forecast, criteria: list[str]) -> str | None:
    """The first criterion this decision point meets, or None."""
    for criterion in criteria:
        name, _, value = criterion.partition(":")
        if name == "forecast_short" and fc.short:
            return criterion
        if name == "parts_failed" and failed_parts(run) >= int(value):
            return criterion
    return None
