"""A rework that keeps its pages (--rework-keeps). The failed product's last call held what its tool rounds returned; today
the rework brief starts without it, so a single agent's rework reads the same pages again. With the switch on, the
rework brief carries what that call read, as far as one call has room with a page to spare, and its first words arm
--then-live. Off, the rework brief is byte for byte as the tapes hold it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from taskorg.adapters import TOOL_RESULTS
from taskorg.budget import Budget
from taskorg.cli import _add_run_args, _engine, main
from taskorg.compare import SingleAgent
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import GAP_ARM, KEEP_ARM, KEEP_NOTE, REWORK_ARM, REWORK_HEAD, Engine
from taskorg.memory_store import MemoryStore
from taskorg.tools import Toolbox

from test_rework_reads import FILING, Scripted, _reading, _rework, _reworks

FAILED = "FAIL. The long-term portion was not confirmed, so the product rests on an estimate."
FIRST = "Broad Street Realty, Inc.: about 234,272 in all. ANSWER: Broad Street Realty, Inc."
ANSWER = "Broad Street Realty, Inc.: Note 7 puts 212,700 due after one year. ANSWER: Broad Street Realty, Inc."


class Sized(Scripted):
    """Scripted, with a size that grows with the brief, so the per-call limit binds."""

    def estimate_tokens(self, brief):
        return len(brief.packet) // 4


def _alone(tmp_path: Path, *replies, files=None, **engine):
    """One agent's whole run: it works and reads, the verifier fails it, it reworks, and the verifier checks again."""
    ws = tmp_path / "ws"
    ws.mkdir()
    for name, text in (files or {"broad-street-realty-inc.txt": FILING}).items():
        (ws / name).write_text(text)
    adapter = Scripted(*replies)
    run = new_run("r", goal="Which company has the highest long-term borrowings?", purpose="p", done_when="ANSWER:")
    run.state.success_criteria = ["ANSWER:"]
    e = SingleAgent(MemoryStore(tmp_path / "s"), adapter=adapter, toolbox=Toolbox(roots=[ws]),
                    budget=Budget(max_calls=20, allow_adapt=True), **engine)
    try:
        result = e.run_task(run, context="The filings are in the workspace.")
        verified = result.verified
    except InvariantError as err:
        verified = err.code
    return adapter, run, verified


def test_it_is_off_by_default_and_the_rework_reads_again_as_before(tmp_path: Path):
    assert Engine(MemoryStore(tmp_path / "e")).rework_keeps is False
    adapter, run, verified = _alone(tmp_path, _reading("reading", "read:broad-street-realty-inc.txt"), FIRST, FAILED,
                                    FIRST, FAILED)
    assert verified == "VERIFY"
    (rework,) = _reworks(adapter)
    assert KEEP_ARM not in rework.packet and TOOL_RESULTS not in rework.packet and "212,700" not in rework.packet
    assert rework.packet.endswith(f"Last product: {FIRST}") or f"Last product: {FIRST}" in rework.packet
    assert not any(e.event == "rework_keeps" for e in run.log)


def test_on_the_rework_brief_carries_what_the_failed_product_read(tmp_path: Path):
    adapter, run, verified = _alone(tmp_path, _reading("reading", "read:broad-street-realty-inc.txt"), FIRST, FAILED,
                                    ANSWER, "PASS. Note 7 read.", rework_keeps=True)
    assert verified is True
    (rework,) = _reworks(adapter)
    head, kept = rework.packet.split(f"\n{TOOL_RESULTS}\n{KEEP_NOTE}\n\n", 1)
    assert REWORK_HEAD in head and f"Last product: {FIRST}" in head
    assert "212,700 falls due after one year" in kept and KEEP_ARM not in head
    # It answered from what it kept: no read in the rework, and the check had the reworked product.
    assert [e.detail["request"] for e in run.log if e.event == "tool"] == ["read:broad-street-realty-inc.txt"]
    assert adapter.briefs[-1].mode == "verify"
    (rec,) = [e.detail for e in run.log if e.event == "rework_keeps"]
    assert rec["held"] == 1 and rec["kept"] == 1 and rec["chars"] == len(kept)


def test_the_kept_note_opens_with_the_arm_and_no_other_switch_has_it():
    assert KEEP_NOTE.startswith(f"[{KEEP_ARM}.") and KEEP_ARM not in GAP_ARM and KEEP_ARM not in REWORK_ARM
    assert REWORK_ARM not in KEEP_NOTE and GAP_ARM not in KEEP_NOTE


def test_every_round_is_kept(tmp_path: Path):
    files = {"a.txt": "Alpha borrowings 10\n", "b.txt": "Beta borrowings 20\n"}
    adapter, run, verified = _alone(
        tmp_path, _reading("a", "read:a.txt"), _reading("b", "read:b.txt"), FIRST, FAILED, ANSWER, "PASS. Fine.",
        files=files, rework_keeps=True)
    (rework,) = _reworks(adapter)
    kept = rework.packet.split(KEEP_NOTE, 1)[1]
    assert "Alpha borrowings 10" in kept and "Beta borrowings 20" in kept
    assert [(e.detail["held"], e.detail["kept"]) for e in run.log if e.event == "rework_keeps"] == [(2, 2)]


