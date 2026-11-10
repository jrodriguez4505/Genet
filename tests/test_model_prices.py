"""A team may mix models (TASKORG_MODEL_NAME_<SKILL>): each call records the model that answered, a trial keeps its
tokens by model, and compare prices each model's tokens at that model's rate (--price MODEL=IN/OUT)."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from taskorg.anthropic_live import AnthropicAdapter
from taskorg.budget import Budget
from taskorg.cli import _model_prices, main
from taskorg.compare import _by_model, spend_cap, trial_cost
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


class Client:
    class messages:
        @staticmethod
        def create(**payload):
            claim = "PASS. Fine." if '"function": "verifier"' in payload["messages"][0]["content"] else "ANSWER: 1"
            return NS(content=[NS(type="text", text=json.dumps({"claim": claim}))], stop_reason="end_turn",
                      usage=NS(input_tokens=1_000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0))


def test_each_call_records_the_model_that_answered(tmp_path: Path):
    adapter = AnthropicAdapter("k", "haiku", models={"verify": "sonnet"}, client=Client())
    run = new_run("r", goal="g", purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    e = Engine(MemoryStore(tmp_path / "s"), adapter=adapter, budget=Budget(max_calls=10))
    e._arm(run)
    product = e._act(run, e._brief(run, "lead", extra="WORK.", mode="work"))
    run.accept_artifact(product)
    e._verify(run, product, adapt=False)
    assert [(c["function"], c["model"]) for c in run.calls] == [("lead", "haiku"), ("verifier", "sonnet")]
    assert _by_model(run.calls) == {"haiku": [1_000, 100, 0, 0], "sonnet": [1_000, 100, 0, 0]}


def test_each_models_tokens_cost_its_own_rate():
    r = NS(prompt_tokens=3_000, completion_tokens=300, cache_write_tokens=0, cache_read_tokens=0,
           by_model={"haiku": [1_000, 100, 0, 0], "sonnet": [1_000, 100, 0, 0]})
    prices = {"haiku": (0.10, 0.50), "sonnet": (2.0, 10.0)}
    # The third 1,000 and 100 no call named a model for: at the run's own price.
    expected = (1_000 * 0.10 + 100 * 0.50 + 1_000 * 2 + 100 * 10 + 1_000 * 4 + 100 * 20) / 1e6
    assert trial_cost(r, 4.0, 20.0, prices) == pytest.approx(expected)
    # With no prices, one rate for all, as before.
    assert trial_cost(r, 0.10, 0.50) == pytest.approx((3_000 * 0.10 + 300 * 0.50) / 1e6)


def test_the_spend_cap_counts_each_model_at_its_rate():
    r = NS(prompt_tokens=1_000_000, completion_tokens=0, cache_write_tokens=0, cache_read_tokens=0,
           by_model={"sonnet": [1_000_000, 0, 0, 0]})
    assert "spend cap" in spend_cap(1.0, 0.10, 0.50, {"sonnet": (2.0, 10.0)})([r])  # $2 of Sonnet, past $1
    assert spend_cap(1.0, 0.10, 0.50)([r]) == ""  # priced as Haiku it would look like $0.10


@pytest.mark.parametrize("bad", ["sonnet", "sonnet=2", "sonnet=a/b", "=2/10", "sonnet=-1/10", "sonnet=nan/1"])
def test_a_price_must_name_a_model_and_two_rates(bad):
    with pytest.raises(InvariantError, match="--price"):
        _model_prices([bad])
    assert _model_prices(["claude-sonnet-5-5=2/10", "claude-haiku-5-5=0.1/0.5"]) == {
        "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.1, 0.5)}


def test_compare_takes_prices_with_a_default_rate_and_records_them(tmp_path: Path, capsys):
    out = tmp_path / "o.json"
    base = ["compare", "--per-family", "1", "--families", "lookup", "--strategies", "single", "--out", str(out)]
    assert main(base + ["--price", "sim=1/2"]) != 0 and "--price-in" in capsys.readouterr().out
    assert main(base + ["--price", "sim=1/2", "--price-in", "0.1", "--price-out", "0.5", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["prices"] == {"sim": [1.0, 2.0]}
