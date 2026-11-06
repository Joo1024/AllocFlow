from pathlib import Path
from typing import Annotated

import typer

from allocflow.application.library import PlanLibrary
from allocflow.reporting.projections import json_text


def register(app, errors):
    library = typer.Typer(help="本地计划版本与运行历史")
    app.add_typer(library, name="library")

    @library.command("save")
    @errors
    def save(root: Path, name: str, plan: Annotated[Path, typer.Option(exists=True)]):
        typer.echo(json_text(PlanLibrary(root).save(name, plan.read_text(encoding="utf-8"))))

    @library.command("list")
    @errors
    def list_plans(root: Path):
        typer.echo(json_text(PlanLibrary(root).revisions()))

    @library.command("copy")
    @errors
    def copy(root: Path, name: str, revision: str, destination: str):
        typer.echo(json_text(PlanLibrary(root).copy(name, revision, destination)))

    @library.command("history")
    @errors
    def history(root: Path):
        typer.echo(json_text(PlanLibrary(root).history()))

    @library.command("run")
    @errors
    def run(
        root: Path,
        name: str,
        revision: str,
        dataset: Annotated[Path, typer.Option(exists=True)],
        html: Annotated[bool, typer.Option("--html/--no-html")],
        checkpoint: Annotated[Path | None, typer.Option()] = None,
    ):
        metadata, _ = PlanLibrary(root).run(
            name, revision, dataset, html=html, checkpoint=checkpoint
        )
        typer.echo(json_text(metadata))
