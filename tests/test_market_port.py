from allocflow.application.service import run_plan
from allocflow.domain.market import MarketData


class PortOnlyMarket:
    """Expose precisely the protocol; no prices/rates attributes or mutable policy."""

    __slots__ = ("_inner",)

    def __init__(self, inner):
        self._inner = inner

    @property
    def dataset_id(self):
        return self._inner.dataset_id

    @property
    def base_currency(self):
        return self._inner.base_currency

    @property
    def metadata(self):
        return self._inner.metadata

    def with_staleness_policy(self, max_stale_days):
        return PortOnlyMarket(self._inner.with_staleness_policy(max_stale_days))

    def price(self, instrument, day, *, visible=False):
        return self._inner.price(instrument, day, visible=visible)

    def fx(self, source, target, day):
        return self._inner.fx(source, target, day)

    def history(self, instrument, before):
        return self._inner.history(instrument, before)

    def price_observations(self, instrument):
        return self._inner.price_observations(instrument)

    def fx_observations(self, currency):
        return self._inner.fx_observations(currency)

    def fx_currencies(self):
        return self._inner.fx_currencies()

    def export_artifacts(self):
        return {}


def test_sdk_accepts_declared_market_protocol_only(plan, flat_market):
    port: MarketData = PortOnlyMarket(flat_market)
    result = run_plan(plan, port)
    original = run_plan(plan, flat_market)
    assert result.valuations == original.valuations
    assert flat_market.max_stale_days == 10
