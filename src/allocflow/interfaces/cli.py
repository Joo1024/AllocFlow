from functools import wraps
from pathlib import Path
from typing import Annotated

import typer

from allocflow.application.errors import error_document
from allocflow.config.loader import load_plan, plan_fingerprint
from allocflow.config.plan import PlanSpec
from allocflow.reporting.projections import json_text

app = typer.Typer(help="AllocFlow · 面向长期投资的现金流与资产配置模拟器", no_args_is_help=True)


def errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, ArithmeticError, ImportError) as exc:
            typer.echo(json_text(error_document(exc)), err=True)
            raise typer.Exit(code=2) from exc

    return wrapped


def read_spec(path, model):
    from allocflow.config.loader import read_document

    return model.model_validate(read_document(path.read_text(encoding="utf-8")))


@app.command()
@errors
def validate(plan: Annotated[Path, typer.Option(exists=True)]):
    spec = load_plan(plan)
    typer.echo(
        json_text({"status": "valid", "name": spec.name, "fingerprint": plan_fingerprint(spec)})
    )


@app.command()
@errors
def schema(output: Annotated[Path, typer.Option()]):
    output.write_text(json_text(PlanSpec.model_json_schema(), indent=2), encoding="utf-8")
    typer.echo(str(output))


@app.command("demo-data")
@errors
def demo_data(
    plan: Annotated[Path, typer.Option(exists=True)],
    spec: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
):
    from allocflow.adapters.demo import DemoSpec, create_demo_dataset

    create_demo_dataset(load_plan(plan), read_spec(spec, DemoSpec), output)
    typer.echo(
        json_text(
            {
                "status": "created",
                "source": "SYNTHETIC_DEMO_NOT_MARKET_HISTORY",
                "path": str(output),
            }
        )
    )


@app.command()
@errors
def run(
    plan: Annotated[Path, typer.Option(exists=True)],
    dataset: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
    html: Annotated[bool, typer.Option("--html/--no-html")],
):
    from allocflow.application.service import run_plan
    from allocflow.reporting.export import export_run

    result = run_plan(load_plan(plan), dataset)
    export_run(result, output, html=html)
    typer.echo(json_text({"status": "complete", "output": str(output), "metrics": result.metrics}))


@app.command()
@errors
def compare(
    plans: Annotated[list[Path], typer.Option(exists=True)],
    dataset: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
):
    from allocflow.application.service import compare_plans

    results = compare_plans([load_plan(p) for p in plans], dataset)
    from allocflow.analysis.comparison import compare_results

    output.write_text(
        json_text(
            {
                "plans": [{"plan": r.plan_name, "metrics": r.metrics} for r in results],
                "comparisons": [compare_results(results[0], r) for r in results[1:]],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    typer.echo(str(output))


@app.command()
@errors
def scenarios(
    plan: Annotated[Path, typer.Option(exists=True)],
    dataset: Annotated[Path, typer.Option(exists=True)],
    spec: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
):
    from dataclasses import asdict

    from allocflow.adapters.dataset import MarketDataset
    from allocflow.application.scenarios import run_scenarios
    from allocflow.config.scenarios import ScenarioSpec

    p = load_plan(plan)
    market = MarketDataset.load(dataset, max_stale_days=p.execution.max_stale_days)
    result = run_scenarios(p, market, read_spec(spec, ScenarioSpec))
    result["paths"] = [
        {**r, "events": [asdict(e) for e in r.get("events", [])]} for r in result["paths"]
    ]
    output.write_text(json_text(result, indent=2), encoding="utf-8")
    typer.echo(json_text({k: v for k, v in result.items() if k != "paths"}))


@app.command()
@errors
def download(
    plan: Annotated[Path, typer.Option(exists=True)],
    request: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
):
    from allocflow.adapters.providers import download_dataset
    from allocflow.config.providers import ProviderRequest

    download_dataset(load_plan(plan), read_spec(request, ProviderRequest), output)
    typer.echo(str(output))


@app.command()
def web():
    import subprocess
    import sys

    path = Path(__file__).with_name("web.py")
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(path)]))


@app.command()
@errors
def resume(
    plan: Annotated[Path, typer.Option(exists=True)],
    dataset: Annotated[Path, typer.Option(exists=True)],
    checkpoint: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
    html: Annotated[bool, typer.Option("--html/--no-html")],
):
    from allocflow.application.checkpoints import load_checkpoint
    from allocflow.application.service import run_plan
    from allocflow.reporting.export import export_run

    spec = load_plan(plan)
    result = run_plan(spec, dataset, initial_state=load_checkpoint(checkpoint, spec))
    export_run(result, output, html=html)
    typer.echo(json_text({"status": "complete", "output": str(output), "metrics": result.metrics}))


@app.command()
@errors
def migrate(
    plan: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
    target_version: Annotated[str, typer.Option()],
):
    from allocflow.config.evolution import migrate_document
    from allocflow.config.loader import dump_plan, read_document

    raw = read_document(plan.read_text(encoding="utf-8"))
    resolved = PlanSpec.model_validate(migrate_document(raw, target_version=target_version))
    with output.open("x", encoding="utf-8") as stream:
        stream.write(dump_plan(resolved))
    typer.echo(str(output))


@app.command()
@errors
def materialize(
    catalog: Annotated[Path, typer.Option(exists=True)],
    name: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
):
    from allocflow.config.loader import dump_plan
    from allocflow.config.presets import PresetCatalog

    plan = read_spec(catalog, PresetCatalog).resolve(name)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(dump_plan(plan))
    typer.echo(
        json_text({"preset": name, "fingerprint": plan_fingerprint(plan), "output": str(output)})
    )


@app.command("data-quality")
@errors
def data_quality(
    plan: Annotated[Path, typer.Option(exists=True)],
    dataset: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()],
):
    from allocflow.adapters.dataset import MarketDataset
    from allocflow.adapters.quality import inspect_dataset

    spec = load_plan(plan)
    report = inspect_dataset(
        spec, MarketDataset.load(dataset, max_stale_days=spec.execution.max_stale_days)
    )
    output.write_text(json_text(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    typer.echo(json_text({"valid": report.valid, "output": str(output)}))
    if not report.valid:
        raise typer.Exit(2)


from allocflow.interfaces.library_cli import register  # noqa: E402

register(app, errors)

from allocflow.interfaces.forecast_cli import register as register_forecast  # noqa: E402

register_forecast(app, errors, read_spec)
