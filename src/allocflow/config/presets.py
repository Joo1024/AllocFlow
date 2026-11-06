"""Explicit named inheritance. Mappings merge; arrays replace, never silently append."""

from copy import deepcopy
from typing import Any, Literal

from pydantic import model_validator

from allocflow.config.common import Identifier, Spec
from allocflow.config.plan import PlanSpec


class PresetSpec(Spec):
    name: Identifier
    extends: Identifier | None
    configuration: dict[str, Any]


class PresetCatalog(Spec):
    schema_version: Literal["1"]
    presets: tuple[PresetSpec, ...]

    @model_validator(mode="after")
    def unique(self):
        if len({p.name for p in self.presets}) != len(self.presets):
            raise ValueError("duplicate preset name")
        return self

    def resolve(self, name: str) -> PlanSpec:
        entries = {p.name: p for p in self.presets}

        def expand(key, visited):
            if key in visited:
                raise ValueError(f"preset inheritance cycle: {key}")
            if key not in entries:
                raise ValueError(f"unknown preset: {key}")
            entry = entries[key]
            base = expand(entry.extends, {*visited, key}) if entry.extends else {}
            return merge(base, entry.configuration)

        return PlanSpec.model_validate(expand(name, set()))


def merge(base, patch):
    result = deepcopy(base)
    for key, value in patch.items():
        result[key] = (
            merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else deepcopy(value)
        )
    return result
