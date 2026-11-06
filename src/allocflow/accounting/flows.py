from copy import deepcopy
from decimal import Decimal

from allocflow.accounting.book import Book
from allocflow.adapters.calendar import next_session, sessions
from allocflow.domain.types import ZERO, SellIntent
from allocflow.execution.model import ceil_step, floor_step


def due(flow, day, monthly, calendar):
    if flow.frequency == "once":
        return day == next_session(calendar, flow.start)
    return (
        monthly
        and flow.start <= day <= flow.end
        and day.strftime("%Y-%m") not in flow.paused_months
    )


def flow_amount(flow, day):
    years = day.year - flow.start.year - ((day.month, day.day) < (flow.start.month, flow.start.day))
    return flow.money.amount * (1 + flow.annual_growth) ** max(years, 0)


def deposit(book, flow, day):
    amount = flow_amount(flow, day)
    nav = book.nav(day)
    external = amount * book.fx(flow.money.currency, day)
    if amount == 0:
        return ZERO
    before = book.value(day)[0]
    # Validate all conversions before changing any financial state.
    credits = {}
    for distribution in flow.distributions:
        currency = book.budgets[distribution.budget].currency
        spread = book.plan.execution.fx_spread if currency != flow.money.currency else ZERO
        raw = amount * distribution.weight * book.market.fx(flow.money.currency, currency, day)
        credits[distribution.budget] = floor_step(raw * (1 - spread), book.plan.execution.cash_step)
    if nav <= 0:
        raise ValueError("cannot deposit into a zero-NAV episode")
    for budget, credit in credits.items():
        book.change_cash(budget, credit)
    book.issue_units(external, nav)
    book.state.latest_inflows[flow.id] = credits
    book.state.external_flows.append((day, external))
    loss = external - (book.value(day)[0] - before)
    book.state.record(
        day,
        "cashflow",
        flow.id,
        "filled",
        direction="deposit",
        amount=amount,
        currency=flow.money.currency,
        external_report=external,
        distributions=credits,
        fx_and_rounding_report=loss,
    )
    return external


def withdraw(book, execution, flow, day):
    requested = flow_amount(flow, day)
    policy = book.plan.withdrawal
    if policy is None:
        raise ValueError("withdrawal policy missing")
    trial = deepcopy(book.state)
    work = Book(book.plan, book.market, trial)
    remaining = requested
    paid = ZERO
    costs = ZERO

    def take_cash():
        nonlocal remaining, paid, costs
        for budget_id in policy.cash_budgets:
            currency = work.budgets[budget_id].currency
            available = work.spendable(budget_id)
            if available <= 0 or remaining <= 0:
                continue
            rate = work.market.fx(currency, flow.money.currency, day)
            spread = work.plan.execution.fx_spread if currency != flow.money.currency else ZERO
            cash_needed = ceil_step(
                remaining / (rate * (1 - spread)), work.plan.execution.cash_step
            )
            debit = min(available, cash_needed)
            received = min(remaining, debit * rate * (1 - spread))
            work.change_cash(budget_id, -debit)
            paid += received
            remaining -= received
            costs += debit * work.fx(currency, day) - received * work.fx(flow.money.currency, day)

    take_cash()
    for instrument in policy.sell_order:
        if remaining <= 0:
            break
        spec = work.instruments[instrument]
        if day not in sessions(spec.calendar, day, day):
            continue
        if spec.execution_delay_sessions:
            work.state.record(
                day,
                "liquidity",
                flow.id,
                "info",
                instrument=instrument,
                reason="delayed_asset_not_available_for_same_day_withdrawal",
            )
            continue
        quantity = work.sellable(instrument)
        if quantity <= 0:
            continue
        price = work.market.price(instrument, day, visible=spec.pricing == "available_nav")
        needed_native = remaining / work.market.fx(spec.currency, flow.money.currency, day)
        # Include fees and FX spread. A conservative sale is bounded by actual holdings.
        fixed = execution.fee(work, needed_native, spec.currency, day)
        step = spec.quantity_step
        estimate = ceil_step(
            (needed_native + fixed) / price / (1 - work.plan.execution.fx_spread), step
        )
        intent = SellIntent(
            flow.id,
            policy.proceeds_budget,
            instrument,
            min(quantity, estimate),
            "withdrawal_liquidation",
        )
        execution.execute(work, intent, day)
        take_cash()
    if remaining > book.plan.execution.cash_step and policy.shortfall == "reject":
        book.state.record(
            day,
            "cashflow",
            flow.id,
            "rejected",
            reason="withdrawal_shortfall",
            requested=requested,
            shortfall=remaining,
        )
        return ZERO
    external = paid * work.fx(flow.money.currency, day)
    nav_for_flow = None
    if external > 0 and trial.units > 0:
        # Liquidation costs precede external redemption, avoiding stranded fund units.
        remaining_value = work.value(day)[0]
        nav_for_flow = (remaining_value + external) / trial.units
        work.issue_units(-external, nav_for_flow)
        if remaining_value == 0:
            trial.units = ZERO
        trial.last_nav = nav_for_flow
    trial.external_flows.append((day, -external))
    trial.record(
        day,
        "cashflow",
        flow.id,
        "filled",
        direction="withdrawal",
        requested=requested,
        amount=paid,
        shortfall=remaining,
        currency=flow.money.currency,
        external_report=-external,
        fx_and_rounding_report=costs,
        nav_for_flow=nav_for_flow,
    )
    book.state.__dict__.update(trial.__dict__)
    return -external


def accrue_interest(book, day):
    previous = book.state.last_date
    if previous is None:
        return
    days = (day - previous).days
    for budget in book.plan.budgets:
        balance = book.state.budgets.get(budget.id, ZERO)
        if not balance or not budget.annual_interest_rate:
            continue
        denominator = 365 if book.plan.execution.interest_day_count == "ACT/365F" else 360
        interest = balance * Decimal(
            str((1 + float(budget.annual_interest_rate)) ** (days / denominator) - 1)
        )
        interest = floor_step(interest, book.plan.execution.cash_step)
        book.change_cash(budget.id, interest)
        book.state.record(
            day,
            "interest",
            budget.id,
            "filled",
            amount=interest,
            currency=budget.currency,
            interest_report=interest * book.fx(budget.currency, day),
        )
