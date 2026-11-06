from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from test_rules import dip_context

from allocflow.application.checkpoints import load_checkpoint
from allocflow.application.service import compare_plans, run_plan
from allocflow.config.plan import PlanSpec
from allocflow.policies.invest import evaluate_invest
from allocflow.reporting.export import export_run


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "DIFFERENT"),
        ("price_mode", "total_return_synthetic"),
        ("calendar", "XSHG"),
        ("pricing", "available_nav"),
    ],
)
def test_checkpoint_rejects_asset_identity_changes(plan, flat_market, tmp_path, field, value):
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-01-29"
    first = run_plan(PlanSpec.model_validate(raw), flat_market)
    export_run(first, tmp_path / "run", html=False)
    raw["start"], raw["end"] = "2021-02-01", "2021-03-31"
    raw["instruments"][0][field] = value
    continuation = PlanSpec.model_validate(raw)
    with pytest.raises(ValueError, match="contract"):
        load_checkpoint(tmp_path / "run" / "checkpoint.json", continuation)


def test_sdk_state_rejects_identity_change_without_file_loader(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-01-29"
    first = run_plan(PlanSpec.model_validate(raw), flat_market)
    raw["start"], raw["end"] = "2021-02-01", "2021-03-31"
    raw["instruments"][0]["symbol"] = "DIFFERENT"
    with pytest.raises(ValueError, match="identity contract"):
        run_plan(PlanSpec.model_validate(raw), flat_market, initial_state=first.final_state)


def test_new_peak_requires_a_strictly_higher_peak(plan, flat_market):
    rule, ctx = dip_context(plan, flat_market, 2000)
    rule = rule.model_copy(
        update={
            "trigger": rule.trigger.model_copy(update={"lookback_sessions": 3, "rearm": "new_peak"})
        }
    )
    old = replace(
        ctx,
        memory={"fired_peak": "100"},
        histories={**ctx.histories, "VOO": (Decimal(80), Decimal(70), Decimal(60))},
    )
    assert not evaluate_invest(rule, old).intents
    fresh = replace(
        old, histories={**old.histories, "VOO": (Decimal(110), Decimal(80), Decimal(70))}
    )
    assert evaluate_invest(rule, fresh).intents


def test_strict_comparison_checks_phase_cashflows(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["planning"] = dict(
        phases=[
            dict(
                id="all",
                kind="accumulation",
                start=str(plan.start),
                end=str(plan.end),
                cashflows=["initial"],
                rules=[r.id for r in plan.rules],
            )
        ],
        inflation=dict(
            annual_rate="0", base_date=str(plan.start), day_count="ACT/365F", indexed_cashflows=[]
        ),
        withdrawal_bounds=None,
        reserves=[],
        goals=[],
    )
    with pytest.raises(ValueError, match="cashflows differ"):
        compare_plans([plan, PlanSpec.model_validate(raw)], flat_market)


def test_continuation_metrics_use_one_window_and_label_lifetime(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-01-29"
    first = run_plan(PlanSpec.model_validate(raw), flat_market)
    raw["start"], raw["end"], raw["rules"] = "2021-02-01", "2021-03-31", []
    result = run_plan(PlanSpec.model_validate(raw), flat_market, initial_state=first.final_state)
    assert result.metrics["net_external_flow"]["value"] == 20000
    assert result.metrics["cash_profit"]["value"] == pytest.approx(0, abs=0.001)
    assert result.metrics["since_inception"]["net_external_flow"]["value"] == 120000
    assert result.metrics["since_inception"]["cash_profit"]["value"] < 0
    assert result.metrics["scope"]["start"] == date(2021, 1, 29)
    assert result.metrics["scope"]["opening_value"] == first.valuations[-1].value


@pytest.mark.parametrize("change", ["inflation", "bounds", "fraction"])
def test_strict_comparison_checks_all_withdrawal_policies(plan, flat_market, change):
    from test_planning import lifecycle

    first = lifecycle(plan)
    raw = first.model_dump(mode="json")
    if change == "inflation":
        raw["planning"]["inflation"]["annual_rate"] = "0.20"
    elif change == "bounds":
        raw["planning"]["withdrawal_bounds"]["maximum"] = "300"
    else:
        raw["planning"]["inflation"]["indexed_cashflows"] = []
        raw["withdrawal"].update(amount_basis="portfolio_fraction", fraction="0.1")
        raw["cashflows"][-1]["money"]["amount"] = "0"
        first_raw = raw.copy()
        first_raw["withdrawal"] = {**raw["withdrawal"], "fraction": "0.2"}
        first = PlanSpec.model_validate(first_raw)
    with pytest.raises(ValueError, match="cashflows differ"):
        compare_plans([first, PlanSpec.model_validate(raw)], flat_market)


def test_strict_comparison_rejects_actual_path_dependent_cashflows(plan, flat_market):
    from test_withdrawals import withdrawal_plan

    raw = withdrawal_plan(plan, "partial", 0).model_dump(mode="json")
    raw["withdrawal"].update(amount_basis="portfolio_fraction", fraction="0.1")
    first = PlanSpec.model_validate(raw)
    raw["execution"]["fee"]["fixed"] = "0"
    second = PlanSpec.model_validate(raw)
    with pytest.raises(ValueError, match="actual cashflows differ"):
        compare_plans([first, second], flat_market)
    assert len(compare_plans([first, second], flat_market, require_same_cashflows=False)) == 2
