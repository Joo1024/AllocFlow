"""Compare all policies that determine requested external cashflows."""


def cashflow_contract(plan):
    planning = plan.planning
    return {
        "decision_calendar": plan.decision_calendar,
        "flows": [f.model_dump(mode="json", exclude={"distributions"}) for f in plan.cashflows],
        "withdrawal": plan.withdrawal.model_dump(mode="json") if plan.withdrawal else None,
        "phases": [
            {"start": p.start, "end": p.end, "cashflows": sorted(p.cashflows)}
            for p in planning.phases
        ]
        if planning
        else None,
        "inflation": planning.inflation.model_dump(mode="json") if planning else None,
        "withdrawal_bounds": (
            planning.withdrawal_bounds.model_dump(mode="json")
            if planning and planning.withdrawal_bounds
            else None
        ),
        "reserves": [
            r.model_dump(mode="json") for r in planning.reserves if r.protect_from_withdrawals
        ]
        if planning
        else [],
    }
