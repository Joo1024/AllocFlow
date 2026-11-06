import hashlib
import json
from pathlib import Path

import yaml

from allocflow.config.plan import PlanSpec


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML must not silently overwrite a user's investment parameters."""


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_plan(text: str) -> PlanSpec:
    return PlanSpec.model_validate(yaml.load(text, Loader=UniqueKeyLoader))


def load_plan(path: str | Path) -> PlanSpec:
    return parse_plan(Path(path).read_text(encoding="utf-8"))


def plan_fingerprint(plan: PlanSpec) -> str:
    canonical = json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
