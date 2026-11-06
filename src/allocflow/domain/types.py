from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class BuyIntent:
    rule_id: str
    budget: str
    instrument: str
    maximum_cash: Decimal
    reason: str


@dataclass(frozen=True)
class SellIntent:
    rule_id: str
    budget: str
    instrument: str
    quantity: Decimal
    reason: str


@dataclass(frozen=True)
class TransferIntent:
    rule_id: str
    source: str
    destination: str
    amount: Decimal
    reason: str


Intent = BuyIntent | SellIntent | TransferIntent


@dataclass(frozen=True)
class Event:
    sequence: int
    date: date
    kind: str
    rule: str
    status: Literal["filled", "rejected", "info", "pending"]
    details: dict


@dataclass(frozen=True)
class PendingIntent:
    submitted: date
    due: date
    intent: Intent


@dataclass
class AccountState:
    cash: dict[str, Decimal] = field(default_factory=dict)
    budgets: dict[str, Decimal] = field(default_factory=dict)
    holdings: dict[str, Decimal] = field(default_factory=dict)
    units: Decimal = ZERO
    last_nav: Decimal | None = None
    events: list[Event] = field(default_factory=list)
    pending: list[PendingIntent] = field(default_factory=list)
    rule_state: dict[str, dict] = field(default_factory=dict)
    latest_inflows: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    external_flows: list[tuple[date, Decimal]] = field(default_factory=list)
    last_date: date | None = None

    def record(self, day: date, kind: str, rule: str, status: str, **details):
        self.events.append(Event(len(self.events) + 1, day, kind, rule, status, details))  # type: ignore[arg-type]


@dataclass(frozen=True)
class Valuation:
    date: date
    value: Decimal
    nav: Decimal | None
    units: Decimal
    external_flow: Decimal
    return_: Decimal | None
    holdings_value: dict[str, Decimal]
    cash_value: Decimal
    attribution: dict[str, Decimal]
    budget_balances: dict[str, Decimal]
    budget_spendable: dict[str, Decimal]
    budget_values: dict[str, Decimal]
    quantities: dict[str, Decimal]


@dataclass
class RunResult:
    plan_name: str
    report_currency: str
    dataset_id: str
    plan_fingerprint: str
    valuations: list[Valuation]
    final_state: AccountState
    metrics: dict
    manifest: dict

    dataset_artifacts: dict[str, bytes] = field(default_factory=dict)
