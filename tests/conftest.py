from datetime import date, timedelta
from decimal import Decimal

import pytest

from allocflow.adapters.dataset import MarketDataset, Observation
from allocflow.config.loader import load_plan
from allocflow.config.plan import PlanSpec


@pytest.fixture
def plan():
    raw = load_plan("examples/user_plan.yaml").model_dump(mode="json")
    raw["end"] = "2021-03-31"
    return PlanSpec.model_validate(raw)


@pytest.fixture
def flat_market(plan):
    day = date(2020, 1, 1)
    days = []
    while day <= date(2024, 1, 1):
        days.append(day)
        day += timedelta(days=1)
    observations = tuple(Observation(d, d, Decimal(100)) for d in days)
    fx = {
        "CNY": tuple(Observation(d, d, Decimal(1) / 7) for d in days),
        "EUR": tuple(Observation(d, d, Decimal("1.1")) for d in days),
    }
    metadata = {
        "base_currency": "USD",
        "dataset_id": "flat-test",
        "source": "independent_hand_calculation",
        "instruments": {i.id: i.price_mode for i in plan.instruments},
    }
    return MarketDataset(
        {i.id: observations for i in plan.instruments}, fx, metadata=metadata, max_stale_days=10
    )


def changed(plan, **updates):
    return PlanSpec.model_validate({**plan.model_dump(mode="json"), **updates})
