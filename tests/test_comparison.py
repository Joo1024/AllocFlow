from decimal import Decimal

from allocflow.analysis.comparison import compare_results, wealth_bridge
from allocflow.application.service import run_plan
from allocflow.config.plan import PlanSpec
from allocflow.reporting.projections import tables


def test_fee_difference_reconciles_and_explains_first_trade(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["execution"]["fee"]["fixed"] = "0"
    free = PlanSpec.model_validate(raw)
    charged, uncharged = run_plan(plan, flat_market), run_plan(free, flat_market)
    paired = compare_results(charged, uncharged)
    assert paired["actual_external_flows_equal"]
    delta = paired["wealth_bridge"]["delta"]
    assert abs(delta["closing"] - sum(v for k, v in delta.items() if k != "closing")) < Decimal(
        "1e-18"
    )
    assert delta["fees"] > 0
    assert paired["first_event_difference"] is not None
    assert not compare_results(charged, charged)["event_differences"]
    bridge = wealth_bridge(charged)
    assert abs(bridge["opening"]) < Decimal("1e-18")
    projections = tables(charged)
    assert len(projections["budgets"]) == len(charged.valuations) * len(plan.budgets)
    assert len(projections["drift"]) == len(charged.valuations) * len(plan.instruments)
    for v in charged.valuations:
        assert abs(sum(v.budget_values.values()) - v.cash_value) < Decimal("1e-18")
