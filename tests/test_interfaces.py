import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from allocflow.adapters.dataset import MarketDataset
from allocflow.adapters.demo import DemoSpec, create_demo_dataset
from allocflow.application.service import run_plan
from allocflow.interfaces.cli import app, read_spec
from allocflow.reporting.export import export_run


def test_cli_missing_parameter_has_field_path(tmp_path, plan):
    raw = plan.model_dump(mode="json")
    del raw["execution"]["fee"]["fixed"]
    file = tmp_path / "invalid.yaml"
    file.write_text(json.dumps(raw))
    result = CliRunner().invoke(app, ["validate", "--plan", str(file)])
    assert result.exit_code == 2
    error = json.loads(result.output)
    assert error["status"] == "error"
    assert error["details"][0]["loc"] == ["execution", "fee", "fixed"]


def test_decimal_parquet_and_exact_json_export(tmp_path, plan, flat_market):
    result = run_plan(plan, flat_market)
    output = export_run(result, tmp_path / "run", html=True)
    table = pq.read_table(output / "valuations.parquet")
    assert pa.types.is_decimal(table.schema.field("value").type)
    rows = json.loads((output / "valuations.json").read_text())
    assert rows[-1]["value"] == str(result.valuations[-1].value)
    html = (output / "report.html").read_text()
    assert "cdn.plot.ly" not in html.split("<script src=")[-1] if "<script src=" in html else True
    assert not (output / ".incomplete").exists()
    with pytest.raises(FileExistsError):
        export_run(result, output)


def test_dataset_hash_detects_changed_file(tmp_path, plan):
    output = tmp_path / "data"
    spec = read_spec(Path("examples/demo_data.yaml"), DemoSpec)
    create_demo_dataset(plan, spec, output)
    MarketDataset.load(output, max_stale_days=10)
    with (output / "prices.csv").open("a") as file:
        file.write("\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        MarketDataset.load(output, max_stale_days=10)


def test_web_loads_and_validates_template():
    file = Path("src/allocflow/interfaces/web.py")
    app_test = AppTest.from_file(str(file.resolve())).run(timeout=30)
    assert not app_test.exception
    app_test.sidebar.selectbox[0].select(Path("examples/user_plan.yaml").resolve()).run(timeout=30)
    app_test.sidebar.button[0].click().run(timeout=30)
    assert not app_test.exception
    assert any("配置有效" in s.value for s in app_test.success)
