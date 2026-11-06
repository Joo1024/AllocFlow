from allocflow.domain.types import ZERO


def market_contributions(book, previous_state, day):
    result = {"asset": ZERO, "fx": ZERO}
    previous = previous_state.last_date
    if previous is None:
        return result
    for instrument, quantity in previous_state.holdings.items():
        if not quantity:
            continue
        spec = book.instruments[instrument]
        visible = spec.pricing == "available_nav"
        p0 = book.market.price(instrument, previous, visible=visible)
        p1 = book.market.price(instrument, day, visible=visible)
        f0, f1 = book.fx(spec.currency, previous), book.fx(spec.currency, day)
        result["asset"] += quantity * (p1 - p0) * f1
        result["fx"] += quantity * p0 * (f1 - f0)
    for currency, amount in previous_state.cash.items():
        if amount:
            result["fx"] += amount * (book.fx(currency, day) - book.fx(currency, previous))
    return result


def reconcile(contributions, events, pnl):
    result = dict(contributions)
    result.update(interest=ZERO, fees=ZERO, fx_and_rounding=ZERO)
    for event in events:
        result["interest"] += event.details.get("interest_report", ZERO)
        result["fees"] -= event.details.get("fee_report", ZERO)
        result["fx_and_rounding"] -= event.details.get("fx_and_rounding_report", ZERO)
    residual = pnl - sum(result.values(), ZERO)
    # Decimal operations may leave tiny arithmetic residue, but unexplained P&L is a failure.
    if abs(residual) > max(abs(pnl), 1) * type(pnl)("1e-12"):
        raise ArithmeticError(f"unexplained attribution residual: {residual}")
    result["arithmetic_residual"] = residual
    return result
