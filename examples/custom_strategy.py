"""Run with the SDK; YAML names a registry entry, never an arbitrary import path."""

from allocflow.config.common import Identifier, Positive, Spec
from allocflow.domain.types import BuyIntent
from allocflow.policies.base import Decision, Strategy, StrategyRegistry


class FixedBuyParameters(Spec):
    budget: Identifier
    instrument: Identifier
    maximum_cash: Positive


class FixedBuy(Strategy):
    def evaluate(self, context, parameters):
        intent = BuyIntent(
            "custom_fixed_buy",
            parameters.budget,
            parameters.instrument,
            parameters.maximum_cash,
            "user_extension",
        )
        return Decision((intent,), "explicit fixed cash budget", {}, {})


def registry():
    result = StrategyRegistry()
    result.register("fixed_buy", FixedBuy(), FixedBuyParameters)
    return result


# YAML rule:
# - id: fixed_buy_example
#   kind: custom
#   schedule: monthly
#   strategy: fixed_buy
#   parameters: {budget: stock_dca, instrument: VOO, maximum_cash: '100'}
# run_plan(plan, dataset, strategies=registry())
