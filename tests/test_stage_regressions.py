from datetime import date
from decimal import Decimal

import pytest

from allocflow.accounting.book import Book
from allocflow.application.service import run_plan
from allocflow.config.loader import parse_plan
from allocflow.config.plan import PlanSpec
from allocflow.domain.types import AccountState, BuyIntent
from allocflow.engine.scheduler import submit
from allocflow.execution.model import CashExecution


def test_pending_order_cannot_reserve_emergency_cash(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["instruments"][0]["execution_delay_sessions"] = 2
    raw["planning"] = dict(
        phases=[
            dict(
                id="all",
                kind="accumulation",
                start=str(plan.start),
                end=str(plan.end),
                cashflows=[],
                rules=[],
            )
        ],
        inflation=dict(
            annual_rate="0", base_date=str(plan.start), day_count="ACT/365F", indexed_cashflows=[]
        ),
        withdrawal_bounds=None,
        reserves=[
            dict(
                budget="stock_dca",
                amount="800",
                inflation_adjusted=False,
                protect_from_withdrawals=True,
            )
        ],
        goals=[],
    )
    p = PlanSpec.model_validate(raw)
    state = AccountState(cash={"USD": Decimal(1000)}, budgets={"stock_dca": Decimal(1000)})
    book = Book(p, flat_market, state)
    book.current_day = date(2021, 1, 4)
    intent = BuyIntent("test", "stock_dca", p.instruments[0].id, Decimal(900), "reserve_test")
    assert submit(book, CashExecution(), intent, book.current_day)
    assert state.pending[0].intent.maximum_cash == 200
    assert book.spendable("stock_dca") == 0
    assert not submit(book, CashExecution(), intent, book.current_day)


def test_snapshot_object_cannot_override_plan_staleness(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["execution"]["max_stale_days"] = 0
    p = PlanSpec.model_validate(raw)
    flat_market.prices["VOO"] = tuple(
        r for r in flat_market.prices["VOO"] if r.date != date(2021, 2, 12)
    )
    with pytest.raises(ValueError, match="preflight"):
        run_plan(p, flat_market)
    assert flat_market.max_stale_days == 10


def test_v2_schema_and_runtime_agree_about_required_extensions(plan):
    schema = PlanSpec.model_json_schema()
    assert schema["allOf"][0]["then"]["required"] == ["controls", "planning"]
    raw = plan.model_dump(mode="json")
    raw["schema_version"] = "1"
    raw["planning"] = {"irrelevant": "value"}
    with pytest.raises(ValueError, match="migration"):
        PlanSpec.model_validate(raw)
    with pytest.raises(ValueError, match="invalid YAML"):
        parse_plan("[not yaml:")


def test_v1_and_explicit_migration_preserve_financial_results(plan, flat_market):
    from allocflow.config.evolution import migrate_document

    raw = plan.model_dump(mode="json", exclude={"controls", "planning"})
    raw["schema_version"] = "1"
    legacy = run_plan(PlanSpec.model_validate(raw), flat_market)
    migrated = run_plan(
        PlanSpec.model_validate(migrate_document(raw, target_version="2")), flat_market
    )
    assert legacy.valuations == migrated.valuations
    assert legacy.final_state == migrated.final_state


def test_withdrawal_funds_protected_proceeds_floor_and_proportional_fee(plan, flat_market):
    from allocflow.accounting.flows import withdraw
    from allocflow.config.cashflows import CashflowSpec

    raw = plan.model_dump(mode="json")
    raw["execution"]["fee"]["proportional"] = "0.10"
    raw["withdrawal"] = dict(
        cash_budgets=["stock_dca"],
        sell_order=["VOO"],
        proceeds_budget="stock_dca",
        shortfall="reject",
        amount_basis="fixed",
        fraction=None,
    )
    raw["planning"] = dict(
        phases=[
            dict(
                id="all",
                kind="retirement",
                start=str(plan.start),
                end=str(plan.end),
                cashflows=[],
                rules=[],
            )
        ],
        inflation=dict(
            annual_rate="0", base_date=str(plan.start), day_count="ACT/365F", indexed_cashflows=[]
        ),
        withdrawal_bounds=None,
        reserves=[
            dict(
                budget="stock_dca",
                amount="500",
                inflation_adjusted=False,
                protect_from_withdrawals=True,
            )
        ],
        goals=[],
    )
    p = PlanSpec.model_validate(raw)
    state = AccountState(
        cash={"USD": Decimal(0)},
        budgets={"stock_dca": Decimal(0)},
        holdings={"VOO": Decimal(20)},
        units=Decimal(14000),
    )
    book = Book(p, flat_market, state)
    book.current_day = date(2021, 1, 4)
    flow = CashflowSpec(
        id="expense",
        direction="withdrawal",
        frequency="once",
        start=book.current_day,
        end=book.current_day,
        money={"amount": "100", "currency": "USD"},
        annual_growth="0",
        paused_months=[],
        distributions=[],
    )
    paid = withdraw(book, CashExecution(), flow, book.current_day)
    assert abs(paid + 700) < Decimal("1e-18")  # report currency CNY; USD/CNY=7
    assert state.budgets["stock_dca"] >= 500
    assert state.holdings["VOO"] < 14
    assert state.events[-1].details["shortfall"] == 0
    book.assert_invariants()
