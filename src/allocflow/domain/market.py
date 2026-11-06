from datetime import date
from decimal import Decimal
from typing import Protocol


class MarketData(Protocol):
    dataset_id: str
    base_currency: str

    def price(self, instrument: str, day: date, *, visible: bool = False) -> Decimal: ...

    def fx(self, source: str, target: str, day: date) -> Decimal: ...

    def history(self, instrument: str, before: date) -> tuple[Decimal, ...]: ...