def test_a_repeat_counts_once(tmp_path: Path):
    e = Engine(MemoryStore(tmp_path / "s"), adapter=Scripted(), rework_keeps=True)
    run = new_run("r", goal="g", purpose="p", done_when="d")
    e._arm(run)
    brief = e._keep_pages(run, e._brief(run, "lead", extra="REWORK.", mode="rework"), ["PAGE-ONE", "PAGE-ONE", "PAGE-TWO"])
    assert brief.packet.count("PAGE-ONE") == 1 and brief.packet.count("PAGE-TWO") == 1
    assert [(x.detail["held"], x.detail["kept"]) for x in run.log if x.event == "rework_keeps"] == [(3, 2)]


def _kept(tmp_path: Path, held: list[str], room: int, page_chars: int | None = None):
    """_keep_pages on a rework brief, with a per-call limit `room` tokens past the brief's own size."""
    adapter = Sized()
    e = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, rework_keeps=True,
               toolbox=Toolbox(roots=[tmp_path], page_chars=page_chars))
    run = new_run("r", goal="g", purpose="p", done_when="d")
    e._arm(run)
    brief = e._brief(run, "lead", extra=f"{REWORK_HEAD}Misses: none named. Last product: x", mode="rework")
    run.attach_budget(Budget(max_calls=20, max_tokens=10**7, max_tokens_per_call=adapter.estimate_tokens(brief) + room))
    out = e._keep_pages(run, brief, held)
    return adapter, run, brief, out


PAGES = ["OLDEST " + "x" * 3_993, "MIDDLE " + "y" * 3_993, "NEWEST " + "z" * 3_993]  # 1,000 tokens each by Sized's measure


def test_where_one_call_has_no_room_the_oldest_is_left_out_first(tmp_path: Path):
    adapter, run, brief, out = _kept(tmp_path, PAGES, room=2_100)
    assert "NEWEST" in out.packet and "MIDDLE" in out.packet and "OLDEST" not in out.packet
    assert adapter.estimate_tokens(out) <= run.budget.max_tokens_per_call
    assert [(x.detail["held"], x.detail["kept"]) for x in run.log if x.event == "rework_keeps"] == [(3, 2)]
    _, _, _, everything = _kept(tmp_path / "all", PAGES, room=3_100)
    assert all(p in everything.packet for p in PAGES)


def test_it_leaves_a_page_to_spare_for_what_the_verifier_named(tmp_path: Path):
    # A 4,000-character page is 1,000 tokens and its frame; with paged reads, the room keeps one page free.
    _, _, _, unpaged = _kept(tmp_path / "u", PAGES, room=3_100)
    _, _, _, paged = _kept(tmp_path / "p", PAGES, room=3_100, page_chars=4_000)
    assert "OLDEST" in unpaged.packet and "OLDEST" not in paged.packet and "NEWEST" in paged.packet


def test_where_nothing_fits_the_brief_is_as_before(tmp_path: Path):
    adapter, run, brief, out = _kept(tmp_path, PAGES, room=500)
    assert out == brief and KEEP_ARM not in out.packet
    assert [(x.detail["held"], x.detail["kept"]) for x in run.log if x.event == "rework_keeps"] == [(3, 0)]


def test_a_merge_that_read_nothing_reworks_as_before(tmp_path: Path):
    adapter, run, product, verified = _rework(tmp_path, FIRST, FAILED, FIRST, FAILED, rework_keeps=True)
    (rework,) = _reworks(adapter)
    assert KEEP_ARM not in rework.packet and not any(e.event == "rework_keeps" for e in run.log)


# --- the switch from the command line ---


def test_run_commands_take_the_switch(tmp_path: Path):
    p = argparse.ArgumentParser()
    _add_run_args(p, id="r", goal="g", purpose="p", done_when="d", context="c")
    for argv, want in ((["--workspace", str(tmp_path)], False), (["--workspace", str(tmp_path), "--rework-keeps"], True)):
        assert _engine(p.parse_args(argv), MemoryStore(tmp_path / "s")).rework_keeps is want


def test_compare_puts_the_switch_on_the_record_and_hands_it_to_every_trial(tmp_path: Path, capsys, monkeypatch):
    base = ["compare", "--dry-run", "--per-family", "1", "--families", "lookup"]
    assert main(base) == 0 and json.loads(capsys.readouterr().out)["rework_keeps"] is False
    assert main(base + ["--rework-keeps"]) == 0 and json.loads(capsys.readouterr().out)["rework_keeps"] is True
    seen = []
    first = Engine.__init__

    def spy(self, *a, **k):
        seen.append(k.get("rework_keeps"))
        first(self, *a, **k)

    monkeypatch.setattr(Engine, "__init__", spy)
    run = ["compare", "--per-family", "1", "--families", "lookup", "--strategies", "single,genet"]
    assert main(run + ["--out", str(tmp_path / "off.json")]) == 0 and seen and set(seen) == {False}
    seen.clear()
    assert main(run + ["--out", str(tmp_path / "on.json"), "--rework-keeps"]) == 0 and seen and set(seen) == {True}
