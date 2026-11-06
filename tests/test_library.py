from decimal import Decimal

import pytest

from allocflow.application.library import PlanLibrary
from allocflow.config.editing import FieldEdit, edit_plan, reorder_rules
from allocflow.config.loader import dump_plan, parse_plan, plan_fingerprint


def test_edits_are_atomic_and_yaml_keeps_all_values(plan):
    updated = edit_plan(
        plan, (FieldEdit(path=("cashflows", 1, "money", "amount"), value="12345.6789"),)
    )
    assert updated.cashflows[1].money.amount == Decimal("12345.6789")
    assert plan.cashflows[1].money.amount == 10000
    assert plan_fingerprint(parse_plan(dump_plan(updated))) == plan_fingerprint(updated)
    with pytest.raises(ValueError):
        edit_plan(plan, (FieldEdit(path=("allocation", "weight"), value="0.5"),))
    ordered = reorder_rules(plan, [r.id for r in reversed(plan.rules)])
    assert ordered.rules[0] == plan.rules[-1]
    with pytest.raises(ValueError):
        reorder_rules(plan, [])


def test_library_revisions_copy_failed_run_and_integrity(plan, tmp_path):
    library = PlanLibrary(tmp_path)
    text = "# retained comment\n" + dump_plan(plan)
    first = library.save("one", text)
    copied = library.copy("one", first["revision"], "two")
    assert library.load("two", copied["revision"]) == text
    assert len(library.revisions()) == 2
    with pytest.raises(ValueError, match="identifier"):
        library.save("../escape", text)
    with pytest.raises(OSError):
        library.run("one", first["revision"], tmp_path / "absent", html=False)
    assert library.history()[0]["status"] == "failed"
    path = tmp_path / "plans" / "one" / first["revision"] / "source.yaml"
    path.write_text(text + "\n# tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        library.load("one", first["revision"])


def test_library_run_records_checkpoint_and_dataset(plan, flat_market, tmp_path):
    library = PlanLibrary(tmp_path)
    revision = library.save("demo", dump_plan(plan))
    meta, result = library.run("demo", revision["revision"], flat_market, html=False)
    assert meta["status"] == "complete"
    from pathlib import Path

    assert (Path(meta["output"]) / "checkpoint.json").exists()
    assert library.history()[0]["dataset_id"] == result.dataset_id
