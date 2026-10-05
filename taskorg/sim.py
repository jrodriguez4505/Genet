"""A deterministic reader for the synthetic suite. Not a language model.

It works through the same briefs, tools and packets a real model gets and reads
the notes with patterns that match the suite's phrasing. Two uses:

- Harness validity. Under every strategy, the facts needed must reach whoever
  answers. A perfect reader that fails a task under one strategy means the
  harness, not the model, is starving that strategy.
- Structural cost. Calls and prompt size per strategy at zero spend.

Its accuracy says nothing about any real model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .adapters import TOOL_RESULTS, Brief, ModelAdapter
from .models import Artifact
from .suite import CHURN, COMPANIES, QUARTER_WORDS, REVENUE, slug

_PHRASE_Q = {w.lower(): q for q, words in QUARTER_WORDS.items() for w in words}
_Q_ALT = "|".join(sorted((re.escape(w) for ws in QUARTER_WORDS.values() for w in ws), key=len, reverse=True))
_SLUGS = sorted((slug(n) for n in COMPANIES), key=len, reverse=True)
_NAME = {slug(n): n for n in COMPANIES}
_REPORT = re.compile(r"(?<![a-z0-9-])([a-z0-9-]+) (revenue|churn) (Q[1-4]) = (\d+(?:\.\d+)?)")
_READ = re.compile(r"\[read ([^\]\n]+)\]\n")


def _pattern(template: str) -> re.Pattern:
    rx = re.escape(template)
    rx = rx.replace(re.escape("{q}"), f"(?P<q>{_Q_ALT})")
    rx = rx.replace(re.escape("{Q}"), "(?P<Q>Q[1-4])")
    rx = rx.replace(re.escape("{v}"), r"(?P<v>\d+(?:\.\d+)?)")
    return re.compile(rx, re.IGNORECASE)


_PATTERNS = [("revenue", _pattern(t)) for t in REVENUE] + [("churn", _pattern(t)) for t in CHURN]


def facts(text: str) -> dict[tuple[str, str], float]:
    """(metric, quarter) -> value, from one company's notes. Distractor phrasings never match."""
    out = {}
    for metric, rx in _PATTERNS:
        for m in rx.finditer(text):
            quarter = m.groupdict().get("Q") or _PHRASE_Q[m.group("q").lower()]
            out[(metric, quarter.upper())] = float(m.group("v"))
    return out


def find_slugs(text: str) -> list[str]:
    """Company slugs named in text, each once, in order of first mention. Longest first,
    so look-alikes stay apart."""
    found, taken = [], []
    for s in _SLUGS:
        for m in re.finditer(rf"(?<![a-z0-9-]){re.escape(s)}(?![a-z0-9-])", text.lower()):
            if not any(a < m.end() and m.start() < b for a, b in taken):
                taken.append((m.start(), m.end()))
                found.append((m.start(), s))
    return list(dict.fromkeys(s for _, s in sorted(found)))


@dataclass
class Question:
    metric: str
    quarter: str
    slugs: list[str]
    kind: str  # lookup | sum | max


def parse_question(text: str) -> Question:
    names = []
    taken: list[tuple[int, int]] = []
    for name in sorted(COMPANIES, key=len, reverse=True):
        for m in re.finditer(re.escape(name) + r"(?![A-Za-z])", text):
            if not any(a < m.end() and m.start() < b for a, b in taken):
                taken.append((m.start(), m.end()))
                names.append((m.start(), name))
    low = text.lower()
    kind = "sum" if "combined" in low else ("max" if "which had the high" in low else "lookup")
    quarter = re.search(r"FY2026 (Q[1-4])", text)
    return Question(
        metric="churn" if "churn" in low else "revenue",
        quarter=quarter.group(1) if quarter else "Q1",
        slugs=[slug(n) for _, n in sorted(names)],
        kind=kind,
    )


def _section(packet: str, start: str, end: str = TOOL_RESULTS) -> str:
    if start not in packet:
        return ""
    body = packet.split(start, 1)[1]
    return body.split(end, 1)[0] if end in body else body


