"""The pages a reader meets first name the version the package has, and the review brief's links hold. On 11 November
2026 the front pages were two days behind main: the README, the website and the completed-work page still said v0.12.0
after the default split policy had changed."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_front_pages_name_the_packages_version():
    v = _version()
    assert f"v{v} kernel" in (ROOT / "README.md").read_text()
    assert f"Version {v}," in (ROOT / "docs/index.html").read_text()
    assert f"Current as of v{v} " in (ROOT / "docs/REVIEW_BRIEF.md").read_text()
    # The newest entry of the completed-work page is this version's.
    assert (ROOT / "COMPLETED.md").read_text().split("\n## ")[1].startswith(f"v{v} ")


def test_the_review_brief_is_linked_and_its_own_links_hold():
    for page in ("README.md", "ARCHITECTURE.md"):
        assert "(docs/REVIEW_BRIEF.md)" in (ROOT / page).read_text()
    assert "/docs/REVIEW_BRIEF.md" in (ROOT / "docs/index.html").read_text()
    links = re.findall(r"\]\(([^)#]+)\)", (ROOT / "docs/REVIEW_BRIEF.md").read_text())
    local = [link for link in links if not link.startswith("http")]
    assert len(local) >= 6 and all((ROOT / "docs" / link).resolve().is_file() for link in local)
