"""Sandboxed tools a specialist may ask for.

A model asks by putting requests in its artifact: "read:<path>",
"retrieve:<query>", "observe" or "observe:<subdir>". The kernel checks the
slot's allowlist first (Run.assert_tools), then runs the tool here and
hands the result back in the next brief. Every round is a budgeted call.

Tools only read. They see the workspace roots the operator declared and the
files the operator attached with --read. Nothing outside them, nothing hidden,
no symlink escapes.
"""

from __future__ import annotations

import re
from pathlib import Path

RUNNABLE = ("read", "retrieve", "observe")
# "search" is accepted as a spelling of retrieve.
ALIASES = {"search": "retrieve"}

READ_CAP = 4000          # chars returned by one read
MATCH_CAP = 20           # lines returned by one retrieve
LIST_CAP = 50            # paths returned by one observe
WALK_CAP = 2000          # files visited per walk
FILE_BYTES_CAP = 1_000_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def parse_request(request: str) -> tuple[str, str]:
    name, _, arg = str(request).strip().partition(":")
    name = name.strip().lower()
    return ALIASES.get(name, name), arg.strip()


def is_runnable(request: str) -> bool:
    return parse_request(request)[0] in RUNNABLE


def _snippet(line: str, low: str, terms: list[str], width: int = 300) -> str:
    """The part of a long line around its first matched term, so the figure is not cut off."""
    line = line.strip()
    if len(line) <= width:
        return line
    found = [low.strip().find(t) for t in terms if t in low]
    pos = min((p for p in found if p >= 0), default=0)
    start = max(0, pos - width // 3)
    end = min(len(line), start + width)
    return ("…" if start else "") + line[start:end] + ("…" if end < len(line) else "")


class Toolbox:
    def __init__(self, roots: list[str | Path] | None = None, files: list[str | Path] | None = None):
        self.roots = [Path(r).resolve() for r in roots or []]
        self.files = {Path(f).resolve() for f in files or []}

    # --- sandbox ---

    def _allowed(self, path: Path) -> bool:
        if path in self.files:
            return True
        return any(path == root or path.is_relative_to(root) for root in self.roots)

    def _resolve(self, raw: str) -> Path | None:
        """Relative paths are tried against each root. The resolved path must stay inside."""
        raw = raw.strip()
        if not raw:
            return None
        candidates = [Path(raw)] if Path(raw).is_absolute() else [root / raw for root in self.roots]
        candidates += [f for f in self.files if f.name == raw or str(f).endswith("/" + raw)]
        for c in candidates:
            try:
                resolved = c.resolve()
            except OSError:
                continue
            if self._allowed(resolved) and resolved.exists():
                return resolved
        return None

    def _walk(self, start: Path | None = None):
        seen = 0
        starts = [start] if start else self.roots
        for top in starts:
            if top.is_file():
                yield top
                continue
            for path in sorted(top.rglob("*")):
                if any(part in SKIP_DIRS or part.startswith(".") for part in path.relative_to(top).parts):
                    continue
                if not path.is_file() or not self._allowed(path.resolve()):
                    continue
                seen += 1
                if seen > WALK_CAP:
                    return
                yield path
        if not start:
            yield from sorted(self.files)

    @staticmethod
    def _text(path: Path) -> str | None:
        try:
            if path.stat().st_size > FILE_BYTES_CAP:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        if b"\x00" in data[:1024]:
            return None
        return data.decode("utf-8", errors="replace")

    def material(self, channel: str, note: str = "") -> int | None:
        """Estimated tokens of workspace text a sub-task covers, or None if unknown.

        A sub-task covers the files named for its channel (file stem == channel id)
        and any file it names in its note. The kernel uses this to judge whether
        the work fits in one context; it never reads the text into a brief.
        """
        wanted = {channel.lower()} | {n.lower() for n in re.findall(r"[\w.-]+\.\w+", note)}
        chars, found = 0, False
        for path in self._walk():
            if path.stem.lower() in wanted or path.name.lower() in wanted:
                text = self._text(path)
                if text is not None:
                    chars += len(text)
                    found = True
        return chars // 4 if found else None

    # --- tools ---

    def run(self, request: str) -> str:
        name, arg = parse_request(request)
        if not self.roots and not self.files:
            return f"[{name}] no workspace attached"
        if name == "read":
            return self.read(arg)
        if name == "retrieve":
            return self.retrieve(arg)
        if name == "observe":
            return self.observe(arg)
        return f"[{name}] not a runnable tool; put the result in the artifact"

    def read(self, raw: str) -> str:
        path = self._resolve(raw)
        if path is None or not path.is_file():
            return f"[read {raw}] not found in the workspace"
        text = self._text(path)
        if text is None:
            return f"[read {path}] binary or too large"
        more = f"\n[truncated at {READ_CAP} of {len(text)} chars]" if len(text) > READ_CAP else ""
        return f"[read {path}]\n{text[:READ_CAP]}{more}"

    def retrieve(self, query: str) -> str:
        """Lines that carry every term; a term also counts when it is in the file name.

        When no line carries every term, the closest lines (at least half the
        terms) come back instead, labeled as such.
        """
        terms = [t for t in query.lower().split() if t]
        if not terms:
            return "[retrieve] empty query"
        need = max(1, -(-len(terms) // 2))
        full: list[str] = []
        partial: list[tuple[int, str]] = []
        for path in self._walk():
            text = self._text(path)
            if text is None:
                continue
            in_name = {t for t in terms if t in path.name.lower()}
            for n, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                low = line.lower()
                hit = sum(1 for t in terms if t in in_name or t in low)
                row = f"{path}:{n}: {_snippet(line, low, terms)}"
                if hit == len(terms):
                    full.append(row)
                    if len(full) > MATCH_CAP:
                        return f"[retrieve {query}]\n" + "\n".join(full[:MATCH_CAP]) + "\n[more matches not shown]"
                elif len(terms) > 1 and hit >= need:
                    partial.append((hit, row))
        if full:
            return f"[retrieve {query}]\n" + "\n".join(full)
        if partial:
            partial.sort(key=lambda x: -x[0])
            more = "\n[more not shown]" if len(partial) > MATCH_CAP else ""
            return f"[retrieve {query}] no line has every term; closest:\n" + "\n".join(r for _, r in partial[:MATCH_CAP]) + more
        return f"[retrieve {query}] no matches"

    def observe(self, raw: str = "") -> str:
        start = self._resolve(raw) if raw else None
        if raw and start is None:
            return f"[observe {raw}] not found in the workspace"
        paths = []
        for path in self._walk(start):
            paths.append(str(path))
            if len(paths) >= LIST_CAP:
                paths.append("[more files not shown]")
                break
        return f"[observe {raw or 'workspace'}]\n" + ("\n".join(paths) if paths else "(empty)")
