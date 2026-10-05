"""Every mutation in scripts/mutation_check.py still points at real code.

The mutation check is slow, so it runs on demand. This test is fast and runs with
the suite: when a refactor moves a rule, the mutation that guards it shows up here
instead of being skipped.
"""

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mutation_check", ROOT / "scripts" / "mutation_check.py")
mutation_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mutation_check)
M = mutation_check.M


def test_mutation_names_are_unique():
    dupes = [n for n, c in Counter(name for _, name, _, _ in M).items() if c > 1]
    assert not dupes


@pytest.mark.parametrize("fname, name, old, new", M, ids=[m[1] for m in M])
def test_mutation_snippet_appears_once(fname, name, old, new):
    src = (ROOT / "taskorg" / fname).read_text()
    assert src.count(old) == 1, f"{name}: snippet found {src.count(old)} times in {fname}"
    assert old != new
