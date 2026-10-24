from __future__ import annotations

from pathlib import Path

from .errors import InvariantError
from .memory_store import MemoryStore
from .run import Run


CAP = 4000


def attach_reads(store: MemoryStore, run: Run, paths: list[str], *, cap: int = CAP) -> list[str]:
    """Operator pointed at files. Text goes in working memory. Not a new Worker."""
    loaded = []
    for raw in paths or []:
        path = Path(raw)
        if not path.is_file():
            raise InvariantError("READ", f"missing file: {path}")
        with path.open(encoding="utf-8", errors="replace") as fh:
            text = fh.read(cap)  # only what is kept, however large the file
        loaded.append({"path": str(path.resolve()), "chars": len(text), "text": text})
    if loaded:
        store.remember_working(run.id, "reads", loaded)
    return [x["path"] for x in loaded]
