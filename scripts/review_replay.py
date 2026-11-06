"""Download once, replay both revisions against identical bytes, retain evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys


def child():
    from allocflow.config.loader import load_plan

    action, plan_path, data_path, extra = sys.argv[2:]
    plan = load_plan(plan_path)
    if action == "download":
        import yaml
        from allocflow.adapters.providers import download_dataset
        from allocflow.config.providers import ProviderRequest
        raw = yaml.safe_load(Path(extra).read_text())
        raw.update(timeout_seconds="15", retry_attempts=2, retry_wait_seconds="1")
        download_dataset(plan, ProviderRequest.model_validate(raw), data_path)
        return
    from allocflow.application.service import run_plan
    from allocflow.reporting.export import export_run
    export_run(run_plan(plan, data_path), extra, html=False)


def invoke(root, action, plan, data, extra):
    environment = {**os.environ, "PYTHONPATH": str(root / "src")}
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "child",
         action, str(plan), str(data), str(extra)],
        cwd=root, env=environment, check=True, timeout=240,
    )


def summary(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    values = json.loads((folder / "valuations.json").read_text())
    events = json.loads((folder / "events.json").read_text())
    return {
        "dataset_id": manifest["dataset_id"],
        "code": manifest["code"],
        "terminal_value": values[-1]["value"],
        "report_currency": manifest["plan"]["report_currency"],
        "events": len(events),
        "quality_valid": manifest["data_quality"]["valid"],
        "metrics": json.loads((folder / "metrics.json").read_text()),
    }


def main():
    root = Path.cwd()
    baseline = root / "work/review-baseline"
    output = root / "work/review-evidence"
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for label, request in [
        ("user", "examples/providers.yaml"),
        ("china", "examples/data/china_providers.yaml"),
    ]:
        plan = root / f"examples/plans/{label}_live.yaml"
        data = output / f"{label}-data"
        row = {"plan": label}
        try:
            invoke(root, "download", plan, data, root / request)
            for version, source in [("baseline", baseline), ("fixed", root), ("repeat", root)]:
                invoke(source, "run", plan, data, output / f"{label}-{version}")
            old = summary(output / f"{label}-baseline")
            fixed = summary(output / f"{label}-fixed")
            repeat = summary(output / f"{label}-repeat")
            assert old["dataset_id"] == fixed["dataset_id"] == repeat["dataset_id"]
            for name in ("valuations.json", "final_state.json"):
                assert (output / f"{label}-fixed" / name).read_bytes() == (
                    output / f"{label}-repeat" / name
                ).read_bytes()
            row.update(status="ok", baseline=old, fixed=fixed, repeat_identical=True)
        except Exception as exc:
            row.update(status="error", error_type=type(exc).__name__, error=str(exc))
        reports.append(row)
        (output / "summary.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
        print(json.dumps(row, ensure_ascii=False), flush=True)
    if any(row["status"] != "ok" for row in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child()
    else:
        main()
