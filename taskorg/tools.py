"""Sandboxed tools a specialist may ask for.

A model asks by putting requests in its artifact: "read:<path>",
"retrieve:<query>", "observe" or "observe:<subdir>". The kernel checks the
slot's allowlist first (Run.assert_tools), then runs the tool here and
hands the result back in the next brief. Every round is a budgeted call.

Tools only read. They see the workspace roots the operator declared and the
files the operator attached with --read. Nothing outside them, nothing hidden
(no dot-file or dot-directory below a root, such as .env or .git), no symlink
escapes. Requests come from model output, so every tool is bounded in what it
reads and returns.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

RUNNABLE = ("read", "retrieve", "observe")
# "search" is accepted as a spelling of retrieve.
ALIASES = {"search": "retrieve"}

READ_CAP = 4000          # chars returned by one read
MATCH_CAP = 20           # lines returned by one retrieve
LIST_CAP = 50            # paths returned by one observe
WALK_CAP = 2000          # files visited per walk
VISIT_CAP = 20_000       # directory entries looked at per walk, so a huge tree cannot exhaust memory or time
FILE_BYTES_CAP = 1_000_000
SCAN_CHARS_CAP = 20_000_000  # text one retrieve scans
NOTE_CAP = 2000          # chars of a sub-task note searched for file names
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
_FILE_NAME = re.compile(r"[\w.-]+\.\w+")


def _skipped(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


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
        """An attached file, or a path inside a root with no hidden part below that root."""
        if path in self.files:
            return True
        return any(
            path == root or (path.is_relative_to(root) and not any(p.startswith(".") for p in path.relative_to(root).parts))
            for root in self.roots
        )

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
        """Files under the roots (or start), in path order, without hidden or tool directories.

        Directory symlinks are not followed. At most VISIT_CAP entries are looked at
        and WALK_CAP files yielded, however large the tree.
        """
        seen = 0
        starts = [start] if start else self.roots
        for top in starts:
            if top.is_file():
                yield top
                continue
            found: list[Path] = []
            visited = 0
            for dirpath, dirnames, filenames in os.walk(top):
                dirnames[:] = sorted(d for d in dirnames if not _skipped(d))
                found.extend(Path(dirpath) / f for f in filenames if not _skipped(f))
                visited += len(dirnames) + len(filenames)
                if visited > VISIT_CAP:
                    break
            for path in sorted(found):
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

    def material(self, channel: str, note: str = "") -> dict[str, int] | None:
        """The workspace files a sub-task covers, with estimated tokens each, or None if unknown.

        A sub-task covers the files named for its channel (file stem == channel id)
        and any file it names in its note. Files are keyed by resolved path so two
        sub-tasks that share a file can be told apart from two that do not. The
        kernel uses this to judge whether the work fits in one context; it never
        reads the text into a brief.
        """
        # Word by word, so a long run of characters cannot make the scan quadratic.
        names = {n.lower() for word in note[:NOTE_CAP].split() if len(word) <= 255 for n in _FILE_NAME.findall(word)}
        wanted = {channel.lower()} | names
        found: dict[str, int] = {}
        for path in self._walk():
            if path.stem.lower() in wanted or path.name.lower() in wanted:
                text = self._text(path)
                if text is not None:
                    found[str(path.resolve())] = len(text) // 4
        return found or None

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
        scanned, stopped = 0, ""
        for path in self._walk():
            text = self._text(path)
            if text is None:
                continue
            scanned += len(text)
            if scanned > SCAN_CHARS_CAP:
                stopped = f"\n[stopped after scanning {SCAN_CHARS_CAP // 1_000_000}M characters; narrow the query]"
                break
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
            return f"[retrieve {query}]\n" + "\n".join(full) + stopped
        if partial:
            partial.sort(key=lambda x: -x[0])
            more = "\n[more not shown]" if len(partial) > MATCH_CAP else ""
            return f"[retrieve {query}] no line has every term; closest:\n" + "\n".join(r for _, r in partial[:MATCH_CAP]) + more + stopped
        return f"[retrieve {query}] no matches" + stopped

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
