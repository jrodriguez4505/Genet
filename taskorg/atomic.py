"""Writes that land whole or not at all."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text(path: str | Path, text: str) -> Path:
    """Write text to path atomically. A crash mid-write leaves the old file in place, never a
    truncated one: the text goes to a temporary file beside it, which then replaces it in one step.
    The temporary name starts with a dot, so a workspace walk never lists a leftover."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
