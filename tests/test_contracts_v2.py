import pytest

from allocflow.application.errors import validate_document
from allocflow.config.evolution import migrate_document
from allocflow.config.loader import dump_plan, parse_plan, plan_fingerprint
from allocflow.config.plan import PlanSpec
from allocflow.config.presets import PresetCatalog


def test_migration_is_explicit_and_roundtrips(plan):
    old = plan.model_dump(mode="json", exclude={"controls", "planning"})
    old["schema_version"] = "1"
    new = migrate_document(old, target_version="2")
    assert old["schema_version"] == "1" and "controls" not in old
    migrated = PlanSpec.model_validate(new)
    assert plan_fingerprint(parse_plan(dump_plan(migrated))) == plan_fingerprint(migrated)
    del new["controls"]
    with pytest.raises(ValueError, match="explicit fields"):
        PlanSpec.model_validate(new)


def test_presets_merge_maps_replace_lists_and_validate(plan):
    catalog = PresetCatalog.model_validate(
        {
            "schema_version": "1",
            "presets": [
                {"name": "base", "extends": None, "configuration": plan.model_dump(mode="json")},
                {
                    "name": "free",
                    "extends": "base",
                    "configuration": {"execution": {"fee": {"fixed": "0"}}, "rules": []},
                },
            ],
        }
    )
    free = catalog.resolve("free")
    assert free.execution.fee.fixed == 0 and free.rules == ()
    assert catalog.resolve("base").execution.fee.fixed == 1
    with pytest.raises(ValueError, match="unknown preset"):
        catalog.resolve("absent")
    cycle = PresetCatalog.model_validate(
        {
            "schema_version": "1",
            "presets": [{"name": "loop", "extends": "loop", "configuration": {}}],
        }
    )
    with pytest.raises(ValueError, match="cycle"):
        cycle.resolve("loop")


def test_errors_are_machine_readable():
    result = validate_document("schema_version: '2'\ncontrols: []\nplanning: null\n")
    assert result["status"] == "error"
    assert any(e["path"] == ["name"] and e["code"] == "missing" for e in result["details"])
    assert validate_document("[broken:")["status"] == "error"
