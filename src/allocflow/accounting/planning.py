"""Lifecycle policies consume configuration; dates and amounts never live in the engine."""

from decimal import Decimal

from allocflow.domain.types import ONE, ZERO


def inflation_factor(planning, day):
    if planning is None:
        return ONE
    inflation = planning.inflation
    denominator = 365 if inflation.day_count == "ACT/365F" else 360
    exponent = Decimal((day - inflation.base_date).days) / Decimal(denominator)
    return (ONE + inflation.annual_rate) ** exponent


def phase_at(plan, day):
    if plan.planning is None:
        return None
    return next(p for p in plan.planning.phases if p.start <= day <= p.end)


def active(plan, day, identifier, kind):
    phase = phase_at(plan, day)
    return phase is None or identifier in getattr(phase, kind)


def indexed_amount(plan, flow, day, amount):
    if plan.planning and flow.id in plan.planning.inflation.indexed_cashflows:
        return amount * inflation_factor(plan.planning, day)
    return amount


def withdrawal_amount(book, day, currency, requested):
    planning = book.plan.planning
    if planning is None or planning.withdrawal_bounds is None:
        return requested
    bounds = planning.withdrawal_bounds
    factor = inflation_factor(planning, day) if bounds.inflation_adjusted else ONE
    rate = book.market.fx(bounds.currency, currency, day)
    return min(max(requested, bounds.minimum * factor * rate), bounds.maximum * factor * rate)


def reserve_floor(plan, budget, day, *, purpose):
    if plan.planning is None or day is None:
        return ZERO
    reserve = next((r for r in plan.planning.reserves if r.budget == budget), None)
    if reserve is None or (purpose == "withdrawal" and not reserve.protect_from_withdrawals):
        return ZERO
    return reserve.amount * (
        inflation_factor(plan.planning, day) if reserve.inflation_adjusted else ONE
    )


def record_planning(book, day, goal_days):
    plan, state = book.plan, book.state
    if plan.planning is None:
        return
    phase = phase_at(plan, day)
    previous = (
        phase_at(plan, state.last_date)
        if state.last_date and plan.planning.phases[0].start <= state.last_date
        else None
    )
    if previous is None or previous.id != phase.id:
        state.record(day, "phase", phase.id, "info", phase_kind=phase.kind, reason="phase_entered")
    for goal in plan.planning.goals:
        if goal_days.get(goal.id) != day:
            continue
        target = goal.amount * book.fx(goal.currency, day)
        if goal.inflation_adjusted:
            target *= inflation_factor(plan.planning, day)
        value = book.value(day)[0]
        state.record(
            day,
            "goal",
            goal.id,
            "info",
            target_report=target,
            value_report=value,
            gap_report=max(target - value, ZERO),
            met=value >= target,
        )
    for reserve in plan.planning.reserves:
        target = reserve_floor(plan, reserve.budget, day, purpose="investment")
        balance = state.budgets.get(reserve.budget, ZERO)
        if balance < target:
            state.record(
                day,
                "reserve",
                reserve.budget,
                "info",
                currency=book.budgets[reserve.budget].currency,
                target=target,
                balance=balance,
                gap=target - balance,
                reason="reserve_underfunded",
            )
