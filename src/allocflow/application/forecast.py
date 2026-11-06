"""Generate each market path once, then run all alternatives from identical state."""

from allocflow.application.checkpoints import account_contract
from allocflow.application.scenarios import scenario_market
from allocflow.application.service import run_plan


def _paired_path(plans, market, spec, path_id, initial_state):
    try:
        generated = scenario_market(plans[0], market, spec, path_id)
    except Exception as exc:
        return {"path_id": path_id, "status": "error", "error": str(exc), "plans": []}
    rows = []
    for index, plan in enumerate(plans):
        try:
            result = run_plan(plan, generated, initial_state=initial_state)
            rows.append(
                {
                    "plan_index": index,
                    "name": plan.name,
                    "status": "ok",
                    "outcomes": result.manifest["planning_outcomes"],
                }
            )
        except Exception as exc:
            rows.append(
                {"plan_index": index, "name": plan.name, "status": "error", "error": str(exc)}
            )
    complete = all(r["status"] == "ok" for r in rows)
    return {
        "path_id": path_id,
        "dataset_id": generated.dataset_id,
        "status": "ok" if complete else "error",
        "plans": rows,
        "terminal_differences": [
            r["outcomes"]["nominal_terminal_value"] - rows[0]["outcomes"]["nominal_terminal_value"]
            for r in rows[1:]
        ]
        if complete
        else None,
    }


def compare_scenarios(plans, market, spec, *, initial_state=None):
    if len(plans) < 2:
        raise ValueError("paired forecast requires at least two plans")
    reference = plans[0]
    for plan in plans[1:]:
        if (
            plan.start,
            plan.end,
            plan.report_currency,
            plan.instruments,
            plan.decision_calendar,
        ) != (
            reference.start,
            reference.end,
            reference.report_currency,
            reference.instruments,
            reference.decision_calendar,
        ):
            raise ValueError(
                "paired forecast requires identical interval, currencies, instruments and calendars"
            )
        if initial_state is not None and account_contract(plan) != account_contract(reference):
            raise ValueError("inherited account requires compatible plan budgets and instruments")
    if spec.workers == 1:
        paths = [_paired_path(plans, market, spec, i, initial_state) for i in range(spec.paths)]
    else:
        from joblib import Parallel, delayed, parallel_config

        with parallel_config(backend="loky", inner_max_num_threads=1):
            paths = Parallel(n_jobs=spec.workers)(
                delayed(_paired_path)(plans, market, spec, i, initial_state)
                for i in range(spec.paths)
            )
    complete = [p for p in paths if p["status"] == "ok"]
    summaries = []
    for index, plan in enumerate(plans):
        outcomes = [p["plans"][index]["outcomes"] for p in complete]
        goal_outcomes = [o for o in outcomes if o["goals_met"] is not None]
        summaries.append(
            dict(
                name=plan.name,
                completed_pairs=len(complete),
                exhaustion_probability=sum(o["first_exhaustion_date"] is not None for o in outcomes)
                / len(outcomes)
                if outcomes
                else None,
                shortfall_probability=sum(bool(o["withdrawal_shortfalls"]) for o in outcomes)
                / len(outcomes)
                if outcomes
                else None,
                goals_met_probability=sum(o["goals_met"] for o in goal_outcomes)
                / len(goal_outcomes)
                if goal_outcomes
                else None,
            )
        )
    return dict(
        requested=spec.paths,
        completed_pairs=len(complete),
        failed_pairs=spec.paths - len(complete),
        source_dataset_id=market.dataset_id,
        spec=spec.model_dump(mode="json"),
        initial_state_supplied=initial_state is not None,
        probability_denominator="completed_pairs_only",
        summaries=summaries,
        paths=paths,
    )
