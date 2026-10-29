"""The concept experiments' suite options: more companies a question, more distractors, and parts already
filed. Each is off by default, and the default suite must not change: every saved run and tape depends on it.
"""

import hashlib
import json
from pathlib import Path

import pytest

from taskorg.cli import main
from taskorg.compare import CONTEXT, run_comparison, task_context
from taskorg.factory import new_run
from taskorg.loop import MAX_PROPOSALS, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.adapters import ModelAdapter
from taskorg.sim import SimModel, facts
from taskorg.suite import ALL_COMPANIES, COMPANIES, DISTRACTORS, build_suite, slug
from taskorg.tools import Toolbox

# The default suite as it stood before these options existed.
DEFAULT = {
    1: "47994a821954ad99e478d2fa52eecf1fd48ff9cccd83e1e5cd9f68a2f66d2741",
    2: "fc3b882553147fcdc13cc00b72c0f350b2a413c5daf358e965ce6ef496c83dc8",
    5: "73b5d8f77969c01c567e15ede22daa628bee07dcdd4419b409e17b68b268b348",
}


@pytest.mark.parametrize("per_family", sorted(DEFAULT))
def test_the_default_suite_is_unchanged(per_family):
    s = build_suite(seed=7, per_family=per_family)
    blob = json.dumps({"corpus": s.corpus, "tasks": [(t.id, t.family, t.question, t.answer, t.kind, t.entities)
                                                      for t in s.tasks]}, sort_keys=True)
    assert hashlib.sha256(blob.encode()).hexdigest() == DEFAULT[per_family]


def test_entities_set_the_companies_a_question_and_draw_from_the_larger_pool():
    s = build_suite(seed=7, per_family=3, entities=20)
    assert set(s.companies) == set(ALL_COMPANIES) and len(ALL_COMPANIES) > len(COMPANIES)
    for t in s.tasks:
        if t.family in ("aggregate", "breadth"):
            assert len(t.entities) == 20 and len(set(t.entities)) == 20


def test_distractors_never_read_as_the_real_figure():
    s = build_suite(seed=7, per_family=1, entities=5, distractors=8)
    for c in s.companies.values():
        doc = s.corpus[f"{slug(c.name)}.md"]
        assert sum(doc.count(t.split("{")[0]) for t in DISTRACTORS) >= 1
        found = facts(doc)
        assert all(found[("revenue", q)] == c.revenue[q] and found[("churn", q)] == c.churn[q] for q in c.revenue)


def test_filed_parts_carry_their_checked_figures():
    s = build_suite(seed=7, per_family=2, entities=6, filed=3)
    for t in s.tasks:
        if t.family in ("aggregate", "breadth"):
            q = t.question.split("FY2026 ")[1][:2]
            assert list(t.filed) == t.entities[:3]
            assert all(v == s.companies[n].revenue[q] for n, v in t.filed.items())
            ctx = task_context(t)
            assert ctx.startswith(CONTEXT) and all(f"{slug(n)} revenue {q} = {v:.1f}" in ctx for n, v in t.filed.items())
        else:
            assert not t.filed and task_context(t) == CONTEXT


@pytest.mark.parametrize("kw, text", [({"entities": 1}, "entities must be"), ({"entities": 99}, "entities must be"),
                                      ({"entities": 4, "filed": 4}, "filed must be fewer")])
def test_impossible_options_are_refused(kw, text):
    with pytest.raises(ValueError, match=text):
        build_suite(seed=7, per_family=1, **kw)


def test_the_cli_refuses_them_before_any_call(tmp_path, capsys):
    assert main(["compare", "--adapter", "sim", "--entities", "5", "--filed", "5", "--out", str(tmp_path / "o.json")]) == 1
    assert "filed must be fewer" in capsys.readouterr().out and not (tmp_path / "o.json").exists()


def test_a_perfect_reader_gets_every_scaled_task_under_every_strategy():
    """Harness validity: at 20 companies a question, past one round's reads and the worker cap, every
    strategy still gets what it needs. A strategy that fails here is starved by the harness, not the model."""
    from taskorg.compare import comparison_budget
    suite = build_suite(seed=7, per_family=1, families=("aggregate", "breadth"), entities=20, distractors=4, filed=0)
    res = run_comparison(suite, SimModel, strategies=("single", "always", "genet", "genet-stated"),
                         budget_factory=lambda: comparison_budget(40, 200_000), tool_rounds=4)
    assert all(r.correct for r in res), [(r.strategy, r.task_id, r.answer, r.code) for r in res if not r.correct]


def test_a_filed_part_gets_no_sub_agent():
    from taskorg.compare import comparison_budget
    suite = build_suite(seed=7, per_family=1, families=("aggregate",), entities=6, filed=3)
    [crew, stated] = run_comparison(suite, SimModel, strategies=("always", "genet-stated"),
                                    budget_factory=lambda: comparison_budget(40, 200_000), tool_rounds=4)
    assert crew.correct and stated.correct
    assert stated.workers == 3 and crew.workers == 4  # the crew staffs filed parts too


class Flood(ModelAdapter):
    name = "flood"

    def __init__(self):
        self.briefs = []

    def act(self, brief):
        self.briefs.append(brief)
        claim = "PASS: ANSWER: 1" if brief.slot_function == "verifier" else "ok. ANSWER: 1"
        art = Artifact(claim=claim, evidence=[], uncertainty="", channel_id="c", context_update="", requests=[])
        if brief.mode == "plan":
            art.requests = [f"subtask:part-{i}=x" for i in range(MAX_PROPOSALS + 5)]
        return art


def test_proposals_past_the_cap_are_the_leads_to_cover(tmp_path: Path):
    from taskorg.budget import Budget
    m = new_run("flood-1", "g", "p", "d")
    m.state.success_criteria = ["ANSWER:"]
    adapter = Flood()
    Engine(MemoryStore(tmp_path), adapter=adapter, isolation_required=True,
           budget=Budget(max_calls=40, max_tokens=500_000, max_tokens_per_call=40_000)).run_task(m, context="many parts")
    merge = next(b.packet for b in adapter.briefs if b.mode == "integrate")
    assert f"5 more proposed part(s) came past the cap of {MAX_PROPOSALS} and are yours to cover too." in merge
    assert sum(1 for e in m.log if e.event == "gate") == MAX_PROPOSALS  # the flood is still not judged


def test_the_contexts_file_name_example_has_no_look_alike():
    """An example from a look-alike pair primed readers to map Halvorsen Freight Labs to halvorsen-freight.md."""
    import re
    from taskorg.suite import ALL_PAIRS
    example = re.search(r"for example (\S+)\.md for ([^)]+)\)", CONTEXT)
    assert example and example.group(1) == slug(example.group(2))
    assert all(example.group(2) not in pair for pair in ALL_PAIRS)
