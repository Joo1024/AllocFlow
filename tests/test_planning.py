from datetime import date
from decimal import Decimal

from allocflow.application.forecast import compare_scenarios
from allocflow.application.service import run_plan
from allocflow.config.plan import PlanSpec
from allocflow.config.scenarios import ScenarioSpec


def lifecycle(plan):
    raw = plan.model_dump(mode="json")
    raw["schema_version"] = "2"
    raw["planning"] = dict(
        phases=[
            dict(
                id="saving",
                kind="accumulation",
                start="2021-01-01",
                end="2021-01-31",
                cashflows=[f.id for f in plan.cashflows],
                rules=[r.id for r in plan.rules],
            ),
            dict(
                id="retired",
                kind="retirement",
                start="2021-02-01",
                end="2023-12-31",
                cashflows=["spend"],
                rules=[],
            ),
        ],
        inflation=dict(
            annual_rate="0.10",
            base_date="2021-01-01",
            day_count="ACT/365F",
            indexed_cashflows=["spend"],
        ),
        withdrawal_bounds=dict(
            currency="USD", minimum="100", maximum="200", inflation_adjusted=False
        ),
        reserves=[
            dict(
                budget="stock_dca",
                amount="1000",
                inflation_adjusted=False,
                protect_from_withdrawals=True,
            )
        ],
        goals=[
            dict(
                id="terminal",
                date=str(plan.end),
                currency="USD",
                amount="5000",
                inflation_adjusted=True,
            )
        ],
    )
    raw["cashflows"].append(
        dict(
            id="spend",
            direction="withdrawal",
            frequency="monthly",
            start="2021-02-01",
            end=str(plan.end),
            money=dict(amount="1000", currency="USD"),
            annual_growth="0",
            paused_months=[],
            distributions=[],
        )
    )
    raw["withdrawal"] = dict(
        cash_budgets=["stock_dca"],
        sell_order=["VOO", "VXUS", "VGT"],
        proceeds_budget="stock_dca",
        shortfall="partial",
        amount_basis="fixed",
        fraction=None,
    )
    return PlanSpec.model_validate(raw)


def test_phase_bounds_reserve_and_goals_use_shared_engine(plan, flat_market):
    p = lifecycle(plan)
    result = run_plan(p, flat_market)
    events = result.final_state.events
    withdrawals = [e for e in events if e.kind == "cashflow" and e.rule == "spend"]
    assert len(withdrawals) == 2
    assert all(e.details["requested"] == 200 for e in withdrawals)
    assert all(v.budget_balances["stock_dca"] >= 1000 for v in result.valuations)
    assert not any(e.kind == "decision" and e.date >= date(2021, 2, 1) for e in events)
    assert [e.rule for e in events if e.kind == "phase"] == ["saving", "retired"]
    outcomes = result.manifest["planning_outcomes"]
    assert outcomes["real_terminal_value"] < outcomes["nominal_terminal_value"]
    assert outcomes["goals"][0]["goal"] == "terminal"
    assert outcomes["goals"][0]["target_report"] > 5000


def test_inflation_and_shortfall_not_misreported_as_compute_failure(plan, flat_market):
    p = lifecycle(plan).model_dump(mode="json")
    p["planning"]["withdrawal_bounds"] = None
    p["cashflows"][-1]["money"]["amount"] = "1000000"
    result = run_plan(PlanSpec.model_validate(p), flat_market)
    outcomes = result.manifest["planning_outcomes"]
    assert outcomes["first_shortfall_date"] == date(2021, 2, 26)
    assert outcomes["withdrawal_shortfalls"][0]["amount"] > 900000
    # Protected cash means failure to fund a withdrawal does not imply a zero account.
    assert outcomes["first_exhaustion_date"] is None


def test_paired_paths_inherit_identical_state_and_do_not_mutate(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-01-29"
    initial = run_plan(PlanSpec.model_validate(raw), flat_market).final_state
    raw["start"], raw["end"] = "2021-02-01", "2021-03-31"
    continuation = PlanSpec.model_validate(raw)
    before = dict(initial.holdings)
    spec = ScenarioSpec(
        schema_version="1",
        method="fixed_shock",
        training_start="2020-01-02",
        training_end="2020-12-31",
        paths=2,
        root_seed=7,
        block_sessions=5,
        workers=1,
        shock_date=date(2021, 3, 1),
        asset_shocks={},
        fx_shocks={},
    )
    result = compare_scenarios(
        [continuation, continuation], flat_market, spec, initial_state=initial
    )
    assert result["completed_pairs"] == 2 and result["failed_pairs"] == 0
    assert all(p["terminal_differences"] == [Decimal(0)] for p in result["paths"])
    assert initial.holdings == before and initial.last_date == date(2021, 1, 29)
