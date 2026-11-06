from allocflow.domain.types import ONE, ZERO, BuyIntent
from allocflow.policies.base import Decision


def trigger(rule, ctx):
    spec = rule.trigger
    if spec.kind == "always":
        return ONE, "always", {}, {}
    history = ctx.histories[spec.instrument]
    if spec.lookback_sessions is not None:
        history = history[-spec.lookback_sessions :]
    if not history:
        return ZERO, "no_visible_signal_history", {}, {}
    peak = max(history)
    drawdown = 1 - history[-1] / peak
    matching = [tier for tier in spec.tiers if drawdown >= tier.threshold]
    level = matching[-1].threshold if matching else ZERO
    observed = {"observed_level": str(level)}
    month = ctx.day.strftime("%Y-%m")
    reason = f"{spec.instrument}:drawdown={drawdown};peak={peak};highest_tier={level}"
    if not matching:
        return ZERO, reason, observed, {}
    if spec.rearm == "monthly" and ctx.memory.get("last_month") == month:
        return ZERO, reason + ";already_triggered_this_month", observed, {}
    if spec.rearm == "crossing" and level <= type(level)(ctx.memory.get("observed_level", "0")):
        return ZERO, reason + ";no_new_crossing", observed, {}
    if spec.rearm == "new_peak" and ctx.memory.get("fired_peak") == str(peak):
        return ZERO, reason + ";waiting_for_new_peak", observed, {}
    return matching[-1].fraction, reason, observed, {"last_month": month, "fired_peak": str(peak)}


def evaluate_invest(rule, ctx):
    fraction, reason, observed, accepted = trigger(rule, ctx)
    spend = ctx.budgets.get(rule.source_budget, ZERO) * rule.sizer.fraction * fraction
    if spend < rule.sizer.minimum_budget or spend <= 0:
        return Decision((), reason + ";below_minimum_or_no_budget", observed, {})
    candidates = ctx.groups[rule.selector.group]
    if rule.selector.method == "underweight":
        scores = {
            i: max(ctx.total_value * ctx.targets[i] - ctx.holding_values.get(i, ZERO), ZERO)
            for i in candidates
        }
        selected = sorted(candidates, key=lambda i: (-scores[i], i))
    else:
        scores = {i: ctx.targets[i] for i in candidates}
        selected = sorted(candidates, key=lambda i: (-scores[i], i))
    selected = [i for i in selected if scores[i] > 0]
    if rule.selector.max_assets is not None:
        selected = selected[: rule.selector.max_assets]
    denominator = sum((scores[i] for i in selected), ZERO)
    intents = tuple(
        BuyIntent(rule.id, rule.source_budget, i, spend * scores[i] / denominator, reason)
        for i in selected
    )
    return Decision(intents, reason, observed, accepted)
