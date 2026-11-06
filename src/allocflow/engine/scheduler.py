from dataclasses import replace

from allocflow.adapters.calendar import next_session, sessions
from allocflow.domain.types import (
    ZERO,
    BuyIntent,
    FundedBuyIntent,
    PendingIntent,
    SellIntent,
    TransferIntent,
)


def submit(book, execution, intent, day):
    if isinstance(intent, FundedBuyIntent):
        remaining = intent.maximum_report
        accepted = False
        for budget in intent.cash_budgets:
            rate = book.fx(book.budgets[budget].currency, day)
            before = book.spendable(budget)
            cap = min(before, remaining / rate)
            if cap <= 0:
                continue
            order = BuyIntent(intent.rule_id, budget, intent.instrument, cap, intent.reason)
            filled_or_pending = submit(book, execution, order, day)
            if filled_or_pending:
                committed = max(before - book.spendable(budget), ZERO)
                remaining = max(remaining - committed * rate, ZERO)
                accepted = True
            if remaining <= 0:
                break
        if remaining > 0:
            book.state.record(
                day,
                "funding",
                intent.rule_id,
                "info",
                instrument=intent.instrument,
                unfunded_report=remaining,
                reason="funding_shortfall_or_execution_rounding",
            )
        return accepted
    if isinstance(intent, TransferIntent):
        return execution.execute(book, intent, day)
    spec = book.instruments[intent.instrument]
    due = next_session(spec.calendar, day, spec.execution_delay_sessions)
    if due == day:
        return execution.execute(book, intent, day)
    if isinstance(intent, BuyIntent):
        available = book.spendable(intent.budget)
        cap = min(intent.maximum_cash, available)
        if cap <= 0:
            book.state.record(
                day, "submission", intent.rule_id, "rejected", reason="no_unreserved_budget"
            )
            return False
        intent = replace(intent, maximum_cash=cap)
    if isinstance(intent, SellIntent):
        if intent.quantity <= 0 or intent.quantity > book.sellable(intent.instrument):
            book.state.record(
                day,
                "submission",
                intent.rule_id,
                "rejected",
                reason="insufficient_unreserved_inventory",
            )
            return False
    book.state.pending.append(PendingIntent(day, due, intent))
    book.state.record(day, "submission", intent.rule_id, "pending", due=due, intent=repr(intent))
    return True


def process_pending(book, execution, day):
    due = [p for p in book.state.pending if p.due <= day]
    for pending in due:
        book.state.pending.remove(pending)
        execution.execute(book, pending.intent, day)


def timeline(plan):
    calendars = {plan.decision_calendar, *(i.calendar for i in plan.instruments)}
    return sorted({day for name in calendars for day in sessions(name, plan.start, plan.end)})
