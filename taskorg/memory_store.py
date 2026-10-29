from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from . import atomic
from .errors import InvariantError

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
LESSONS = "lessons"      # guidelines/lessons.md, kept by the kernel
MAX_LESSONS = 10
_LESSON_LINE = re.compile(r"^- (.+) \(seen (\d+)x\)$")


def _safe_id(run_id: str) -> str:
    """Run ids become file names. No separators, no '..'."""
    if not _SAFE_ID.fullmatch(run_id or "") or ".." in run_id:
        raise InvariantError("STORE", f"run id must be letters, digits, '.', '_' or '-': {run_id!r}")
    return run_id


class MemoryStore:
    """File-backed working + guidelines memory. No dump into briefs."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.working = self.root / "working"
        self.guidelines = self.root / "guidelines"
        self.episodic = self.root / "episodic"
        for d in (self.working, self.guidelines, self.episodic):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write_guidelines(self, name: str, text: str) -> Path:
        path = self.guidelines / f"{name}.md"
        atomic.write_text(path, text.strip() + "\n")
        return path

    def read_guidelines(self, name: str) -> str:
        path = self.guidelines / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def lessons(self) -> list[tuple[str, int]]:
        """(lesson, times seen), most recently seen first."""
        path = self.guidelines / f"{LESSONS}.md"
        if not path.exists():
            return []
        found = (_LESSON_LINE.match(line) for line in path.read_text(encoding="utf-8").splitlines())
        return [(m.group(1), int(m.group(2))) for m in found if m]

    def add_lesson(self, lesson: str) -> None:
        """A lesson from a failed run, into the shared guidelines every brief carries.

        The kernel writes these from fixed sentences (see review.py), never from model text.
        A repeat is counted, not repeated; the most recently seen come first; at most MAX_LESSONS stay.
        """
        lesson = " ".join(str(lesson).split())[:240]
        with self._lock:
            seen = self.lessons()
            count = next((n for text, n in seen if text == lesson), 0) + 1
            seen = [(lesson, count)] + [(text, n) for text, n in seen if text != lesson]
            body = ("# Lessons from earlier runs\n\nWritten by the kernel from runs that had a failure. "
                    "Every agent reads these.\n\n" + "\n".join(f"- {t} (seen {n}x)" for t, n in seen[:MAX_LESSONS]) + "\n")
            atomic.write_text(self.guidelines / f"{LESSONS}.md", body)

    def guidelines_packet(self) -> str:
        parts = []
        for path in sorted(self.guidelines.glob("*.md")):
            parts.append(f"# {path.stem}\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(parts)

    def remember_working(self, run_id: str, key: str, value: Any) -> None:
        path = self.working / f"{_safe_id(run_id)}.json"
        with self._lock:
            data = self._facts(path)
            data[key] = value
            atomic.write_text(path, json.dumps(data, indent=2))

    @staticmethod
    def _facts(path: Path) -> dict:
        """A run's working memory. A damaged file is a clean STORE error, not a traceback."""
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, RecursionError) as e:
            raise InvariantError("STORE", f"working memory is damaged: {path}: {type(e).__name__}") from e
        if not isinstance(data, dict):
            raise InvariantError("STORE", f"working memory is damaged: {path}: not an object")
        return data

    def reset_working(self, run_id: str) -> None:
        """Start a run clean. A reused id must not inherit the last run's facts."""
        path = self.working / f"{_safe_id(run_id)}.json"
        with self._lock:
            path.unlink(missing_ok=True)

    def working_facts(self, run_id: str) -> dict:
        path = self.working / f"{_safe_id(run_id)}.json"
        with self._lock:
            return self._facts(path)

    def scoped_brief(self, run_id: str, extra: str = "", channel_id: str | None = None,
                     keep: tuple[str, ...] | None = None) -> str:
        """INV-6 / INV-12: guidelines + this run, minus sibling channel packets. keep: only these facts."""
        facts = dict(self.working_facts(run_id))
        if keep is not None:
            facts = {k: v for k, v in facts.items() if k in keep}
        if channel_id is not None:
            facts = {
                k: v
                for k, v in facts.items()
                if not str(k).startswith("channel:") or k == f"channel:{channel_id}"
            }
        packet = ["GUIDELINES", self.guidelines_packet() or "(none)"]
        packet += ["WORKING", json.dumps(facts, indent=2) if facts else "(none)"]
        if extra:
            packet += ["BRIEF", extra]
        return "\n".join(packet)

    def archive_episode(self, run_id: str, summary: dict) -> Path:
        path = self.episodic / f"{_safe_id(run_id)}.json"
        atomic.write_text(path, json.dumps(summary, indent=2))
        return path
