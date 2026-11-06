from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class Observation:
    date: date
    available_on: date
    value: Decimal


class MarketData(Protocol):
    dataset_id: str
    base_currency: str
    metadata: Mapping[str, Any]

    def with_staleness_policy(self, max_stale_days: int) -> "MarketData": ...

    def price(self, instrument: str, day: date, *, visible: bool = False) -> Decimal: ...

    def fx(self, source: str, target: str, day: date) -> Decimal: ...

    def history(self, instrument: str, before: date) -> tuple[Decimal, ...]: ...

    def price_observations(self, instrument: str) -> Sequence[Observation]: ...

    def fx_observations(self, currency: str) -> Sequence[Observation]: ...

    def fx_currencies(self) -> tuple[str, ...]: ...

    def export_artifacts(self) -> Mapping[str, bytes]: ...
