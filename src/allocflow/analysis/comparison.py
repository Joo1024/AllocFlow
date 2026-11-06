"""Paired differences are evidence, not a claim of per-rule causal attribution."""

from collections import defaultdict
from dataclasses import asdict

from allocflow.domain.types import ZERO
from allocflow.reporting.projections import json_text


def wealth_bridge(result):
    contributions = defaultdict(lambda: ZERO)
    external = ZERO
    for valuation in result.valuations:
        external += valuation.external_flow
        for key, value in valuation.attribution.items():
            contributions[key] += value
    closing = result.valuations[-1].value
    opening = closing - external - sum(contributions.values(), ZERO)
    return {"opening": opening, "external_cashflows": external, **contributions, "closing": closing}


def _events(result):
    counts, rows = defaultdict(int), {}
    start, end = result.valuations[0].date, result.valuations[-1].date
    for event in result.final_state.events:
        if not start <= event.date <= end:
            continue
        group = (event.date, event.kind, event.rule)
        counts[group] += 1
        row = asdict(event)
        row.pop("sequence")
        rows[(*group, counts[group])] = row
    return rows


def compare_results(left, right):
    if left.dataset_id != right.dataset_id:
        raise ValueError("comparison requires the same fixed dataset/path")
    if left.report_currency != right.report_currency or [v.date for v in left.valuations] != [
        v.date for v in right.valuations
    ]:
        raise ValueError("comparison requires identical valuation dates and report currency")
    a, b = wealth_bridge(left), wealth_bridge(right)
    event_a, event_b = _events(left), _events(right)
    differences = []
    for key in sorted(event_a.keys() | event_b.keys()):
        first, second = event_a.get(key), event_b.get(key)
        if json_text(first) != json_text(second):
            differences.append(
                dict(
                    date=key[0],
                    kind=key[1],
                    rule=key[2],
                    occurrence=key[3],
                    left=first,
                    right=second,
                )
            )
    return {
        "left": left.plan_name,
        "right": right.plan_name,
        "dataset_id": left.dataset_id,
        "report_currency": left.report_currency,
        "delta_direction": "right_minus_left",
        "wealth_bridge": {
            "left": a,
            "right": b,
            "delta": {k: b.get(k, ZERO) - a.get(k, ZERO) for k in a.keys() | b.keys()},
        },
        "actual_external_flows_equal": [(v.date, v.external_flow) for v in left.valuations]
        == [(v.date, v.external_flow) for v in right.valuations],
        "first_event_difference": differences[0] if differences else None,
        "event_differences": differences,
        "daily_value_difference": [
            dict(date=x.date, amount=y.value - x.value)
            for x, y in zip(left.valuations, right.valuations, strict=True)
        ],
    }
