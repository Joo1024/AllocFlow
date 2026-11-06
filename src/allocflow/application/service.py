import hashlib
import importlib.metadata
import platform
import subprocess
from dataclasses import asdict
from pathlib import Path

from allocflow.adapters.dataset import MarketDataset
from allocflow.analysis.metrics import compute_metrics
from allocflow.config.loader import plan_fingerprint
from allocflow.config.plan import PlanSpec
from allocflow.domain.types import RunResult
from allocflow.engine.simulation import simulate
from allocflow.execution.model import CashExecution
from allocflow.policies.base import StrategyRegistry


def code_identity():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for file in sorted(root.rglob("*.py")):
        digest.update(str(file.relative_to(root)).encode())
        digest.update(file.read_bytes())
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"commit": commit, "python_source_sha256": digest.hexdigest()}


def run_plan(plan, dataset, *, strategies=None, execution=None, initial_state=None):
    # Even existing models are revalidated at the public boundary.
    plan = PlanSpec.model_validate(
        plan.model_dump(mode="json") if isinstance(plan, PlanSpec) else plan
    )
    market = (
        MarketDataset.load(dataset, max_stale_days=plan.execution.max_stale_days)
        if isinstance(dataset, (str, Path))
        else dataset
    )
    market = market.with_staleness_policy(plan.execution.max_stale_days)
    from allocflow.adapters.quality import inspect_dataset

    quality = inspect_dataset(plan, market)
    if not quality.valid:
        failures = [
            f"{i.reference}:{i.code}:{i.first_date}"
            for i in quality.issues
            if i.severity == "error"
        ]
        raise ValueError("dataset preflight failed: " + "; ".join(failures))
    registry = strategies if strategies is not None else StrategyRegistry()
    for rule in plan.rules:
        if rule.kind == "custom":
            registry.validate(rule.strategy, rule.parameters)
    values, state = simulate(
        plan,
        market,
        execution if execution is not None else CashExecution(),
        registry,
        initial_state=initial_state,
    )
    versions = {}
    for package in [
        "allocflow",
        "pydantic",
        "pandas",
        "numpy",
        "exchange-calendars",
        "pyarrow",
        "empyrical-reloaded",
        "pyxirr",
    ]:
        versions[package] = importlib.metadata.version(package)
    lock = Path(__file__).resolve().parents[3] / "uv.lock"
    manifest = {
        "schema_version": "1",
        "engine_semantics": "allocflow.daily.v2",
        "plan": plan.model_dump(mode="json"),
        "plan_fingerprint": plan_fingerprint(plan),
        "dataset_id": market.dataset_id,
        "data_quality": quality.model_dump(mode="json"),
        "dataset_metadata": getattr(market, "metadata", {}),
        "code": code_identity(),
        "python": platform.python_version(),
        "versions": versions,
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
        "pending_intents_at_end": len(state.pending),
        "initial_state_supplied": initial_state is not None,
        "initial_state": asdict(initial_state) if initial_state is not None else None,
    }
    metrics = compute_metrics(values, state, plan.analysis, initial_state=initial_state)
    result = RunResult(
        plan.name,
        plan.report_currency,
        market.dataset_id,
        plan_fingerprint(plan),
        values,
        state,
        metrics,
        manifest,
    )

    from allocflow.analysis.planning import planning_outcomes

    result.manifest["planning_outcomes"] = planning_outcomes(result)
    result.dataset_artifacts = dict(market.export_artifacts())
    result.manifest["dataset_bundled"] = bool(result.dataset_artifacts)
    return result


def compare_plans(plans, dataset, *, require_same_cashflows=True):
    if not plans:
        raise ValueError("comparison requires at least one plan")
    reference = plans[0]
    for plan in plans[1:]:
        if (plan.start, plan.end, plan.report_currency) != (
            reference.start,
            reference.end,
            reference.report_currency,
        ):
            raise ValueError("comparison requires identical interval and report currency")
        if require_same_cashflows:
            from allocflow.application.cashflow_contract import cashflow_contract

            if cashflow_contract(plan) != cashflow_contract(reference):
                raise ValueError("comparison cashflows differ in schedule or effective policy")
    results = [run_plan(plan, dataset) for plan in plans]
    if require_same_cashflows:

        def actual(result):
            return [(v.date, v.external_flow) for v in result.valuations]

        if any(actual(r) != actual(results[0]) for r in results[1:]):
            raise ValueError(
                "comparison actual cashflows differ; use require_same_cashflows=False "
                "to inspect path-dependent withdrawals or shortfalls"
            )
    return results
