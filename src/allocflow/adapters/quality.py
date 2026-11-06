"""Preflight coverage over the execution timeline; never substitutes missing prices."""

from datetime import date, timedelta
from typing import Literal

from allocflow.config.common import Spec
from allocflow.engine.scheduler import timeline


class DataIssue(Spec):
    severity: Literal["error", "warning"]
    code: str
    reference: str
    first_date: date | None
    last_date: date | None
    count: int
    message: str


class SeriesCoverage(Spec):
    reference: str
    first_observation: date | None
    last_observation: date | None
    first_available: date | None
    observations: int
    maximum_publication_lag_days: int | None
    price_mode: str | None


class QualityReport(Spec):
    dataset_id: str
    start: date
    end: date
    valid: bool
    series: tuple[SeriesCoverage, ...]
    issues: tuple[DataIssue, ...]


def inspect_dataset(plan, market):
    issues, coverage = [], []
    days = timeline(plan)
    if not days:
        raise ValueError("requested interval has no sessions")

    def issue(severity, code, reference, dates, message):
        issues.append(
            DataIssue(
                severity=severity,
                code=code,
                reference=reference,
                first_date=min(dates) if dates else None,
                last_date=max(dates) if dates else None,
                count=len(dates),
                message=message,
            )
        )

    def check(reference, rows, getter, mode):
        coverage.append(
            SeriesCoverage(
                reference=reference,
                first_observation=min((r.date for r in rows), default=None),
                last_observation=max((r.date for r in rows), default=None),
                first_available=min((r.available_on for r in rows), default=None),
                observations=len(rows),
                maximum_publication_lag_days=max(
                    ((r.available_on - r.date).days for r in rows), default=None
                ),
                price_mode=mode,
            )
        )
        failures = []
        for day in days:
            try:
                getter(day)
            except ValueError:
                failures.append(day)
        if failures:
            issue(
                "error",
                "coverage_gap",
                reference,
                failures,
                "No usable observation within configured staleness; no proxy or backfill applied",
            )
        if rows and min(r.available_on for r in rows) >= plan.start:
            issue(
                "warning",
                "no_prestart_history",
                reference,
                [],
                "First observed date is not a certified listing date; earlier signal history is unavailable",
            )

    from allocflow.accounting.planning import active
    from allocflow.adapters.calendar import month_ends

    monthly = month_ends(plan.decision_calendar, plan.start, plan.end)
    decision_days = [
        d
        for d in days
        if any(
            active(plan, d, r.id, "rules")
            and (
                r.schedule == "every_session"
                or (r.schedule == "monthly" and d in monthly)
                or (r.schedule == "initial" and d == days[0])
            )
            for r in plan.rules
        )
    ]
    for instrument in plan.instruments:
        mode = market.metadata.get("instruments", {}).get(instrument.id)
        if mode != instrument.price_mode:
            issue(
                "error",
                "price_mode_mismatch",
                instrument.id,
                [],
                f"Plan {instrument.price_mode}, dataset {mode}",
            )
        check(
            instrument.id,
            market.prices.get(instrument.id, ()),
            lambda d, i=instrument: market.price(i.id, d, visible=i.pricing == "available_nav"),
            mode,
        )
        unavailable_signals = []
        for day in decision_days:
            try:
                market.price(instrument.id, day - timedelta(days=1), visible=True)
            except ValueError:
                unavailable_signals.append(day)
        if unavailable_signals:
            issue(
                "error",
                "signal_coverage_gap",
                instrument.id,
                unavailable_signals,
                "Decision context requires prior-day visible prices; provide earlier history or change the run interval",
            )
    currencies = {plan.report_currency, plan.execution.fee.fixed_currency}
    currencies.update(i.currency for i in plan.instruments)
    currencies.update(b.currency for b in plan.budgets)
    currencies.update(f.money.currency for f in plan.cashflows)
    if plan.planning:
        currencies.update(g.currency for g in plan.planning.goals)
        if plan.planning.withdrawal_bounds:
            currencies.add(plan.planning.withdrawal_bounds.currency)
    for currency in sorted(currencies - {market.base_currency}):
        check(
            f"FX:{currency}",
            market.rates.get(currency, ()),
            lambda d, c=currency: market.fx(c, market.base_currency, d),
            None,
        )
    if market.metadata.get("source") == "retrospective_provider_download":
        issue(
            "warning",
            "retrospective_adjustment",
            "dataset",
            [],
            "Provider-adjusted history is retrospective. Assumed publication times and cumulative NAV do not certify point-in-time or reinvested total returns",
        )
    return QualityReport(
        dataset_id=market.dataset_id,
        start=plan.start,
        end=plan.end,
        valid=not any(i.severity == "error" for i in issues),
        series=tuple(coverage),
        issues=tuple(issues),
    )