def _read_results(packet: str) -> dict[str, dict]:
    """slug -> facts, from every [read ...] block in the tool results."""
    tail = packet.split(TOOL_RESULTS, 1)[1] if TOOL_RESULTS in packet else ""
    parts = _READ.split(tail)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[Path(parts[i].strip()).stem] = facts(parts[i + 1])
    return out


class SimModel(ModelAdapter):
    """Plans like each strategy's prompt asks, reads through tools, answers from what reached it."""

    name = "sim"

    def act(self, brief: Brief) -> Artifact:
        q = parse_question(brief.goal)
        packet = brief.packet
        if brief.slot_function == "verifier":
            product = _section(packet, "\nBRIEF\n", "VERIFIER RULE")
            return self._art("PASS" if "ANSWER:" in product else "FAIL: no ANSWER line")
        if brief.slot_function == "lead" and brief.mode == "plan":
            return self._art("plan", requests=self._plan(q, crew="You lead a crew" in packet))
        known = self._known(packet, q)
        if brief.slot_function == "worker":
            note = _section(packet, "\nBRIEF\n")
            targets = find_slugs(f"{brief.channel_id} {note}") or q.slugs[:1]
            return self._work(brief, q, targets, known, report_only=True)
        return self._work(brief, q, q.slugs, known, report_only=False)

    @staticmethod
    def _plan(q: Question, *, crew: bool) -> list[str]:
        if not crew:
            # Gated lead: one sub-agent per company, only when there are several.
            return [f"subtask:{s}@retrieve=keep_{s.replace('-', '_')}_figures_apart" for s in q.slugs] if len(q.slugs) > 1 else []
        if len(q.slugs) == 1:
            s = q.slugs[0]
            return [f"subtask:find@retrieve=find_the_figure_in_{s}.md", f"subtask:check@retrieve=double_check_the_figure_in_{s}.md"]
        if len(q.slugs) <= 4:
            return [f"subtask:{s}@retrieve=read_{s}.md" for s in q.slugs]
        parts = [q.slugs[i::4] for i in range(4)]
        return [f"subtask:part-{i + 1}@retrieve=read_" + "_and_".join(f"{s}.md" for s in part) for i, part in enumerate(parts)]

    @staticmethod
    def _known(packet: str, q: Question) -> dict[str, float]:
        """Figures that reached this brief: sub-agent reports in working memory, and own reads."""
        out = {}
        for s, metric, quarter, v in _REPORT.findall(packet):
            if metric == q.metric and quarter == q.quarter:
                out[s] = float(v)
        for s, f in _read_results(packet).items():
            if (q.metric, q.quarter) in f:
                out[s] = f[(q.metric, q.quarter)]
        return out

    def _work(self, brief: Brief, q: Question, targets: list[str], known: dict[str, float], *, report_only: bool) -> Artifact:
        missing = [s for s in targets if s not in known]
        if missing and "read" in (brief.tools or []) and TOOL_RESULTS not in brief.packet:
            return self._art("Reading first.", requests=[f"read:{s}.md" for s in missing])
        lines = [f"{s} {q.metric} {q.quarter} = {known[s]:.1f}" for s in targets if s in known]
        if report_only:
            return self._art("; ".join(lines) or "no figures found")
        return self._art("; ".join(lines) + f"\nANSWER: {self._answer(q, known)}")

    @staticmethod
    def _answer(q: Question, known: dict[str, float]) -> str:
        if any(s not in known for s in q.slugs):
            return "unknown"
        if q.kind == "sum":
            return f"{sum(known[s] for s in q.slugs):.1f}"
        if q.kind == "max":
            return _NAME[max(q.slugs, key=lambda s: known[s])]
        return f"{known[q.slugs[0]]:.1f}"

    @staticmethod
    def _art(claim: str, requests: list[str] | None = None) -> Artifact:
        return Artifact(claim=claim, evidence=[], uncertainty="sim", channel_id="sim", context_update="", requests=requests or [])
