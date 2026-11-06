from collections import defaultdict
from datetime import date
from decimal import Decimal

import empyrical as ep
import numpy as np
import pyxirr
from scipy.optimize import brentq

from allocflow.domain.types import ZERO


def metric(value, status="ok", **metadata):
    if value is None or not np.isfinite(float(value)):
        return {"value": None, "status": "not_computable", **metadata}
    return {"value": float(value), "status": status, **metadata}


def standard_returns(valuations, frequency):
    if frequency == "daily":
        return np.array([float(v.return_) for v in valuations if v.return_ is not None])
    by_month = {}
    for v in valuations:
        if v.return_ is not None:
            key = v.date.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 1.0) * (1 + float(v.return_))
    return np.array([factor - 1 for factor in by_month.values()])


def xirr_metric(flows, end: date, terminal: Decimal, spec):
    grouped = defaultdict(lambda: ZERO)
    for day, account_flow in flows:
        grouped[day] -= account_flow
    grouped[end] += terminal
    items = sorted((d, a) for d, a in grouped.items() if a)
    if len(items) < 2 or not any(a < 0 for _, a in items) or not any(a > 0 for _, a in items):
        return metric(None, reason="insufficient_opposite_sign_cashflows")
    dates, raw = zip(*items, strict=True)
    scale = max(abs(a) for a in raw)
    amounts = [float(a / scale) for a in raw]
    denominator = 365 if spec.xirr_day_count == "ACT/365F" else 360
    day_count = pyxirr.DayCount.ACT_365F if denominator == 365 else pyxirr.DayCount.ACT_360
    years = np.array([(d - dates[0]).days / denominator for d in dates])

    def npv(rate):
        return float(np.sum(np.array(amounts) / (1 + rate) ** years))

    lower, upper = float(spec.xirr_lower), float(spec.xirr_upper)
    grid = np.expm1(np.linspace(np.log1p(lower), np.log1p(upper), spec.xirr_grid_size))
    roots = []
    for left, right in zip(grid[:-1], grid[1:], strict=True):
        a, b = npv(left), npv(right)
        root = float(left) if a == 0 else (brentq(npv, left, right) if a * b < 0 else None)
        if root is not None and not any(
            abs(root - r) < float(spec.xirr_root_tolerance) for r in roots
        ):
            roots.append(root)
    candidate = pyxirr.xirr(dates, amounts, silent=True, day_count=day_count)
    if (
        candidate is not None
        and lower <= candidate <= upper
        and abs(npv(candidate)) < float(spec.xirr_npv_tolerance)
    ):
        if not any(abs(candidate - r) < float(spec.xirr_root_tolerance) for r in roots):
            roots.append(float(candidate))
    roots.sort()
    conventional = pyxirr.is_conventional_cash_flow(amounts)
    status = (
        "multiple_roots"
        if len(roots) > 1
        else ("ok" if conventional else "nonconventional_root_search")
    )
    return metric(
        roots[0] if roots else None,
        status,
        roots=roots,
        npv_residual=abs(npv(roots[0])) if roots else None,
        search_domain=[lower, upper],
        uniqueness_proven=bool(conventional and roots),
        search_note="grid/sign-change search does not prove all roots were found",
    )


def compute_metrics(valuations, state, spec):
    if not valuations:
        raise ValueError("no valuation sessions in requested interval")
    returns = standard_returns(valuations, spec.frequency)
    daily = standard_returns(valuations, "daily")
    annualization = float(spec.periods_per_year)
    rf = (1 + float(spec.risk_free_annual)) ** (1 / annualization) - 1
    total_flow = sum((amount for _, amount in state.external_flows), ZERO)
    value = valuations[-1].value
    # Include the unit-NAV starting point so a first-period loss appears in drawdown.
    wealth = np.r_[1.0, np.cumprod(1 + daily)]
    max_dd = float(np.min(wealth / np.maximum.accumulate(wealth) - 1)) if len(daily) else None
    enough = len(returns) >= 2
    nonzero_vol = enough and np.std(returns, ddof=1) > 1e-15
    result = {
        "terminal_value": metric(value),
        "net_external_flow": metric(total_flow),
        "cash_profit": metric(value - total_flow),
        "twr": metric(np.prod(1 + daily) - 1 if len(daily) else None),
        "max_drawdown": metric(max_dd, frequency="daily"),
        "annual_volatility": metric(
            ep.annual_volatility(returns, annualization=annualization) if enough else None
        ),
        "sharpe": metric(
            ep.sharpe_ratio(returns, risk_free=rf, annualization=annualization)
            if nonzero_vol
            else None
        ),
        "xirr": xirr_metric(state.external_flows, valuations[-1].date, value, spec),
        "frequency": spec.frequency,
        "periods_per_year": annualization,
        "observations": len(returns),
        "partial_periods_included": True,
    }
    return result
