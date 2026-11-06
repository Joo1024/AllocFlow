from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from allocflow.application.service import compare_plans, run_plan
from allocflow.config.loader import load_plan
from allocflow.config.plan import PlanSpec

TEMPLATES = [
    "ordinary_dca",
    "growing_contributions",
    "drawdown_buy",
    "cashflow_underweight",
    "hierarchical_rebalance",
    "retirement_withdrawal",
]


@pytest.mark.parametrize("template", TEMPLATES)
def test_six_templates_share_one_engine(template, flat_market):
    raw = load_plan(f"examples/{template}.yaml").model_dump(mode="json")
    raw["end"] = "2021-03-31"
    result = run_plan(PlanSpec.model_validate(raw), flat_market)
    assert result.metrics["terminal_value"]["status"] == "ok"
    assert result.valuations[-1].value > 0
    previous = Decimal(0)
    for v in result.valuations:
        assert abs(sum(v.attribution.values()) - (v.value - previous - v.external_flow)) < Decimal(
            "1e-12"
        )
        previous = v.value
    assert result.manifest["engine_semantics"] == "allocflow.daily.v1"


def test_future_changes_do_not_change_earlier_fills(plan, flat_market):
    original = run_plan(plan, flat_market)
    cutoff = date(2021, 3, 1)
    for key, rows in flat_market.prices.items():
        flat_market.prices[key] = tuple(
            replace(r, value=r.value * 2) if r.date >= cutoff else r for r in rows
        )
    changed = run_plan(plan, flat_market)
    first = [e for e in original.final_state.events if e.date < cutoff]
    second = [e for e in changed.final_state.events if e.date < cutoff]
    assert first == second


def test_checkpoint_resume_matches_uninterrupted_finances(plan, flat_market):
    full = run_plan(plan, flat_market)
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-02-26"
    first = run_plan(PlanSpec.model_validate(raw), flat_market)
    raw = plan.model_dump(mode="json")
    raw["start"] = "2021-03-01"
    resumed = run_plan(PlanSpec.model_validate(raw), flat_market, initial_state=first.final_state)
    assert resumed.final_state.holdings == full.final_state.holdings
    assert resumed.final_state.budgets == full.final_state.budgets
    assert resumed.valuations[-1].value == full.valuations[-1].value
    assert first.final_state.last_date == date(2021, 2, 26)


def test_comparison_rejects_different_external_cashflows(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["cashflows"][1]["money"]["amount"] = "9999"
    with pytest.raises(ValueError, match="cashflows differ"):
        compare_plans([plan, PlanSpec.model_validate(raw)], flat_market)
