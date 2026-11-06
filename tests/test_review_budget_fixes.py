from datetime import date
from decimal import Decimal

import pytest

from allocflow.accounting.book import Book
from allocflow.config.plan import PlanSpec
from allocflow.domain.types import AccountState, BuyIntent, PendingIntent
from allocflow.engine.scheduler import submit
from allocflow.execution.model import CashExecution
from allocflow.policies.context import make_context
from allocflow.policies.rebalance import evaluate_rebalance


def two_asset_plan(plan, *, reserve=False, zero_stock=False):
    raw = plan.model_dump(mode="json")
    raw.update(report_currency="USD", cashflows=[], controls=[], planning=None, withdrawal=None)
    raw["instruments"] = [i for i in raw["instruments"] if i["id"] in {"VOO", "BND"}]
    raw["groups"] = []
    raw["allocation"] = dict(
        id="portfolio", weight="1", instrument=None,
        children=[
            dict(id="stocks", weight="0" if zero_stock else "0.6", instrument="VOO", children=[]),
            dict(id="bonds", weight="1" if zero_stock else "0.4", instrument="BND", children=[]),
        ],
    )
    raw["budgets"] = [
        dict(id=k, currency="USD", allocation_node=node, annual_interest_rate="0")
        for k, node in [("a", "stocks"), ("b", "bonds"), ("reserve", "stocks")]
    ]
    raw["rules"] = [dict(
        id="rebalance", schedule="every_session", kind="rebalance", target_node="portfolio",
        cash_budgets=["a", "b"], proceeds_budget="a", weight_basis="budget_inclusive",
        threshold_mode="absolute", threshold="0", minimum_trade="0",
    )]
    raw["execution"]["fee"]["fixed"] = "0"
    if reserve:
        raw["planning"] = dict(
            phases=[dict(id="all", kind="accumulation", start=str(plan.start),
                         end=str(plan.end), cashflows=[], rules=["rebalance"])],
            inflation=dict(annual_rate="0", base_date=str(plan.start),
                           day_count="ACT/365F", indexed_cashflows=[]),
            withdrawal_bounds=None,
            reserves=[dict(budget="reserve", amount="200", inflation_adjusted=False,
                           protect_from_withdrawals=True)],
            goals=[],
        )
    return PlanSpec.model_validate(raw)


def execute_rebalance(plan, market, balances, holdings, pending=()):
    state = AccountState(
        cash={"USD": sum((Decimal(v) for v in balances.values()), Decimal(0))},
        budgets={k: Decimal(v) for k, v in balances.items()},
        holdings={k: Decimal(v) for k, v in holdings.items()},
        pending=list(pending),
    )
    book = Book(plan, market, state)
    book.current_day = date(2021, 1, 4)
    rule = plan.rules[0]
    ctx = make_context(book, book.current_day, rule.id)
    decision = evaluate_rebalance(rule, ctx)
    for intent in decision.intents:
        submit(book, CashExecution(), intent, book.current_day)
    book.assert_invariants()
    return state, ctx


def test_empty_proceeds_budget_falls_through_to_funded_budget(plan, flat_market):
    p = two_asset_plan(plan)
    state, _ = execute_rebalance(p, flat_market, {"a": "0", "b": "100"}, {"VOO": "6", "BND": "3"})
    assert state.holdings["BND"] == 4
    assert state.budgets["b"] == 0


@pytest.mark.parametrize("balances", [{"a": "100", "b": "100"}, {"a": "0", "b": "200"}])
def test_multiple_assets_cannot_reuse_planned_cash(plan, flat_market, balances):
    state, _ = execute_rebalance(two_asset_plan(plan), flat_market, balances, {})
    assert state.holdings == {"VOO": Decimal("1.2"), "BND": Decimal("0.8")}
    assert sum(state.budgets.values()) == 0


def test_buys_use_actual_sale_proceeds(plan, flat_market):
    state, _ = execute_rebalance(
        two_asset_plan(plan), flat_market, {"a": "0", "b": "0"}, {"VOO": "8", "BND": "2"}
    )
    assert state.holdings == {"VOO": Decimal(6), "BND": Decimal(4)}


def test_protected_cash_counts_toward_stock_target(plan, flat_market):
    state, ctx = execute_rebalance(
        two_asset_plan(plan, reserve=True), flat_market,
        {"a": "0", "b": "100", "reserve": "200"}, {"VOO": "4", "BND": "3"},
    )
    assert ctx.budget_snapshots["reserve"].balance == 200
    assert ctx.budget_snapshots["reserve"].reserve == 200
    assert ctx.budgets["reserve"] == 0
    assert state.holdings == {"VOO": Decimal(4), "BND": Decimal(4)}
    assert state.budgets["reserve"] == 200


def test_pending_cash_remains_allocated_and_cannot_be_reused(plan, flat_market):
    pending = PendingIntent(
        date(2021, 1, 4), date(2021, 1, 5),
        BuyIntent("earlier", "reserve", "VOO", Decimal(200), "pending"),
    )
    state, ctx = execute_rebalance(
        two_asset_plan(plan), flat_market,
        {"a": "0", "b": "100", "reserve": "200"}, {"VOO": "4", "BND": "3"}, [pending],
    )
    assert ctx.budget_snapshots["reserve"].pending == 200
    assert state.holdings["VOO"] == 4
    assert state.holdings["BND"] == 4
    assert state.pending == [pending]


def test_zero_weight_node_does_not_divide_by_zero(plan, flat_market):
    state, _ = execute_rebalance(
        two_asset_plan(plan, zero_stock=True), flat_market,
        {"a": "0", "b": "100", "reserve": "0"}, {},
    )
    assert state.holdings == {"BND": Decimal(1)}
