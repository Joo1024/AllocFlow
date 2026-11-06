from allocflow.domain.types import ZERO, TransferIntent
from allocflow.policies.base import Decision
from allocflow.policies.invest import evaluate_invest
from allocflow.policies.rebalance import evaluate_rebalance


def evaluate_cap(rule, ctx):
    inflow = ctx.inflows.get(rule.inflow_reference, {}).get(rule.source_budget, ZERO)
    excess = ctx.budgets.get(rule.source_budget, ZERO) - inflow * rule.multiple
    intents = (
        ()
        if excess <= 0
        else (
            TransferIntent(
                rule.id, rule.source_budget, rule.destination_budget, excess, "budget_cap_overflow"
            ),
        )
    )
    return Decision(intents, f"cap={inflow * rule.multiple}", {}, {})


BUILTINS = {"invest": evaluate_invest, "budget_cap": evaluate_cap, "rebalance": evaluate_rebalance}


def evaluate_rule(rule, ctx, strategies):
    if rule.kind == "custom":
        return strategies.evaluate(rule.strategy, ctx, rule.parameters)
    return BUILTINS[rule.kind](rule, ctx)
