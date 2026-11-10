"""The gap check (--gap-check): a product the verifier passed that says itself it has no figure for something, adds 0
for it or set it aside goes back once, with the kernel's reason. A reworked product that still says so stops the run.
And the tape that lets a replay go live from that point, so only what the check changes is paid for."""

import json
from pathlib import Path

import pytest

from taskorg import checks
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.compare import live_spend_cap
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import GAP_ARM, GAP_MISS, GAP_REASON, REWORK_HEAD, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.tape import Continuing, LiveSpend, Player, Recorder, request_key

# Products from the rerun of 5 November that the verifier passed and that finished wrong, cut to the sentence that
# gives them away, and what the check must quote.
GAPS = [
    ("Combined FY2026 Q1 revenue is 404.7 $M for nine of the ten companies. Halvorsen Freight has no FY2026 Q1 figure "
     "in its file, so its amount is not included. ANSWER: 404.7",
     "Halvorsen Freight has no FY2026 Q1 figure in its file, so its amount is not included."),
    ("Group sums: a 268.7 + b 198.6 + c 148.5 + d 199.8 = 815.6. Kestrel Mill Supply contributes 0 because its notes "
     "have no Q2 figure. ANSWER: 815.6",
     "Kestrel Mill Supply contributes 0 because its notes have no Q2 figure."),
    ("Orbrook had the highest FY2026 Q3 revenue at $82.2M.\nAmbergate's $87.2M is excluded because its line sits under "
     "an 'FY2025 churn' heading.\nANSWER: Orbrook",
     "Ambergate's $87.2M is excluded because its line sits under an 'FY2025 churn' heading."),
]
CLEAN = [
    "Everholt had the highest FY2026 Q4 revenue among the ten companies, at $94.5M, ahead of Orbrook at $83.9M. ANSWER: Everholt",
    "Combined FY2026 Q4 revenue for the ten named companies is $585.5M. All ten are covered once. ANSWER: 585.5",
]


@pytest.mark.parametrize("claim,said", GAPS)
def test_the_check_quotes_the_sentence_that_leaves_something_out(claim, said):
    assert checks.gap_said(claim) == said


@pytest.mark.parametrize("claim", CLEAN + ["", "ANSWER: 1"])
def test_a_product_that_leaves_nothing_out_is_not_flagged(claim):
    assert checks.gap_said(claim) == ""


def test_what_the_check_quotes_is_bounded():
    assert len(checks.gap_said("x" * 5_000 + " contributes 0 " + "y" * 5_000)) == checks.GAP_SAID_CHARS


def _art(claim):
    return Artifact(claim=claim, evidence=["e"], uncertainty="u", channel_id="", context_update="", requests=[])


class Scripted:
    """Replies in turn; keeps each brief."""

    name = "scripted"

    def __init__(self, *claims):
        self.claims, self.briefs = list(claims), []
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 10}

    def estimate_tokens(self, brief):
        return 10

    def act(self, brief):
        self.briefs.append(brief)
        return _art(self.claims.pop(0))


def _verify(tmp_path: Path, *claims, **engine):
    """A lead's product, then the verifier, a rework and a second check, as the script says."""
    from taskorg.adapters import ModelAdapter

    adapter = type("S", (Scripted, ModelAdapter), {})(*claims)
    run = new_run("r", goal="g", purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    e = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, budget=Budget(max_calls=20, allow_adapt=True), **engine)
    e._arm(run)
    product = e._act(run, e._brief(run, "lead", extra="WORK.", mode="work"))
    run.accept_artifact(product)
    try:
        product, verified = e._verify(run, product, adapt=True)
    except InvariantError as err:
        product, verified = None, err.code
    return adapter, run, product, verified


GAP, SAID = GAPS[1]


def test_it_is_off_by_default_and_a_pass_then_finishes(tmp_path: Path):
    assert Engine(MemoryStore(tmp_path / "s")).gap_check is False
    adapter, run, product, verified = _verify(tmp_path, GAP, "PASS. Fine.")
    assert verified is True and product.claim == GAP and len(adapter.briefs) == 2
    assert not any(e.event == "gap_check" for e in run.log)


def test_on_a_pass_that_leaves_something_out_goes_back_with_the_kernels_reason(tmp_path: Path):
    adapter, run, product, verified = _verify(tmp_path, GAP, "PASS. Fine.", "ANSWER: 857.4", "PASS. Fine.", gap_check=True)
    assert verified is True and product.claim == "ANSWER: 857.4"
    rework = next(b for b in adapter.briefs if b.mode == "rework")
    assert f"{REWORK_HEAD}It said: {GAP_REASON.format(said=SAID)} Misses: " in rework.packet
    assert GAP_ARM in rework.packet and GAP_MISS in rework.packet
    assert [e.detail["said"] for e in run.log if e.event == "gap_check"] == [SAID]


def test_the_kernels_reason_is_given_even_where_the_verifiers_is_not(tmp_path: Path):
    adapter, *_ = _verify(tmp_path, GAP, "PASS. Fine.", "ANSWER: 857.4", "PASS. Fine.", gap_check=True, rework_reason=False)
    assert GAP_ARM in next(b for b in adapter.briefs if b.mode == "rework").packet


