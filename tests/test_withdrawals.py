from decimal import Decimal

from allocflow.config.plan import PlanSpec
from allocflow.engine.simulation import simulate
from allocflow.execution.model import CashExecution
from allocflow.policies.base import StrategyRegistry


def withdrawal_plan(plan, shortfall, amount):
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-01-15"
    raw["rules"] = [r for r in raw["rules"] if r["schedule"] == "initial"]
    raw["cashflows"] = raw["cashflows"][:1] + [
        dict(
            id="withdraw",
            direction="withdrawal",
            frequency="once",
            start="2021-01-15",
            end="2021-01-15",
            money=dict(amount=str(amount), currency="CNY"),
            annual_growth="0",
            paused_months=[],
            distributions=[],
        )
    ]
    raw["withdrawal"] = dict(
        cash_budgets=["stock_dca"],
        sell_order=[i.id for i in plan.instruments],
        proceeds_budget="stock_dca",
        shortfall=shortfall,
    )
    return PlanSpec.model_validate(raw)


def test_rejected_withdrawal_rolls_back_liquidations(plan, flat_market):
    p = withdrawal_plan(plan, "reject", 200000)
    values, state = simulate(p, flat_market, CashExecution(), StrategyRegistry())
    baseline_raw = p.model_dump(mode="json")
    baseline_raw["cashflows"] = baseline_raw["cashflows"][:1]
    _, baseline = simulate(
        PlanSpec.model_validate(baseline_raw), flat_market, CashExecution(), StrategyRegistry()
    )
    assert state.holdings == baseline.holdings
    assert state.cash == baseline.cash
    assert state.units == baseline.units
    assert any(e.rule == "withdraw" and e.status == "rejected" for e in state.events)
    assert not any(e.rule == "withdraw" and e.kind == "trade" for e in state.events)


def test_partial_shortfall_is_an_explicit_valid_result(plan, flat_market):
    p = withdrawal_plan(plan, "partial", 200000)
    values, state = simulate(p, flat_market, CashExecution(), StrategyRegistry())
    event = next(e for e in state.events if e.rule == "withdraw" and e.kind == "cashflow")
    assert event.status == "filled"
    assert 0 < event.details["amount"] < 100000
    assert event.details["shortfall"] > 100000
    assert values[-1].value < 1


def test_legal_withdrawal_is_return_neutral_without_fees(plan, flat_market):
    p = withdrawal_plan(plan, "partial", 10000)
    raw = p.model_dump(mode="json")
    raw["execution"]["fee"]["fixed"] = "0"
    values, state = simulate(
        PlanSpec.model_validate(raw), flat_market, CashExecution(), StrategyRegistry()
    )
    assert abs(values[-1].nav - 1) < Decimal("1e-9")
    assert abs(values[-1].value - 90000) < Decimal("0.001")
