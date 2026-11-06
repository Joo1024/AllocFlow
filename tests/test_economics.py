from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from allocflow.accounting.book import Book
from allocflow.accounting.flows import deposit
from allocflow.config.plan import PlanSpec
from allocflow.domain.types import ZERO, AccountState, BuyIntent, SellIntent, TransferIntent
from allocflow.engine.simulation import simulate
from allocflow.execution.model import CashExecution
from allocflow.policies.base import StrategyRegistry


def no_fees(plan):
    raw = plan.model_dump(mode="json")
    raw["execution"]["fee"]["fixed"] = "0"
    return PlanSpec.model_validate(raw)


def test_flat_market_deposits_do_not_create_returns(plan, flat_market):
    values, state = simulate(no_fees(plan), flat_market, CashExecution(), StrategyRegistry())
    assert values[-1].value == pytest.approx(Decimal(120000), abs=Decimal("0.001"))
    assert all(abs(v.nav - 1) < Decimal("1e-9") for v in values if v.nav is not None)
    assert state.budgets["stock_dip"] > 0


def test_initial_stock_budget_is_not_split(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["end"] = raw["start"]
    values, state = simulate(
        PlanSpec.model_validate(raw), flat_market, CashExecution(), StrategyRegistry()
    )
    assert state.budgets.get("stock_dip", ZERO) == 0
    fills = [e for e in state.events if e.kind == "trade" and e.status == "filled"]
    assert len(fills) == 9
    assert values[-1].value == pytest.approx(Decimal(100000 - 9 * 7), abs=Decimal("0.001"))
    stock = sum(state.holdings[i] * 100 for i in ["VGT", "VOO", "VTV", "VO", "VB", "VXUS"])
    assert stock == pytest.approx(Decimal(60000) / 7 - 6, abs=Decimal("0.001"))


@pytest.mark.parametrize(
    "model,fixed,ratio,budget",
    [
        ("fixed_plus_proportional", "1", "0", "101"),
        ("fixed_plus_proportional", "0", "0.01", "101"),
        ("max", "1", "0.01", "101"),
    ],
)
def test_independent_fee_hand_calculation(plan, flat_market, model, fixed, ratio, budget):
    raw = plan.model_dump(mode="json")
    raw["execution"]["fee"].update(model=model, fixed=fixed, proportional=ratio)
    book = Book(PlanSpec.model_validate(raw), flat_market, AccountState())
    book.change_cash("stock_dca", Decimal(budget))
    assert CashExecution().execute(
        book, BuyIntent("test", "stock_dca", "VOO", Decimal(budget), "hand"), date(2021, 1, 4)
    )
    assert book.state.holdings["VOO"] == 1
    assert book.state.budgets["stock_dca"] == 0


def test_atomic_rejection_and_budget_conservation(plan, flat_market):
    book = Book(plan, flat_market, AccountState())
    book.change_cash("stock_dca", Decimal(100))
    before = deepcopy((book.state.cash, book.state.budgets, book.state.holdings))
    executor = CashExecution()
    assert not executor.execute(
        book, SellIntent("test", "stock_dca", "VOO", Decimal(1), "oversell"), date(2021, 1, 4)
    )
    assert (book.state.cash, book.state.budgets, book.state.holdings) == before
    value = book.value(date(2021, 1, 4))[0]
    assert executor.execute(
        book,
        TransferIntent("test", "stock_dca", "stock_dip", Decimal(50), "internal"),
        date(2021, 1, 4),
    )
    assert book.value(date(2021, 1, 4))[0] == value
    book.assert_invariants()


@given(st.integers(min_value=1, max_value=10000000))
def test_budget_transfer_property(amount):
    # Independent financial identity: a same-currency transfer cannot change aggregate cash.
    from allocflow.config.loader import load_plan

    plan = load_plan("examples/user_plan.yaml")

    class NoFX:
        def fx(self, source, target, day):
            return Decimal(1)

    book = Book(plan, NoFX(), AccountState())
    book.change_cash("stock_dca", Decimal(amount))
    CashExecution().execute(
        book,
        TransferIntent("p", "stock_dca", "stock_dip", Decimal(amount) / 2, "property"),
        date(2021, 1, 4),
    )
    assert book.state.cash["USD"] == amount
    book.assert_invariants()


def test_monthly_split_before_orders(plan, flat_market):
    book = Book(plan, flat_market, AccountState())
    deposit(book, plan.cashflows[1], date(2021, 2, 26))
    expected = {
        "stock_dca": Decimal(4200) / 7,
        "stock_dip": Decimal(1800) / 7,
        "bonds": Decimal(2400) / 7,
        "cash_equiv": Decimal(1600) / 7,
    }
    for key, value in expected.items():
        assert abs(book.state.budgets[key] - value) < Decimal("0.000001")
