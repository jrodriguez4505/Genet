"""Two arms on the same questions, compared question by question, with their noise.

A live comparison here is small: 12 to 54 questions an arm. A difference of a few right answers can come from chance
alone, and a run that changes a brief draws every reply again. So a readout gives each difference with its noise:

- Right or wrong finishes: only the questions where the arms differ say anything. Of those, the exact two-sided sign
  test (McNemar's test, exact) gives how often a split at least that uneven comes from chance.
- Tokens a question: the mean per-question difference, with a 95% bootstrap range.

Nothing here calls a model; it reads results.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import comb
from typing import Callable, Mapping

NOISE_P = 0.05


def sign_p(gained: int, lost: int) -> float:
    """Exact two-sided sign test: questions one arm got and the other did not, each way."""
    n = gained + lost
    if n == 0:
        return 1.0
    k = min(gained, lost)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def boot_range(diffs: list[float], *, resamples: int = 10_000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap range of the mean of per-question differences. Seeded, so a readout is the same each time."""
    if not diffs:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


@dataclass
class Count:
    before: int
    after: int
    gained: int  # questions the second arm has and the first does not
    lost: int
    p: float

    @property
    def noise(self) -> bool:
        return self.p >= NOISE_P


@dataclass
class Paired:
    questions: int
    right: Count
    wrong: Count
    tokens: float  # mean per-question difference, second arm less first
    tokens_range: tuple[float, float]

    @property
    def tokens_noise(self) -> bool:
        return self.tokens_range[0] <= 0 <= self.tokens_range[1]

    def lines(self, first: str, second: str) -> list[str]:
        out = [f"{second} against {first}, {self.questions} questions:"]
        for name, c in (("right", self.right), ("wrong", self.wrong)):
            out.append(f"  {name} {c.before} -> {c.after} (+{c.gained} / -{c.lost} questions; p = {c.p:.2f})"
                       + ("  within noise" if c.noise else ""))
        lo, hi = self.tokens_range
        out.append(f"  tokens a question {self.tokens:+,.0f} (95% range {lo:+,.0f} to {hi:+,.0f})"
                   + ("  within noise" if self.tokens_noise else ""))
        return out


def _count(f: Callable[[dict], bool], a: list[dict], b: list[dict]) -> Count:
    gained = sum(f(y) and not f(x) for x, y in zip(a, b))
    lost = sum(f(x) and not f(y) for x, y in zip(a, b))
    return Count(sum(map(f, a)), sum(map(f, b)), gained, lost, sign_p(gained, lost))


def paired(first: Mapping[object, dict], second: Mapping[object, dict], *, right: Callable[[dict], bool],
           wrong: Callable[[dict], bool]) -> Paired:
    """first and second: question -> result, on the same questions (questions in only one are left out)."""
    qs = [q for q in first if q in second]
    a, b = [first[q] for q in qs], [second[q] for q in qs]
    diffs = [y["tokens"] - x["tokens"] for x, y in zip(a, b)]
    return Paired(len(qs), _count(right, a, b), _count(wrong, a, b),
                  sum(diffs) / len(diffs) if diffs else 0.0, boot_range(diffs))


def judged_right(r: dict) -> bool:
    """A judged benchmark's right finish: a judge score of at least 80 in a run that finished."""
    return (r.get("judge_score") or 0) >= 80 and r["status"] == "complete"


def judged_wrong(r: dict) -> bool:
    return r["status"] == "complete" and not judged_right(r)


def exact_right(r: dict) -> bool:
    """A generated question's right finish: the exact answer, in a run that finished."""
    return bool(r.get("correct")) and r["status"] == "complete"


def exact_wrong(r: dict) -> bool:
    return r["status"] == "complete" and not r.get("correct")
