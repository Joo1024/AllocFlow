"""Cross-model validation kept outside the plan's field definitions."""


def validate_extensions(plan):
    rules = {r.id: r for r in plan.rules}
    instruments = {i.id for i in plan.instruments}
    budgets = {b.id for b in plan.budgets}
    flows = {f.id: f for f in plan.cashflows}

    def condition(spec):
        if spec is None:
            return
        if spec.kind != "predicate":
            for child in spec.conditions:
                condition(child)
            return
        allowed = budgets if spec.metric == "budget" else instruments
        if spec.metric == "total_value":
            if spec.reference is not None:
                raise ValueError("total_value predicate requires null reference")
        elif spec.reference not in allowed:
            raise ValueError(f"unknown predicate reference: {spec.reference}")
        if spec.metric != "drawdown" and spec.lookback_sessions is not None:
            raise ValueError("lookback only applies to drawdown predicate")

    if len({c.rule for c in plan.controls}) != len(plan.controls):
        raise ValueError("duplicate rule control")
    for control in plan.controls:
        if control.rule not in rules:
            raise ValueError(f"unknown controlled rule: {control.rule}")
        condition(control.condition)
        if rules[control.rule].kind != "invest" and (
            control.rank != "original"
            or control.max_assets is not None
            or control.minimum_order
            or control.maximum_deployment is not None
            or control.reserve_amount
        ):
            raise ValueError("order sizing/ranking controls require an invest rule")
    p = plan.planning
    if p is None:
        return
    if p.phases[0].start > plan.start or p.phases[-1].end < plan.end:
        raise ValueError("planning phases must cover the run interval")
    from datetime import timedelta

    for left, right in zip(p.phases, p.phases[1:], strict=False):
        if right.start != left.end + timedelta(days=1):
            raise ValueError("planning phases must be contiguous")
    for phase in p.phases:
        if not set(phase.rules) <= rules.keys() or not set(phase.cashflows) <= flows.keys():
            raise ValueError(f"unknown rule/cashflow in phase: {phase.id}")
    if not set(p.inflation.indexed_cashflows) <= flows.keys():
        raise ValueError("unknown inflation cashflow")
    if any(flows[f].annual_growth != 0 for f in p.inflation.indexed_cashflows):
        raise ValueError("indexed cashflows require zero annual_growth to avoid double escalation")
    if (
        plan.withdrawal
        and plan.withdrawal.amount_basis == "portfolio_fraction"
        and any(flows[f].direction == "withdrawal" for f in p.inflation.indexed_cashflows)
    ):
        raise ValueError("fraction withdrawals cannot also be inflation-indexed")
    if any(r.budget not in budgets for r in p.reserves):
        raise ValueError("unknown reserve budget")
    if any(g.date < p.phases[0].start or g.date > p.phases[-1].end for g in p.goals):
        raise ValueError("goal date must lie inside planning phases")
