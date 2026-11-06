from copy import deepcopy
from typing import Any

from allocflow.config.common import Spec
from allocflow.config.plan import PlanSpec


class FieldEdit(Spec):
    path: tuple[str | int, ...]
    value: Any


def edit_plan(plan: PlanSpec, edits: tuple[FieldEdit, ...]) -> PlanSpec:
    """Apply one atomic edit transaction; no partial or invalid model can escape."""
    raw = deepcopy(plan.model_dump(mode="json"))
    for edit in edits:
        if not edit.path:
            raise ValueError("field edit requires a nonempty path")
        target: Any = raw
        try:
            for part in edit.path[:-1]:
                target = target[part]
            final = edit.path[-1]
            if isinstance(target, dict) and final not in target:
                raise KeyError(final)
            target[final] = deepcopy(edit.value)
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"invalid edit path: {edit.path}") from exc
    return PlanSpec.model_validate(raw)


def reorder_rules(plan, order):
    rules = {r.id: r.model_dump(mode="json") for r in plan.rules}
    if len(order) != len(rules) or set(order) != rules.keys():
        raise ValueError("rule order must contain every rule exactly once")
    return edit_plan(plan, (FieldEdit(path=("rules",), value=[rules[i] for i in order]),))