def test_a_rework_that_still_leaves_something_out_stops_the_run(tmp_path: Path):
    *_, verified = _verify(tmp_path, GAP, "PASS. Fine.", GAP, "PASS. Fine.", gap_check=True)
    assert verified == "VERIFY"


def test_after_the_verifiers_own_rework_the_check_does_not_stop_the_run(tmp_path: Path):
    adapter, run, product, verified = _verify(tmp_path, "ANSWER: 1", "FAIL: wrong sum.", GAP, "PASS. Fine.", gap_check=True)
    assert verified is True and product.claim == GAP
    # The verifier's own reason went to the rework, as without the check.
    assert "It said: FAIL: wrong sum." in next(b for b in adapter.briefs if b.mode == "rework").packet


def test_a_product_that_leaves_nothing_out_is_not_sent_back(tmp_path: Path):
    adapter, run, product, verified = _verify(tmp_path, CLEAN[0], "PASS. Fine.", gap_check=True)
    assert verified is True and len(adapter.briefs) == 2


# --- a replay that goes live after the check ---


class Endpoint:
    """An adapter whose endpoint is a list: what _post sends, and the usage it reports."""

    max_reply_param = None

    def __init__(self):
        self.sent, self.last_usage = [], {}

    def _post(self, payload):
        self.sent.append(payload)
        self.last_usage = {"prompt_tokens": 1_000, "completion_tokens": 100}
        return "live reply"


def _payload(text):
    return {"system": "s", "messages": [{"role": "user", "content": text}]}


def _continuing(tmp_path: Path):
    tape = tmp_path / "t.jsonl"
    recorded = _payload("recorded request")
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m"}) + "\n" + json.dumps(
        {"key": request_key(recorded, None), "request": recorded, "reply": "recorded reply", "usage": {"prompt_tokens": 5,
         "completion_tokens": 5}, "error": None}) + "\n")
    player, spend = Player(tape), LiveSpend()
    recorder = Recorder(tmp_path / "live.jsonl", {"adapter": "anthropic", "model": "m"})
    return player, recorder, spend, recorded


def test_it_replays_until_the_check_and_goes_live_after(tmp_path: Path):
    player, recorder, spend, recorded = _continuing(tmp_path)
    tape, adapter = Continuing(player, recorder, GAP_ARM, spend), Endpoint()
    assert tape.exchange(adapter, recorded) == "recorded reply" and adapter.sent == [] and spend.calls == 0
    armed = _payload(f"{REWORK_HEAD}It said: {GAP_REASON.format(said=SAID)}")
    assert tape.exchange(adapter, armed) == "live reply" and tape.armed
    # From then on the trial is live, even for a request the tape has: its context is no longer the tape's.
    assert tape.exchange(adapter, recorded) == "live reply" and len(adapter.sent) == 2
    assert spend.calls == 2 and spend.cost(0.10, 0.50) == pytest.approx(2 * (1_000 * 0.10 + 100 * 0.50) / 1e6)
    recorder.close()
    assert len((tmp_path / "live.jsonl").read_text().splitlines()) == 3  # header and the two live exchanges


def test_a_trial_that_leaves_the_tape_for_any_other_reason_spends_nothing(tmp_path: Path):
    player, recorder, spend, _ = _continuing(tmp_path)
    tape, adapter = Continuing(player, recorder, GAP_ARM, spend), Endpoint()
    with pytest.raises(InvariantError, match="replay"):
        tape.exchange(adapter, _payload("a request the tape never saw"))
    assert adapter.sent == [] and spend.calls == 0 and not tape.armed


def test_a_cap_counts_only_what_went_to_the_model():
    spend = LiveSpend()
    stop = live_spend_cap(spend, 0.01, 0.10, 0.50)
    assert stop([]) == ""
    spend.add({"prompt_tokens": 40_000, "completion_tokens": 2_000})  # $0.005
    assert stop(["trial"]) == ""
    spend.add({"prompt_tokens": 40_000, "completion_tokens": 2_000})
    assert "past $0.01" in stop(["trial", "trial"]) or "of $0.01" in stop(["trial", "trial"])


def test_then_live_refuses_what_it_cannot_do_faithfully(tmp_path: Path, monkeypatch, capsys):
    tape = tmp_path / "t.jsonl"
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "claude-haiku-5-5", "effort": "low",
                                "compare": {}}) + "\n")
    base = ["compare", "--adapter", "anthropic", "--replay", str(tape), "--record", str(tmp_path / "l.jsonl"),
            "--then-live", "--out", str(tmp_path / "o.json"), "--per-family", "1", "--families", "lookup"]
    assert main(base) != 0 and "--gap-check" in capsys.readouterr().out
    monkeypatch.setenv("TASKORG_ANTHROPIC_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("TASKORG_MODEL_NAME", "claude-sonnet-5-5")
    monkeypatch.setenv("TASKORG_MODEL_EFFORT", "low")
    assert main(base + ["--gap-check"]) != 0 and "model and effort" in capsys.readouterr().out
    # Refused before any tape was opened for writing, or any call made.
    assert not (tmp_path / "l.jsonl").exists() and not (tmp_path / "o.json").exists()
