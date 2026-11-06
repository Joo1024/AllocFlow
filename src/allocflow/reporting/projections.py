import json
from datetime import date, datetime
from decimal import Decimal

import pandas as pd


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def json_text(value, *, indent=None):
    return json.dumps(
        value, default=json_default, ensure_ascii=False, indent=indent, allow_nan=False
    )


def tables(result):
    values = []
    holdings, attribution, budgets, drift = [], [], [], []
    from allocflow.config.plan import PlanSpec

    plan = PlanSpec.model_validate(result.manifest["plan"])
    targets = plan.allocation.leaves()
    budget_specs = {b.id: b for b in plan.budgets}
    for v in result.valuations:
        values.append(
            dict(
                date=v.date,
                value=v.value,
                nav=v.nav,
                units=v.units,
                external_flow=v.external_flow,
                return_=v.return_,
                cash_value=v.cash_value,
            )
        )
        for instrument, value in v.holdings_value.items():
            holdings.append(
                dict(
                    date=v.date,
                    instrument=instrument,
                    value=value,
                    quantity=v.quantities.get(instrument, 0),
                )
            )
        for budget, spec in budget_specs.items():
            budgets.append(
                dict(
                    date=v.date,
                    budget=budget,
                    currency=spec.currency,
                    balance=v.budget_balances.get(budget, 0),
                    spendable=v.budget_spendable.get(budget, 0),
                    report_value=v.budget_values.get(budget, 0),
                )
            )
        for instrument, target in targets.items():
            weight = v.holdings_value.get(instrument, 0) / v.value if v.value else None
            drift.append(
                dict(
                    date=v.date,
                    instrument=instrument,
                    target=target,
                    actual_weight=weight,
                    deviation=weight - target if weight is not None else None,
                )
            )
        for component, amount in v.attribution.items():
            attribution.append(dict(date=v.date, component=component, amount=amount))
    events = [
        dict(
            sequence=e.sequence,
            date=e.date,
            kind=e.kind,
            rule=e.rule,
            status=e.status,
            details=json_text(e.details),
        )
        for e in result.final_state.events
    ]
    fills = [
        dict(sequence=e.sequence, date=e.date, rule=e.rule, **e.details)
        for e in result.final_state.events
        if e.kind == "trade" and e.status == "filled"
    ]
    return {
        "valuations": pd.DataFrame(values),
        "holdings": pd.DataFrame(holdings, columns=["date", "instrument", "value", "quantity"]),
        "budgets": pd.DataFrame(budgets),
        "drift": pd.DataFrame(drift),
        "non_trades": pd.DataFrame(
            [
                dict(
                    date=e.date,
                    rule=e.rule,
                    kind=e.kind,
                    status=e.status,
                    reason=e.details.get("reason"),
                    details=json_text(e.details),
                )
                for e in result.final_state.events
                if e.status == "rejected"
                or (e.kind == "decision" and e.details.get("intent_count") == 0)
            ]
        ),
        "attribution": pd.DataFrame(attribution, columns=["date", "component", "amount"]),
        "events": pd.DataFrame(
            events, columns=["sequence", "date", "kind", "rule", "status", "details"]
        ),
        "fills": pd.DataFrame(fills),
    }
