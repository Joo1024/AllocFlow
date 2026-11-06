from datetime import date

import numpy as np
import pandas as pd

from allocflow.adapters.calendar import next_session, sessions
from allocflow.adapters.dataset import save_dataset
from allocflow.config.common import Currency, Fraction, Number, Positive, Spec


class DemoSpec(Spec):
    schema_version: str
    start: date
    end: date
    base_currency: Currency
    seed: int
    initial_price: Positive
    initial_fx: dict[Currency, Positive]
    annual_return: Number
    annual_volatility: Positive
    fx_annual_volatility: Positive
    periods_per_year: Positive
    common_factor_loading: Fraction
    shock_date: date
    shock_fraction: Number


def create_demo_dataset(plan, spec: DemoSpec, output):
    """Generate visibly synthetic fixtures, never pretend these are historical quotes."""
    if spec.end < spec.start or spec.shock_fraction <= -1:
        raise ValueError("invalid synthetic dataset interval/shock")
    rng = np.random.default_rng(spec.seed)
    days = sorted({d for i in plan.instruments for d in sessions(i.calendar, spec.start, spec.end)})
    common = dict(zip(days, rng.standard_normal(len(days)), strict=True))
    prices = []
    for instrument in plan.instruments:
        value = float(spec.initial_price)
        for day in sessions(instrument.calendar, spec.start, spec.end):
            loading = float(spec.common_factor_loading)
            periods = float(spec.periods_per_year)
            innovation = loading * common[day] + np.sqrt(1 - loading**2) * rng.standard_normal()
            value *= np.exp(
                float(spec.annual_return) / periods
                + float(spec.annual_volatility) / np.sqrt(periods) * innovation
            )
            if day == spec.shock_date:
                value *= 1 + float(spec.shock_fraction)
            available = (
                next_session(instrument.calendar, day, 1)
                if instrument.pricing == "available_nav"
                else day
            )
            prices.append(
                dict(
                    instrument=instrument.id,
                    date=day,
                    available_on=available,
                    value=f"{value:.10f}",
                )
            )
    currencies = {
        plan.report_currency,
        *(i.currency for i in plan.instruments),
        *(b.currency for b in plan.budgets),
        *(f.money.currency for f in plan.cashflows),
        plan.execution.fee.fixed_currency,
    }
    rates = []
    for currency in sorted(currencies):
        if currency not in spec.initial_fx:
            raise ValueError(f"demo spec missing initial FX for {currency}")
        value = float(spec.initial_fx[currency])
        for day in days:
            if currency != spec.base_currency:
                value *= np.exp(
                    float(spec.fx_annual_volatility)
                    / np.sqrt(float(spec.periods_per_year))
                    * rng.standard_normal()
                )
            else:
                value = 1.0
            rates.append(dict(currency=currency, date=day, available_on=day, value=f"{value:.14f}"))
    save_dataset(
        output,
        pd.DataFrame(prices),
        pd.DataFrame(rates),
        dict(
            schema_version="1",
            base_currency=spec.base_currency,
            source="SYNTHETIC_DEMO_NOT_MARKET_HISTORY",
            availability_basis="synthetic daily close; mutual-fund NAV published next own-market session",
            generated_from=spec.model_dump(mode="json"),
            instruments={i.id: i.price_mode for i in plan.instruments},
        ),
    )
