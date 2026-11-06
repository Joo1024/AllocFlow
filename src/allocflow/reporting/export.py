from dataclasses import asdict
from decimal import Decimal, localcontext
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from allocflow.reporting.projections import json_text, tables


def arrow_table(frame):
    arrays = {}
    for name in frame.columns:
        values = frame[name].tolist()
        present = [v for v in values if v is not None]
        if present and all(isinstance(v, Decimal) for v in present):
            # Fact JSON preserves exact Decimal text; numeric projections use explicit scale.
            with localcontext() as ctx:
                ctx.prec = 80
                projected = [
                    v.quantize(Decimal("1e-18")) if v is not None else None for v in values
                ]
            arrays[name] = pa.array(projected, type=pa.decimal256(76, 18))
        else:
            arrays[name] = pa.array(values)
    return pa.table(arrays)


def export_run(result, output, *, html=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    marker = output / ".incomplete"
    marker.touch()
    from allocflow.application.checkpoints import checkpoint_document

    (output / "checkpoint.json").write_text(
        json_text(checkpoint_document(result), indent=2), encoding="utf-8"
    )
    (output / "manifest.json").write_text(json_text(result.manifest, indent=2), encoding="utf-8")
    (output / "metrics.json").write_text(json_text(result.metrics, indent=2), encoding="utf-8")
    (output / "events.json").write_text(
        json_text([asdict(e) for e in result.final_state.events], indent=2), encoding="utf-8"
    )
    (output / "final_state.json").write_text(
        json_text(asdict(result.final_state), indent=2), encoding="utf-8"
    )
    (output / "valuations.json").write_text(
        json_text([asdict(v) for v in result.valuations], indent=2), encoding="utf-8"
    )
    for name, frame in tables(result).items():
        frame.to_csv(output / f"{name}.csv", index=False)
        pq.write_table(arrow_table(frame), output / f"{name}.parquet")
    if html:
        from allocflow.reporting.html import render_report

        (output / "report.html").write_text(render_report(result), encoding="utf-8")
    if result.dataset_artifacts:
        dataset_dir = output / "dataset"
        dataset_dir.mkdir()
        for name, data in result.dataset_artifacts.items():
            (dataset_dir / name).write_bytes(data)
    marker.unlink()
    return output
