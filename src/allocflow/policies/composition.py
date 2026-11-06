from dataclasses import replace
from datetime import date
from operator import ge, gt, le, lt

from allocflow.domain.types import ZERO
from allocflow.policies.base import Decision
from allocflow.policies.registry import evaluate_rule

OPERATORS = {"lt": lt, "le": le, "gt": gt, "ge": ge}


def matches(spec, ctx):
    if spec is None:
        return True
    if spec.kind != "predicate":
        values = [matches(c, ctx) for c in spec.conditions]
        return all(values) if spec.kind == "all" else any(values)
    if spec.metric == "budget":
        value = ctx.budgets.get(spec.reference, ZERO)
    elif spec.metric == "total_value":
        value = ctx.total_value
    elif spec.metric in {"weight", "drift"}:
        value = (
            ctx.holding_values.get(spec.reference, ZERO) / ctx.total_value
            if ctx.total_value
            else ZERO
        )
        if spec.metric == "drift":
            value -= ctx.targets[spec.reference]
    else:
        history = ctx.histories[spec.reference]
        if spec.lookback_sessions is not None:
            history = history[-spec.lookback_sessions :]
        if not history:
            return False
        value = 1 - history[-1] / max(history)
    return OPERATORS[spec.operator](value, spec.value)


def evaluate_controlled(rule, ctx, strategies, control):
    if control is None:
        return evaluate_rule(rule, ctx, strategies)
    active = matches(control.condition, ctx)
    observed = {"control_condition": active}
    reason = None
    if not control.start <= ctx.day <= control.end or ctx.day.month not in control.months:
        reason = "outside_control_schedule"
    elif not active:
        reason = "condition_false"
    elif control.rearm == "crossing" and ctx.memory.get("control_condition", False):
        reason = "waiting_for_condition_reset"
    elif (
        control.max_fires is not None
        and int(ctx.memory.get("control_fires", 0)) >= control.max_fires
    ):
        reason = "maximum_fire_count"
    elif (
        "control_last_fire" in ctx.memory
        and (ctx.day - date.fromisoformat(ctx.memory["control_last_fire"])).days
        < control.cooldown_days
    ):
        reason = "cooldown"
    if reason:
        return Decision((), reason, observed, {})
    # Rank the entire eligible selection, then apply both explicit count limits.
    evaluated = rule
    if rule.kind == "invest" and control.rank != "original":
        evaluated = rule.model_copy(
            update={"selector": rule.selector.model_copy(update={"max_assets": None})}
        )
    result = evaluate_rule(evaluated, ctx, strategies)
    intents = list(result.intents)
    if rule.kind == "invest" and intents:
        if control.rank == "underweight":
            intents.sort(
                key=lambda i: (
                    -(
                        ctx.total_value * ctx.targets[i.instrument]
                        - ctx.holding_values.get(i.instrument, ZERO)
                    ),
                    i.instrument,
                )
            )
        elif control.rank == "momentum":

            def score(intent):
                h = ctx.histories[intent.instrument][-control.ranking_lookback_sessions :]
                return h[-1] / h[0] - 1 if len(h) >= control.ranking_lookback_sessions else None

            intents = [i for i in intents if score(i) is not None]
            intents.sort(key=lambda i: (-score(i), i.instrument))
        original_total = sum((i.maximum_cash for i in intents), ZERO)
        counts = [c for c in (control.max_assets, rule.selector.max_assets) if c is not None]
        if counts:
            intents = intents[: min(counts)]
        cap = max(ctx.budgets.get(rule.source_budget, ZERO) - control.reserve_amount, ZERO)
        if control.maximum_deployment is not None:
            cap = min(cap, control.maximum_deployment)
        spend = min(original_total, cap)
        denominator = sum((i.maximum_cash for i in intents), ZERO)
        intents = [
            replace(i, maximum_cash=spend * i.maximum_cash / denominator)
            for i in intents
            if denominator
        ]
        intents = [
            i for i in intents if i.maximum_cash >= control.minimum_order and i.maximum_cash > 0
        ]
    accepted = {
        **result.accepted_state,
        "control_last_fire": ctx.day.isoformat(),
        "control_fires": int(ctx.memory.get("control_fires", 0)) + 1,
    }
    explanation = result.explanation + (
        ";control_filtered_all_orders" if result.intents and not intents else ";control_passed"
    )
    return Decision(tuple(intents), explanation, {**result.observed_state, **observed}, accepted)
