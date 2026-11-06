"""Versioned, integrity-checked account checkpoints for explicit continuation."""

import hashlib
import json
from dataclasses import asdict, fields
from datetime import date
from decimal import Decimal
from pathlib import Path

from allocflow.accounting.book import Book
from allocflow.domain.types import (
    AccountState,
    BuyIntent,
    Event,
    PendingIntent,
    SellIntent,
    TransferIntent,
)
from allocflow.reporting.projections import json_default


def account_contract(plan):
    raw = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
    return dict(
        report_currency=raw["report_currency"],
        instruments={
            i["id"]: {k: i[k] for k in ["currency", "quantity_step"]} for i in raw["instruments"]
        },
        budgets={b["id"]: b["currency"] for b in raw["budgets"]},
    )


def canonical(value):
    return json.dumps(
        value, default=json_default, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def checkpoint_document(result):
    payload = dict(
        schema_version="1",
        account_contract=account_contract(result.manifest["plan"]),
        state=asdict(result.final_state),
    )
    return {**payload, "sha256": hashlib.sha256(canonical(payload).encode()).hexdigest()}


def decimal(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("checkpoint numbers must be finite")
    return result


def money_map(value):
    return {k: decimal(v) for k, v in value.items()}


def load_checkpoint(path, plan):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "account_contract",
        "state",
        "sha256",
    }:
        raise ValueError("checkpoint document schema mismatch")
    expected = document.pop("sha256")
    if hashlib.sha256(canonical(document).encode()).hexdigest() != expected:
        raise ValueError("checkpoint integrity mismatch")
    if document["schema_version"] != "1" or document["account_contract"] != account_contract(plan):
        raise ValueError("checkpoint account/currency contract mismatch")
    raw = document["state"]
    if set(raw) != {f.name for f in fields(AccountState)}:
        raise ValueError("checkpoint state schema mismatch")
    numeric = {
        "target_report",
        "value_report",
        "gap_report",
        "target",
        "balance",
        "gap",
        "liquidity_gap",
        "amount",
        "requested",
        "shortfall",
        "external_report",
        "fee_report",
        "fee",
        "price",
        "quantity",
        "cash_change",
        "fx_and_rounding_report",
        "interest_report",
        "credit",
        "nav_for_flow",
    }
    events = []
    for event in raw["events"]:
        details = dict(event["details"])
        for key in numeric & details.keys():
            if details[key] is not None:
                details[key] = decimal(details[key])
        for key in ["distributions", "available_budgets"]:
            if key in details:
                details[key] = money_map(details[key])
        events.append(
            Event(
                event["sequence"],
                date.fromisoformat(event["date"]),
                event["kind"],
                event["rule"],
                event["status"],
                details,
            )
        )
    pending = []
    for row in raw["pending"]:
        intent = dict(row["intent"])
        if "maximum_cash" in intent:
            intent["maximum_cash"] = decimal(intent["maximum_cash"])
            action = BuyIntent(**intent)
        elif "quantity" in intent:
            intent["quantity"] = decimal(intent["quantity"])
            action = SellIntent(**intent)
        else:
            intent["amount"] = decimal(intent["amount"])
            action = TransferIntent(**intent)
        pending.append(
            PendingIntent(
                date.fromisoformat(row["submitted"]), date.fromisoformat(row["due"]), action
            )
        )
    state = AccountState(
        cash=money_map(raw["cash"]),
        budgets=money_map(raw["budgets"]),
        holdings=money_map(raw["holdings"]),
        units=decimal(raw["units"]),
        last_nav=decimal(raw["last_nav"]) if raw["last_nav"] is not None else None,
        events=events,
        pending=pending,
        rule_state=raw["rule_state"],
        latest_inflows={k: money_map(v) for k, v in raw["latest_inflows"].items()},
        external_flows=[(date.fromisoformat(d), decimal(a)) for d, a in raw["external_flows"]],
        last_date=date.fromisoformat(raw["last_date"]) if raw["last_date"] else None,
    )
    if not set(state.budgets) <= {b.id for b in plan.budgets} or not set(state.holdings) <= {
        i.id for i in plan.instruments
    }:
        raise ValueError("checkpoint contains unknown budget or instrument")
    Book(plan, None, state).assert_invariants()
    return state
