"""Local immutable plan revisions and inspectable synchronous run history."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from allocflow.application.errors import error_document
from allocflow.config.loader import dump_plan, parse_plan, plan_fingerprint
from allocflow.reporting.projections import json_text


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise ValueError(
            "library identifier must contain 1-96 letters, digits, underscores or hyphens"
        )
    return value


def _write(path, document):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json_text(document, indent=2), encoding="utf-8")
    temporary.replace(path)


class PlanLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def save(self, name, text):
        name = identifier(name)
        plan = parse_plan(text)
        revision = uuid4().hex
        folder = self.root / "plans" / name / revision
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "source.yaml").write_text(text, encoding="utf-8")
        (folder / "resolved.yaml").write_text(dump_plan(plan), encoding="utf-8")
        metadata = dict(
            name=name,
            revision=revision,
            created_at=datetime.now(UTC).isoformat(),
            fingerprint=plan_fingerprint(plan),
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        _write(folder / "revision.json", metadata)
        return metadata

    def load(self, name, revision):
        folder = self.root / "plans" / identifier(name) / identifier(revision)
        metadata = json.loads((folder / "revision.json").read_text(encoding="utf-8"))
        text = (folder / "source.yaml").read_text(encoding="utf-8")
        if hashlib.sha256(text.encode()).hexdigest() != metadata["source_sha256"]:
            raise ValueError("plan revision source hash mismatch")
        if plan_fingerprint(parse_plan(text)) != metadata["fingerprint"]:
            raise ValueError("plan revision fingerprint mismatch")
        return text

    def copy(self, name, revision, destination):
        return self.save(destination, self.load(name, revision))

    def revisions(self):
        return sorted(
            (
                json.loads(p.read_text(encoding="utf-8"))
                for p in (self.root / "plans").glob("*/*/revision.json")
            ),
            key=lambda x: x["created_at"],
            reverse=True,
        )

    def history(self):
        return sorted(
            (
                json.loads(p.read_text(encoding="utf-8"))
                for p in (self.root / "runs").glob("*/run.json")
            ),
            key=lambda x: x["created_at"],
            reverse=True,
        )

    def run(self, name, revision, dataset, *, html, checkpoint=None, strategies=None):
        from allocflow.application.checkpoints import load_checkpoint
        from allocflow.application.service import run_plan
        from allocflow.reporting.export import export_run

        plan = parse_plan(self.load(name, revision))
        run_id = uuid4().hex
        folder = self.root / "runs" / run_id
        folder.mkdir(parents=True, exist_ok=False)
        metadata = dict(
            run_id=run_id,
            name=name,
            revision=revision,
            status="running",
            created_at=datetime.now(UTC).isoformat(),
            output=str(folder / "result"),
            resumed_from=str(checkpoint) if checkpoint else None,
        )
        _write(folder / "run.json", metadata)
        try:
            state = load_checkpoint(checkpoint, plan) if checkpoint else None
            result = run_plan(plan, dataset, strategies=strategies, initial_state=state)
            export_run(result, folder / "result", html=html)
            metadata.update(
                status="complete", dataset_id=result.dataset_id, fingerprint=result.plan_fingerprint
            )
        except Exception as exc:
            metadata.update(status="failed", error=error_document(exc))
            _write(folder / "run.json", metadata)
            raise
        _write(folder / "run.json", metadata)
        return metadata, result
