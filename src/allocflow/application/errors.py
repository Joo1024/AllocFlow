from pydantic import ValidationError


def error_document(exc):
    """Identical machine-readable errors for SDK validation, CLI and Web."""
    issues = (
        [
            {"path": list(e["loc"]), "loc": list(e["loc"]), "code": e["type"], "message": e["msg"]}
            for e in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
        if isinstance(exc, ValidationError)
        else [{"path": [], "code": type(exc).__name__, "message": str(exc)}]
    )
    return {"status": "error", "type": type(exc).__name__, "details": issues}


def validate_document(text):
    from allocflow.config.loader import parse_plan, plan_fingerprint

    try:
        plan = parse_plan(text)
        return {
            "status": "valid",
            "fingerprint": plan_fingerprint(plan),
            "plan": plan.model_dump(mode="json"),
        }
    except (ValueError, TypeError) as exc:
        return error_document(exc)
