from allocflow.accounting.planning import inflation_factor
from allocflow.config.plan import PlanSpec


def planning_outcomes(result):
    plan = PlanSpec.model_validate(result.manifest["plan"])
    first, last = result.valuations[0].date, result.valuations[-1].date
    events = [e for e in result.final_state.events if first <= e.date <= last]
    shortfalls = [
        dict(
            date=e.date,
            flow=e.rule,
            amount=e.details["shortfall"],
            currency=e.details.get("currency"),
        )
        for e in events
        if e.kind == "cashflow" and e.details.get("shortfall", 0) > 0
    ]
    goals = [dict(date=e.date, goal=e.rule, **e.details) for e in events if e.kind == "goal"]
    expected_goals = (
        {g.id for g in plan.planning.goals if first <= g.date <= last} if plan.planning else set()
    )
    missing_goals = sorted(expected_goals - {g["goal"] for g in goals})
    depletion = next(
        (
            v.date
            for v in result.valuations
            if v.value <= 0
            and any(d <= v.date and amount > 0 for d, amount in result.final_state.external_flows)
        ),
        None,
    )
    return dict(
        real_terminal_value=result.valuations[-1].value / inflation_factor(plan.planning, last),
        nominal_terminal_value=result.valuations[-1].value,
        first_exhaustion_date=depletion,
        first_shortfall_date=shortfalls[0]["date"] if shortfalls else None,
        withdrawal_shortfalls=shortfalls,
        goals=goals,
        goals_met=all(g["met"] for g in goals) if goals and not missing_goals else None,
        unobserved_goals=missing_goals,
        reserve_breaches=[
            dict(date=e.date, budget=e.rule, **e.details) for e in events if e.kind == "reserve"
        ],
    )
