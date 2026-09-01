from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryStore:
    """File-backed working + doctrine memory. No dump into briefs."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.working = self.root / "working"
        self.doctrine = self.root / "doctrine"
        self.episodic = self.root / "episodic"
        for d in (self.working, self.doctrine, self.episodic):
            d.mkdir(parents=True, exist_ok=True)

    def write_doctrine(self, name: str, text: str) -> Path:
        path = self.doctrine / f"{name}.md"
        path.write_text(text.strip() + "\n", encoding="utf-8")
        return path

    def read_doctrine(self, name: str) -> str:
        path = self.doctrine / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def doctrine_packet(self) -> str:
        parts = []
        for path in sorted(self.doctrine.glob("*.md")):
            parts.append(f"# {path.stem}\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(parts)

    def remember_working(self, mission_id: str, key: str, value: Any) -> None:
        path = self.working / f"{mission_id}.json"
        data = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        data[key] = value
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def working_facts(self, mission_id: str) -> dict:
        path = self.working / f"{mission_id}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def scoped_brief(self, mission_id: str, extra: str = "", channel_id: str | None = None) -> str:
        """INV-6 / INV-12: doctrine + this mission, minus sibling channel packets."""
        facts = dict(self.working_facts(mission_id))
        if channel_id is not None:
            facts = {
                k: v
                for k, v in facts.items()
                if not str(k).startswith("channel:") or k == f"channel:{channel_id}"
            }
        packet = ["DOCTRINE", self.doctrine_packet() or "(none)"]
        packet += ["WORKING", json.dumps(facts, indent=2) if facts else "(none)"]
        if extra:
            packet += ["BRIEF", extra]
        return "\n".join(packet)

    def archive_episode(self, mission_id: str, summary: dict) -> Path:
        path = self.episodic / f"{mission_id}.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return path
