from allocflow.application.scenarios import run_scenarios
from allocflow.config.plan import PlanSpec
from allocflow.config.scenarios import ScenarioSpec


def short_plan(plan):
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-01-15"
    return PlanSpec.model_validate(raw)


def spec(workers):
    return ScenarioSpec.model_validate(
        dict(
            schema_version="1",
            method="joint_block",
            training_start="2020-01-02",
            training_end="2020-12-31",
            paths=2,
            root_seed=17,
            block_sessions=5,
            workers=workers,
            shock_date=None,
            asset_shocks={},
            fx_shocks={},
        )
    )


def test_serial_parallel_paths_are_identical(plan, flat_market):
    p = short_plan(plan)
    first = run_scenarios(p, flat_market, spec(1))
    second = run_scenarios(p, flat_market, spec(2))
    assert first["failed"] == second["failed"] == 0
    assert [p["terminal_value"] for p in first["paths"]] == [
        p["terminal_value"] for p in second["paths"]
    ]
    assert [p["dataset_id"] for p in first["paths"]] == [
        p["dataset_id"] for p in second["paths"]
    ]  # worker config is provenance, not randomness


def test_compute_errors_are_not_counted_as_exhaustion(plan, flat_market):
    raw = spec(1).model_dump(mode="json")
    raw["training_end"] = "2021-02-01"
    result = run_scenarios(short_plan(plan), flat_market, ScenarioSpec.model_validate(raw))
    assert result["completed"] == 0
    assert result["failed"] == 2
    assert result["exhaustion_probability_among_completed"] is None
    assert all(p["status"] == "error" for p in result["paths"])


def test_generated_fund_nav_respects_own_calendar_and_publication(plan, flat_market):
    from allocflow.adapters.calendar import sessions
    from allocflow.application.scenarios import scenario_market

    raw = plan.model_dump(mode="json")
    raw["start"], raw["end"] = "2021-02-10", "2021-02-22"
    raw["instruments"][1].update(
        kind="mutual_fund", calendar="XSHG", pricing="available_nav", execution_delay_sessions=1
    )
    p = PlanSpec.model_validate(raw)
    market = scenario_market(p, flat_market, spec(1), 0)
    rows = [r for r in market.prices["VOO"] if r.date >= p.start]
    assert rows
    assert {r.date for r in rows} <= set(sessions("XSHG", p.start, p.end))
    assert all(r.available_on > r.date for r in rows)
