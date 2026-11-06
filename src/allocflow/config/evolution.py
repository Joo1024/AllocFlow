"""One visible compatibility policy; migration never changes an investment parameter."""

from copy import deepcopy
from typing import Any

# v1 predates composition and planning. These defaults ONLY disable new capabilities.
V1_COMPATIBILITY: dict[str, Any] = {"controls": [], "planning": None}
CURRENT_VERSION = "2"


def migrate_document(document, *, target_version):
    if target_version != CURRENT_VERSION:
        raise ValueError(f"unsupported migration target: {target_version}")
    if not isinstance(document, dict) or document.get("schema_version") not in {"1", "2"}:
        raise ValueError("migration requires a supported explicit schema_version")
    result = deepcopy(document)
    if result["schema_version"] == "1":
        for key, value in V1_COMPATIBILITY.items():
            result.setdefault(key, deepcopy(value))
        result["schema_version"] = CURRENT_VERSION
    return result
