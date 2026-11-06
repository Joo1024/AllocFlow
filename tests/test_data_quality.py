from datetime import date

from allocflow.adapters.quality import inspect_dataset


def test_middle_gap_cannot_hide_between_endpoints(plan, flat_market):
    flat_market.prices["VOO"] = tuple(
        r for r in flat_market.prices["VOO"] if not date(2021, 2, 1) <= r.date <= date(2021, 2, 25)
    )
    report = inspect_dataset(plan, flat_market)
    assert not report.valid
    issue = next(i for i in report.issues if i.reference == "VOO" and i.code == "coverage_gap")
    assert issue.first_date == date(2021, 2, 11)
    assert issue.last_date == date(2021, 2, 25)


def test_fx_missing_and_coverage_have_explicit_evidence(plan, flat_market):
    flat_market.rates.pop("CNY")
    report = inspect_dataset(plan, flat_market)
    assert any(i.reference == "FX:CNY" and i.severity == "error" for i in report.issues)
    assert next(s for s in report.series if s.reference == "VOO").first_observation == date(
        2020, 1, 1
    )
