from pathlib import Path

import pytest
from pydantic import ValidationError

from allocflow.config.loader import load_plan, parse_plan
from allocflow.config.plan import PlanSpec


def test_all_named_plans_validate():
    for path in Path("examples").glob("*.yaml"):
        if path.stem not in {"demo_data", "scenarios", "stress", "providers"}:
            load_plan(path)


def test_missing_and_unknown_parameters_fail(plan):
    raw = plan.model_dump(mode="json")
    del raw["execution"]["fee"]["fixed"]
    with pytest.raises(ValidationError, match="fixed"):
        PlanSpec.model_validate(raw)
    raw["execution"]["fee"]["fixed"] = "1"
    raw["execution"]["hidden_default"] = 123
    with pytest.raises(ValidationError, match="hidden_default"):
        PlanSpec.model_validate(raw)


def test_duplicate_yaml_rejected():
    with pytest.raises(ValueError, match="duplicate YAML key"):
        parse_plan("name: first\nname: second\n")


def test_exact_user_allocation_and_cashflow(plan):
    assert plan.allocation.leaves()["BND"] == type(plan.allocation.weight)("0.168")
    assert plan.allocation.leaves()["SGOV"] == type(plan.allocation.weight)("0.16")
    initial, monthly = plan.cashflows
    assert initial.money.amount == 100000
    assert monthly.money.amount == 10000
    assert {d.budget: d.weight for d in initial.distributions}.get("stock_dip", 0) == 0
    assert {d.budget: d.weight for d in monthly.distributions}["stock_dip"] == type(
        initial.money.amount
    )("0.18")


def test_bad_references_and_weights_rejected(plan):
    raw = plan.model_dump(mode="json")
    raw["budgets"][0]["allocation_node"] = "missing"
    with pytest.raises(ValidationError, match="unknown allocation node"):
        PlanSpec.model_validate(raw)
