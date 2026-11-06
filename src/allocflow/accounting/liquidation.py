"""Size liquidation against net proceeds, FX, protected cash and both rounding steps."""

from allocflow.accounting.planning import reserve_floor
from allocflow.domain.types import ZERO
from allocflow.execution.model import ceil_step, floor_step


def liquidation_quantity(book, execution, instrument, budget, currency, remaining, day):
    spec = book.instruments[instrument]
    budget_currency = book.budgets[budget].currency
    cash_step = book.plan.execution.cash_step
    spread = book.plan.execution.fx_spread
    outgoing_spread = spread if budget_currency != currency else ZERO
    cash_needed = ceil_step(
        remaining / (book.market.fx(budget_currency, currency, day) * (1 - outgoing_spread)),
        cash_step,
    )
    protected = reserve_floor(book.plan, budget, day, purpose="withdrawal")
    required_credit = max(protected + cash_needed - book.uncommitted(budget), ZERO)
    incoming_spread = spread if spec.currency != budget_currency else ZERO
    rate = book.market.fx(spec.currency, budget_currency, day)
    price = book.market.price(instrument, day, visible=spec.pricing == "available_nav")
    step = spec.quantity_step
    maximum = int(book.sellable(instrument) // step)

    def credit(steps):
        nominal = steps * step * price
        fee = execution.fee(book, nominal, spec.currency, day)
        return floor_step((nominal - fee) * rate * (1 - incoming_spread), cash_step)

    # CashExecution's net proceeds are monotonic when fees permit positive proceeds.
    # Extension fee schedules used for liquidation must satisfy the same contract.
    if credit(maximum) < required_credit:
        return maximum * step
    lower, upper = 0, maximum
    while lower < upper:
        middle = (lower + upper) // 2
        if credit(middle) >= required_credit:
            upper = middle
        else:
            lower = middle + 1
    return lower * step
