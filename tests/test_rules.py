from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from allocflow.accounting.book import Book
from allocflow.domain.types import AccountState, BuyIntent, PendingIntent, TransferIntent
from allocflow.execution.model import CashExecution
from allocflow.policies.context import make_context
from allocflow.policies.invest import evaluate_invest
from allocflow.policies.registry import evaluate_cap


def dip_context(plan, market, balance):
    book = Book(plan, market, AccountState())
    book.change_cash("stock_dip", Decimal(balance))
    rule = next(r for r in plan.rules if r.id == "dip_buy")
    ctx = make_context(book, date(2021, 2, 26), rule.id)
    ctx = replace(ctx, histories={**ctx.histories, "VOO": (Decimal(100), Decimal(70))})
    return rule, ctx


def test_highest_tier_two_assets_and_non_tech_only(plan, flat_market):
    rule, ctx = dip_context(plan, flat_market, 2000)
    decision = evaluate_invest(rule, ctx)
    assert sum(i.maximum_cash for i in decision.intents) == 800
    assert len(decision.intents) == 2
    assert {i.instrument for i in decision.intents} <= {"VOO", "VTV", "VO", "VB", "VXUS"}
    assert "highest_tier=0.3" in decision.explanation


def test_minimum_and_monthly_rearm(plan, flat_market):
    rule, small = dip_context(plan, flat_market, 1000)
    assert not evaluate_invest(rule, small).intents
    rule, ctx = dip_context(plan, flat_market, 2000)
    already = replace(ctx, memory={"last_month": "2021-02"})
    assert not evaluate_invest(rule, already).intents
    assert evaluate_invest(rule, replace(already, day=date(2021, 3, 31))).intents


def test_cap_is_based_on_configured_inflow(plan, flat_market):
    book = Book(plan, flat_market, AccountState())
    book.change_cash("stock_dip", Decimal(5000))
    book.state.latest_inflows["monthly"] = {"stock_dip": Decimal(250)}
    rule = next(r for r in plan.rules if r.kind == "budget_cap")
    decision = evaluate_cap(rule, make_context(book, date(2021, 2, 26), rule.id))
    assert decision.intents[0].amount == 2000


def test_context_is_read_only_and_excludes_execution_day(plan, flat_market):
    book = Book(plan, flat_market, AccountState())
    ctx = make_context(book, date(2021, 2, 26), "test")
    with pytest.raises(TypeError):
        ctx.budgets["stock_dca"] = 999
    rows = flat_market.prices["VOO"]
    flat_market.prices["VOO"] = tuple(
        replace(r, value=Decimal(1000)) if r.date >= ctx.day else r for r in rows
    )
    fresh = make_context(book, ctx.day, "test")
    assert fresh.prices["VOO"] == 100
    assert max(fresh.histories["VOO"]) == 100


def test_pending_cash_cannot_be_transferred(plan, flat_market):
    book = Book(plan, flat_market, AccountState())
    book.change_cash("stock_dca", Decimal(1000))
    book.state.pending.append(
        PendingIntent(
            date(2021, 1, 4),
            date(2021, 1, 5),
            BuyIntent("x", "stock_dca", "VOO", Decimal(900), "reserved"),
        )
    )
    assert not CashExecution().execute(
        book,
        TransferIntent("x", "stock_dca", "stock_dip", Decimal(200), "attempt"),
        date(2021, 1, 4),
    )
    book.assert_invariants()
