import hashlib
from datetime import timedelta
from decimal import Decimal

import numpy as np

from allocflow.adapters.calendar import next_session, sessions
from allocflow.adapters.dataset import MarketDataset, Observation
from allocflow.application.service import run_plan
from allocflow.engine.scheduler import timeline
from allocflow.reporting.projections import json_text


def scenario_market(plan, market, spec, path_id):
    if spec.training_end >= plan.start:
        raise ValueError("scenario calibration must end strictly before simulation start")
    if spec.shock_date is not None and not plan.start <= spec.shock_date <= plan.end:
        raise ValueError("shock date outside simulation interval")
    ids = [i.id for i in plan.instruments]
    currencies = sorted(market.fx_currencies())
    if not set(spec.asset_shocks) <= set(ids) or not set(spec.fx_shocks) <= set(currencies):
        raise ValueError("shock refers to unknown asset/currency")
    if market.base_currency in spec.fx_shocks and spec.fx_shocks[market.base_currency]:
        raise ValueError("dataset numeraire cannot be shocked relative to itself")
    rng = np.random.default_rng(np.random.SeedSequence([spec.root_seed, path_id]))
    days = timeline(plan)
    training = sessions(plan.decision_calendar, spec.training_start, spec.training_end)
    if len(training) < 3:
        raise ValueError("insufficient training sessions")
    columns = []
    for instrument in ids:
        columns.append([float(market.price(instrument, d, visible=True)) for d in training])
    for currency in currencies:
        columns.append([float(market.fx(currency, market.base_currency, d)) for d in training])
    factors = np.diff(np.log(np.array(columns).T), axis=0)
    if spec.method == "joint_block":
        from arch.bootstrap import CircularBlockBootstrap

        sampler = CircularBlockBootstrap(spec.block_sessions, np.arange(len(factors)), seed=rng)
        index = np.concatenate(
            [sampler.update_indices() for _ in range((len(days) - 1) // len(factors) + 1)]
        )[: len(days)]
        changes = factors[index]
    else:
        index = np.full(len(days), -1)
        changes = np.zeros((len(days), len(columns)))
    initial_day = plan.start - timedelta(days=1)
    initial = [float(market.price(i, initial_day, visible=True)) for i in ids]
    initial += [float(market.fx(c, market.base_currency, initial_day)) for c in currencies]
    matrix = np.exp(np.cumsum(changes, axis=0)) * np.array(initial)
    if spec.shock_date is not None:
        mask = np.array([d >= spec.shock_date for d in days])
        for i, instrument in enumerate(ids):
            matrix[mask, i] *= 1 + float(spec.asset_shocks.get(instrument, 0))
        for i, currency in enumerate(currencies, start=len(ids)):
            matrix[mask, i] *= 1 + float(spec.fx_shocks.get(currency, 0))
    prices = {
        i: tuple(r for r in market.price_observations(i) if r.date < plan.start and r.available_on < plan.start)
        for i in ids
    }
    rates = {
        c: tuple(r for r in market.fx_observations(c) if r.date < plan.start and r.available_on < plan.start)
        for c in currencies
    }
    instrument_specs = {i.id: i for i in plan.instruments}
    for column, instrument in enumerate(ids):
        asset = instrument_specs[instrument]
        asset_sessions = set(sessions(asset.calendar, plan.start, plan.end))
        prices[instrument] += tuple(
            Observation(
                d,
                next_session(asset.calendar, d, 1) if asset.pricing == "available_nav" else d,
                Decimal(str(matrix[row, column])),
            )
            for row, d in enumerate(days)
            if d in asset_sessions
        )
    for column, currency in enumerate(currencies, start=len(ids)):
        rates[currency] += tuple(
            Observation(d, d, Decimal(str(matrix[row, column]))) for row, d in enumerate(days)
        )
    metadata = {
        **market.metadata,
        "scenario": spec.model_dump(mode="json", exclude={"workers", "paths"}),
        "path_id": path_id,
        "sampled_indices": index.tolist(),
        "source_dataset_id": market.dataset_id,
        "source": "SYNTHETIC_SCENARIO",
        "availability_basis": "generated daily research path",
    }
    metadata["dataset_id"] = hashlib.sha256(json_text(metadata).encode()).hexdigest()
    return MarketDataset(
        prices, rates, metadata=metadata, max_stale_days=plan.execution.max_stale_days
    )


def _run_path(plan, market, spec, path_id, initial_state):
    try:
        generated = scenario_market(plan, market, spec, path_id)
        result = run_plan(plan, generated, initial_state=initial_state)
        shortfalls = [
            e
            for e in result.final_state.events
            if e.kind == "cashflow" and e.details.get("shortfall", 0) > 0 and e.date >= plan.start
        ]
        return {
            "path_id": path_id,
            "status": "ok",
            "terminal_value": str(result.valuations[-1].value),
            "exhausted": result.manifest["planning_outcomes"]["first_exhaustion_date"] is not None,
            "liquidity_shortfall": bool(shortfalls),
            "planning": result.manifest["planning_outcomes"],
            "dataset_id": generated.dataset_id,
            "metrics": result.metrics,
            "events": [
                e
                for e in result.final_state.events
                if e.status == "rejected" or e.details.get("shortfall", 0) > 0
            ],
        }
    except Exception as exc:
        return {
            "path_id": path_id,
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def run_scenarios(plan, market, spec, *, initial_state=None):
    if spec.workers == 1:
        paths = [_run_path(plan, market, spec, i, initial_state) for i in range(spec.paths)]
    else:
        from joblib import Parallel, delayed, parallel_config

        with parallel_config(backend="loky", inner_max_num_threads=1):
            paths = Parallel(n_jobs=spec.workers)(
                delayed(_run_path)(plan, market, spec, i, initial_state) for i in range(spec.paths)
            )
    completed = [p for p in paths if p["status"] == "ok"]
    values = [float(p["terminal_value"]) for p in completed]
    return {
        "requested": spec.paths,
        "completed": len(completed),
        "failed": spec.paths - len(completed),
        "exhaustion_probability_among_completed": sum(p["exhausted"] for p in completed)
        / len(completed)
        if completed
        else None,
        "shortfall_probability_among_completed": sum(p["liquidity_shortfall"] for p in completed)
        / len(completed)
        if completed
        else None,
        "distribution_status": "complete"
        if len(completed) == spec.paths
        else "incomplete_due_to_compute_failures",
        "terminal_quantiles": dict(
            zip(["p05", "p50", "p95"], np.quantile(values, [0.05, 0.5, 0.95]).tolist(), strict=True)
        )
        if values
        else None,
        "spec": spec.model_dump(mode="json"),
        "paths": paths,
    }
