from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from test_withdrawals import withdrawal_plan

from allocflow.accounting.book import Book
from allocflow.adapters.dataset import MarketDataset
from allocflow.adapters.demo import DemoSpec, create_demo_dataset
from allocflow.application.service import run_plan
from allocflow.config.plan import PlanSpec
from allocflow.domain.types import AccountState, SellIntent
from allocflow.engine.scheduler import submit
from allocflow.execution.model import CashExecution
from allocflow.interfaces.cli import read_spec
from allocflow.reporting.export import export_run


def test_delayed_sells_reserve_inventory(plan, flat_market):
    raw = plan.model_dump(mode="json")
    raw["instruments"][1]["execution_delay_sessions"] = 1
    p = PlanSpec.model_validate(raw)
    book = Book(p, flat_market, AccountState())
    book.state.holdings["VOO"] = Decimal(10)
    intent = SellIntent("test", "stock_dca", "VOO", Decimal(8), "test")
    assert submit(book, CashExecution(), intent, date(2021, 1, 4))
    assert not submit(book, CashExecution(), intent, date(2021, 1, 4))
    assert book.sellable("VOO") == 2
    assert not CashExecution().execute(book, replace(intent, quantity=Decimal(3)), date(2021, 1, 4))
    book.assert_invariants()


def test_complete_redemption_does_not_invent_total_loss(plan, flat_market):
    raw = withdrawal_plan(plan, "partial", 200000).model_dump(mode="json")
    raw["withdrawal"]["cash_budgets"] = [b.id for b in plan.budgets]
    result = run_plan(PlanSpec.model_validate(raw), flat_market)
    assert result.valuations[-1].value == 0
    assert result.final_state.units == 0
    assert -0.01 < result.metrics["twr"]["value"] < 0


def test_file_dataset_is_bundled_without_changing_identity(tmp_path, plan):
    create_demo_dataset(
        plan, read_spec(Path("examples/demo_data.yaml"), DemoSpec), tmp_path / "input"
    )
    result = run_plan(plan, tmp_path / "input")
    export_run(result, tmp_path / "run", html=False)
    restored = MarketDataset.load(tmp_path / "run" / "dataset", max_stale_days=10)
    assert restored.dataset_id == result.dataset_id
    repeated = run_plan(plan, restored)
    assert repeated.valuations == result.valuations
