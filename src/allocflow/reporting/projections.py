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
    holdings, attribution = [], []
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
            holdings.append(dict(date=v.date, instrument=instrument, value=value))
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
        "holdings": pd.DataFrame(holdings, columns=["date", "instrument", "value"]),
        "attribution": pd.DataFrame(attribution, columns=["date", "component", "amount"]),
        "events": pd.DataFrame(
            events, columns=["sequence", "date", "kind", "rule", "status", "details"]
        ),
        "fills": pd.DataFrame(fills),
    }
