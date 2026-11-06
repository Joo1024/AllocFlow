from copy import copy, deepcopy

from allocflow.accounting.book import Book
from allocflow.accounting.flows import accrue_interest, deposit, due, withdraw
from allocflow.adapters.calendar import month_ends
from allocflow.analysis.attribution import market_contributions, reconcile
from allocflow.domain.types import ONE, ZERO, AccountState, Valuation
from allocflow.engine.scheduler import process_pending, submit, timeline
from allocflow.policies.context import make_context
from allocflow.policies.registry import evaluate_rule


def simulate(plan, market, execution, strategies, *, initial_state=None):
    state = deepcopy(initial_state) if initial_state is not None else AccountState()
    if state.last_date is not None and state.last_date >= plan.start:
        raise ValueError("resumed plan must start strictly after checkpoint date")
    book = Book(plan, market, state)
    monthly_days = month_ends(plan.decision_calendar, plan.start, plan.end)
    valuations = []
    previous_value = book.value(state.last_date)[0] if state.last_date else ZERO
    previous_nav = state.last_nav
    days = timeline(plan)
    if not days:
        raise ValueError("requested interval has no sessions")
    for day in days:
        before = copy(state)
        before.cash = dict(state.cash)
        before.holdings = dict(state.holdings)
        event_offset = len(state.events)
        contributions = market_contributions(book, before, day)
        accrue_interest(book, day)
        process_pending(book, execution, day)
        monthly = day in monthly_days
        flow_total = ZERO
        for flow in plan.cashflows:
            if due(flow, day, monthly, plan.decision_calendar):
                flow_total += (
                    deposit(book, flow, day)
                    if flow.direction == "deposit"
                    else withdraw(book, execution, flow, day)
                )
        for rule in plan.rules:
            should_run = (
                rule.schedule == "every_session"
                or (rule.schedule == "initial" and before.last_date is None)
                or (rule.schedule == "monthly" and monthly)
            )
            if not should_run:
                continue
            context = make_context(book, day, rule.id)
            decision = evaluate_rule(rule, context, strategies)
            memory = state.rule_state.setdefault(rule.id, {})
            memory.update(decision.observed_state)
            book.state.record(
                day,
                "decision",
                rule.id,
                "info",
                reason=decision.explanation,
                parameters=rule.model_dump(mode="json"),
                intent_count=len(decision.intents),
                available_budgets=dict(context.budgets),
            )
            accepted = False
            for intent in decision.intents:
                accepted = submit(book, execution, intent, day) or accepted
            if accepted:
                memory.update(decision.accepted_state)
        book.assert_invariants()
        value, holdings, cash = book.value(day)
        nav = value / state.units if state.units > 0 else None
        baseline = previous_nav if previous_nav is not None else ONE
        return_ = nav / baseline - 1 if nav is not None and baseline > 0 else None
        if nav is None:
            closing_navs = [
                e.details.get("nav_for_flow")
                for e in state.events[event_offset:]
                if e.details.get("nav_for_flow") is not None
            ]
            return_ = closing_navs[-1] / baseline - 1 if closing_navs and baseline > 0 else None
        pnl = value - previous_value - flow_total
        attribution = reconcile(contributions, state.events[event_offset:], pnl)
        valuations.append(
            Valuation(
                day, value, nav, state.units, flow_total, return_, holdings, cash, attribution
            )
        )
        state.last_date = day
        if nav is not None:
            state.last_nav = nav
        previous_value, previous_nav = value, state.last_nav
    return valuations, state
