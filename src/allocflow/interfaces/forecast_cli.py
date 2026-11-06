from pathlib import Path
from typing import Annotated

import typer

from allocflow.reporting.projections import json_text


def register(app, errors, read_spec):
    @app.command("forecast-compare")
    @errors
    def forecast(
        plans: Annotated[list[Path], typer.Option(exists=True)],
        dataset: Annotated[Path, typer.Option(exists=True)],
        spec: Annotated[Path, typer.Option(exists=True)],
        output: Annotated[Path, typer.Option()],
        checkpoint: Annotated[Path | None, typer.Option()] = None,
    ):
        from allocflow.adapters.dataset import MarketDataset
        from allocflow.application.checkpoints import load_checkpoint
        from allocflow.application.forecast import compare_scenarios
        from allocflow.config.loader import load_plan
        from allocflow.config.scenarios import ScenarioSpec

        parsed = [load_plan(p) for p in plans]
        state = load_checkpoint(checkpoint, parsed[0]) if checkpoint else None
        market = MarketDataset.load(dataset, max_stale_days=parsed[0].execution.max_stale_days)
        result = compare_scenarios(
            parsed, market, read_spec(spec, ScenarioSpec), initial_state=state
        )
        output.write_text(json_text(result, indent=2), encoding="utf-8")
        typer.echo(json_text({k: v for k, v in result.items() if k != "paths"}))
