from allocflow.domain.types import ZERO, BuyIntent, SellIntent
from allocflow.policies.base import Decision


def evaluate_rebalance(rule, ctx):
    members = ctx.node_targets[rule.target_node]
    credits = {i: ZERO for i in members}
    if rule.weight_basis == "budget_inclusive":
        # Protected cash counts toward its allocation node, but is never spent here.
        for budget, balance in ctx.budgets.items():
            if budget in rule.cash_budgets:
                continue
            leaves = ctx.node_targets[ctx.budget_nodes[budget]]
            weight_sum = sum(leaves.values(), ZERO)
            value = balance * ctx.fx_to_report[ctx.budget_currencies[budget]]
            for instrument, weight in leaves.items():
                if instrument in credits:
                    credits[instrument] += value * weight / weight_sum
    if ctx.total_value <= 0:
        return Decision((), "empty_account", {}, {})
    drifts = {}
    for instrument in members:
        actual = (ctx.holding_values.get(instrument, ZERO) + credits[instrument]) / ctx.total_value
        target = ctx.targets[instrument]
        drift = abs(actual - target)
        drifts[instrument] = (
            drift / target if rule.threshold_mode == "relative" and target else drift
        )
    if max(drifts.values()) <= rule.threshold:
        return Decision((), "within_rebalance_threshold", {}, {})
    desired = {i: max(ctx.total_value * ctx.targets[i] - credits[i], ZERO) for i in members}
    intents = []
    # Sells precede buys; execution caps each buy to funds actually available after fees.
    for i in sorted(members):
        excess = ctx.holding_values.get(i, ZERO) - desired[i]
        if excess > rule.minimum_trade:
            price = ctx.prices[i] * ctx.fx_to_report[ctx.instrument_currencies[i]]
            intents.append(
                SellIntent(
                    rule.id,
                    rule.proceeds_budget,
                    i,
                    min(ctx.holdings[i], excess / price),
                    "rebalance_overweight",
                )
            )
    for i in sorted(members, key=lambda i: (ctx.holding_values.get(i, ZERO) - desired[i], i)):
        deficit = desired[i] - ctx.holding_values.get(i, ZERO)
        if deficit <= rule.minimum_trade:
            continue
        for budget in rule.cash_budgets:
            # The last configured budget may receive sale proceeds not yet visible in ctx.
            currency_rate = ctx.fx_to_report[ctx.budget_currencies[budget]]
            cap = deficit / currency_rate
            if budget != rule.proceeds_budget:
                cap = min(cap, ctx.budgets.get(budget, ZERO))
            if cap > 0:
                intents.append(BuyIntent(rule.id, budget, i, cap, "rebalance_underweight"))
                deficit -= cap * currency_rate
            if deficit <= 0:
                break
    return Decision(tuple(intents), f"threshold_exceeded:{dict(drifts)}", {}, {})
