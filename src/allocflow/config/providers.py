from datetime import date
from typing import Literal

from pydantic import Field

from allocflow.config.common import Currency, Identifier, NonNegative, Positive, Spec


class PriceSourceSpec(Spec):
    instrument: Identifier
    provider: Literal["yfinance", "akshare_equity", "akshare_etf", "akshare_fund"]
    symbol: str
    adjustment: Literal["auto_adjust", "hfq", "qfq", "cumulative_nav"]


class FXSourceSpec(Spec):
    currency: Currency
    symbol: str
    invert: bool


class ProviderRequest(Spec):
    schema_version: Literal["1"]
    start: date
    end: date
    base_currency: Currency
    timeout_seconds: Positive
    retry_attempts: int = Field(ge=1)
    retry_wait_seconds: NonNegative
    prices: tuple[PriceSourceSpec, ...]
    fx: tuple[FXSourceSpec, ...]
