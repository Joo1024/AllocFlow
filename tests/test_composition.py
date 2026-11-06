from datetime import date
from decimal import Decimal

import pytest

from allocflow.accounting.book import Book
from allocflow.config.composition import RuleControl
from allocflow.config.plan import PlanSpec
from allocflow.domain.types import AccountState
from allocflow.policies.base import StrategyRegistry
from allocflow.policies.composition import evaluate_controlled
from allocflow.policies.context import make_context


def control(rule, **updates):
    values = dict(
        rule=rule,
        start="2021-01-01",
        end="2023-12-31",
        months=list(range(1, 13)),
        condition=None,
        cooldown_days=10,
        max_fires=2,
        rearm="level",
        rank="underweight",
        ranking_lookback_sessions=None,
        max_assets=2,
        minimum_order="100",
        maximum_deployment="500",
        reserve_amount="200",
    )
    values.update(updates)
    return RuleControl.model_validate(values)


def test_control_limits_and_compound_predicates(plan, flat_market):
    rule = next(r for r in plan.rules if r.kind == "invest" and r.source_budget == "stock_dca")
    state = AccountState(cash={"USD": Decimal(1000)}, budgets={"stock_dca": Decimal(1000)})
    ctx = make_context(Book(plan, flat_market, state), date(2021, 1, 4), rule.id)
    c = control(
        rule.id,
        condition={
            "kind": "all",
            "conditions": [
                {
                    "kind": "predicate",
                    "metric": "budget",
                    "reference": "stock_dca",
                    "operator": "ge",
                    "value": "900",
                    "lookback_sessions": None,
                },
                {
                    "kind": "any",
                    "conditions": [
                        {
                            "kind": "predicate",
                            "metric": "total_value",
                            "reference": None,
                            "operator": "gt",
                            "value": "0",
                            "lookback_sessions": None,
                        }
                    ],
                },
            ],
        },
    )
    decision = evaluate_controlled(rule, ctx, StrategyRegistry(), c)
    assert len(decision.intents) == 2
    assert sum(i.maximum_cash for i in decision.intents) == 500
    assert all(i.maximum_cash >= 100 for i in decision.intents)
    state.rule_state[rule.id] = dict(decision.accepted_state)
    next_ctx = make_context(Book(plan, flat_market, state), date(2021, 1, 5), rule.id)
    assert evaluate_controlled(rule, next_ctx, StrategyRegistry(), c).explanation == "cooldown"
    state.rule_state[rule.id]["control_fires"] = 2
    assert evaluate_controlled(rule, next_ctx, StrategyRegistry(), c).explanation == "cooldown"
    next_ctx = make_context(Book(plan, flat_market, state), date(2021, 2, 5), rule.id)
    assert (
        evaluate_controlled(rule, next_ctx, StrategyRegistry(), c).explanation
        == "maximum_fire_count"
    )


def test_unknown_reference_rejected_before_run(plan):
    raw = plan.model_dump(mode="json")
    raw["controls"] = [control("absent").model_dump(mode="json")]
    with pytest.raises(ValueError, match="unknown controlled rule"):
        PlanSpec.model_validate(raw)
