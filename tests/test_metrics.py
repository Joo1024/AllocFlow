from datetime import date
from decimal import Decimal

from allocflow.analysis.metrics import xirr_metric


def test_xirr_investor_terminal_value_and_multiple_roots(plan):
    annual = xirr_metric(
        [(date(2021, 1, 1), Decimal(100))], date(2022, 1, 1), Decimal(110), plan.analysis
    )
    assert abs(annual["value"] - 0.10) < 1e-8
    # -100 +230/(1+r) -132/(1+r)^2 has roots 10% and 20%.
    flows = [
        (date(2021, 1, 1), Decimal(100)),
        (date(2022, 1, 1), Decimal(-230)),
        (date(2023, 1, 1), Decimal(132)),
    ]
    result = xirr_metric(flows, date(2023, 1, 1), Decimal(0), plan.analysis)
    assert result["status"] == "multiple_roots"
    assert len(result["roots"]) == 2
    assert not result["uniqueness_proven"]
