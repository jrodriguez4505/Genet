from __future__ import annotations

from pathlib import Path

from .errors import InvariantError
from .memory_store import MemoryStore
from .mission import Mission


CAP = 4000


def attach_reads(store: MemoryStore, mission: Mission, paths: list[str], *, cap: int = CAP) -> list[str]:
    """Operator pointed at files. Text goes in working memory. Not a new Worker."""
    loaded = []
    for raw in paths or []:
        path = Path(raw)
        if not path.is_file():
            raise InvariantError("READ", f"missing file: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")[:cap]
        loaded.append({"path": str(path.resolve()), "chars": len(text), "text": text})
    if loaded:
        store.remember_working(mission.id, "reads", loaded)
    return [x["path"] for x in loaded]
