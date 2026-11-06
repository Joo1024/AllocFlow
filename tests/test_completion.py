import json
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from test_withdrawals import withdrawal_plan

from allocflow.adapters.dataset import MarketDataset
from allocflow.adapters.providers import download_dataset
from allocflow.application.checkpoints import load_checkpoint
from allocflow.application.service import run_plan
from allocflow.config.plan import PlanSpec
from allocflow.config.providers import ProviderRequest
from allocflow.interfaces.cli import read_spec
from allocflow.reporting.export import export_run


def test_fraction_withdrawal_is_sized_from_account(plan, flat_market):
    raw = withdrawal_plan(plan, "partial", 0).model_dump(mode="json")
    raw["withdrawal"].update(amount_basis="portfolio_fraction", fraction="0.1")
    raw["execution"]["fee"]["fixed"] = "0"
    result = run_plan(PlanSpec.model_validate(raw), flat_market)
    event = next(
        e for e in result.final_state.events if e.rule == "withdraw" and e.kind == "cashflow"
    )
    assert float(event.details["requested"]) == pytest.approx(10000, abs=0.001)
    assert float(result.valuations[-1].value) == pytest.approx(90000, abs=0.001)
    raw["cashflows"][-1]["money"]["amount"] = "100"
    with pytest.raises(ValidationError, match="zero fixed amount"):
        PlanSpec.model_validate(raw)


def test_persisted_checkpoint_matches_continuous_run_and_rejects_edits(tmp_path, plan, flat_market):
    full = run_plan(plan, flat_market)
    raw = plan.model_dump(mode="json")
    raw["end"] = "2021-02-26"
    first = run_plan(PlanSpec.model_validate(raw), flat_market)
    export_run(first, tmp_path / "run", html=False)
    raw = plan.model_dump(mode="json")
    raw["start"] = "2021-03-01"
    continuation = PlanSpec.model_validate(raw)
    path = tmp_path / "run" / "checkpoint.json"
    restored = load_checkpoint(path, continuation)
    assert restored == first.final_state
    final = run_plan(continuation, flat_market, initial_state=restored)
    assert final.final_state.holdings == full.final_state.holdings
    assert final.final_state.budgets == full.final_state.budgets
    assert final.valuations[-1].value == full.valuations[-1].value
    raw["report_currency"] = "USD"
    with pytest.raises(ValueError, match="currency contract"):
        load_checkpoint(path, PlanSpec.model_validate(raw))
    payload = json.loads(path.read_text())
    payload["state"]["units"] = "9999"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity"):
        load_checkpoint(path, continuation)


def test_unknown_strategy_fails_before_execution(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["rules"].append(
        dict(id="extension", kind="custom", schedule="monthly", strategy="missing", parameters={})
    )

    class ForbiddenExecution:
        def execute(self, *args):
            raise AssertionError("execution started before strategy validation")

    with pytest.raises(ValueError, match="unregistered strategy"):
        run_plan(PlanSpec.model_validate(raw), flat_market, execution=ForbiddenExecution())


def test_provider_snapshot_mapping_and_fx_inversion(tmp_path, plan, monkeypatch):
    request = read_spec(Path("examples/providers.yaml"), ProviderRequest)
    monkeypatch.setattr(
        "allocflow.adapters.providers._prices",
        lambda source, request: [(request.start, 100.0), (request.end, 101.0)],
    )
    monkeypatch.setattr(
        "allocflow.adapters.providers._history",
        lambda symbol, request: pd.DataFrame(
            {"Close": [7.0, 7.0]}, index=pd.to_datetime([request.start, request.end])
        ),
    )
    download_dataset(plan, request, tmp_path / "data")
    market = MarketDataset.load(tmp_path / "data", max_stale_days=10)
    assert float(market.fx("CNY", "USD", request.start)) == pytest.approx(1 / 7)
    assert market.price("VOO", request.start) == 100
    assert market.metadata["source"] == "retrospective_provider_download"
    assert "not certified point-in-time" in market.metadata["availability_basis"]
