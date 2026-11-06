import inspect
from datetime import UTC, datetime, timedelta

import pandas as pd

from allocflow.adapters.calendar import next_session
from allocflow.adapters.dataset import save_dataset


def _history(symbol, request):
    import yfinance as yf

    return yf.Ticker(symbol).history(
        start=request.start.isoformat(),
        end=(request.end + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        actions=False,
        repair=False,
        timeout=float(request.timeout_seconds),
    )


def _prices(source, request):
    if source.provider == "yfinance":
        if source.adjustment != "auto_adjust":
            raise ValueError("yfinance adapter requires explicit auto_adjust")
        frame = _history(source.symbol, request)
        return [(d.date(), float(v)) for d, v in frame["Close"].items()]
    import akshare as ak

    if source.provider == "akshare_fund":
        if source.adjustment != "cumulative_nav":
            raise ValueError("fund adapter requires explicitly selected cumulative_nav")
        frame = ak.fund_open_fund_info_em(symbol=source.symbol, indicator="累计净值走势")
        return [
            (pd.Timestamp(d).date(), float(v))
            for d, v in zip(frame["净值日期"], frame["累计净值"], strict=True)
        ]
    if source.adjustment not in {"hfq", "qfq"}:
        raise ValueError("Chinese equity/ETF adapter requires hfq or qfq")
    method = ak.stock_zh_a_hist if source.provider == "akshare_equity" else ak.fund_etf_hist_em
    kwargs = dict(
        symbol=source.symbol,
        period="daily",
        start_date=request.start.strftime("%Y%m%d"),
        end_date=request.end.strftime("%Y%m%d"),
        adjust=source.adjustment,
    )
    if "timeout" in inspect.signature(method).parameters:
        kwargs["timeout"] = float(request.timeout_seconds)
    frame = method(**kwargs)
    return [
        (pd.Timestamp(d).date(), float(v))
        for d, v in zip(frame["日期"], frame["收盘"], strict=True)
    ]


def download_dataset(plan, request, output):
    """Freeze source output before simulation; no provider session reaches the engine."""
    import requests
    from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

    if request.end < request.start:
        raise ValueError("provider request end precedes start")
    instruments = {i.id: i for i in plan.instruments}
    if {s.instrument for s in request.prices} != instruments.keys() or len(request.prices) != len(
        instruments
    ):
        raise ValueError("provider request must name each plan instrument exactly once")
    retry = Retrying(
        stop=stop_after_attempt(request.retry_attempts),
        wait=wait_fixed(float(request.retry_wait_seconds)),
        retry=retry_if_exception_type(
            (ConnectionError, TimeoutError, requests.exceptions.RequestException)
        ),
        reraise=True,
    )
    currencies = {i.currency for i in plan.instruments} | {b.currency for b in plan.budgets}
    currencies |= {f.money.currency for f in plan.cashflows} | {
        plan.report_currency,
        plan.execution.fee.fixed_currency,
    }
    supplied = [f.currency for f in request.fx]
    if len(supplied) != len(set(supplied)):
        raise ValueError("duplicate FX source currency")
    if not (currencies - {request.base_currency}) <= set(supplied):
        raise ValueError("provider request missing required FX currencies")
    rows = []
    for source in request.prices:
        spec = instruments[source.instrument]
        if spec.price_mode != "provider_adjusted_synthetic":
            raise ValueError(
                "download adapters do not certify total-return semantics; use provider_adjusted_synthetic"
            )
        pairs = retry(_prices, source, request)
        pairs = [(day, value) for day, value in pairs if request.start <= day <= request.end]
        if not pairs:
            raise ValueError(f"empty provider response: {source.instrument}")
        for day, price in pairs:
            if request.start <= day <= request.end:
                available = (
                    next_session(spec.calendar, day, 1) if spec.pricing == "available_nav" else day
                )
                rows.append(
                    dict(instrument=spec.id, date=day, available_on=available, value=str(price))
                )
    rates = []
    for source in request.fx:
        frame = retry(_history, source.symbol, request)
        if frame.empty:
            raise ValueError(f"empty FX provider response: {source.currency}")
        for stamp, price in frame["Close"].items():
            value = 1 / float(price) if source.invert else float(price)
            rates.append(
                dict(
                    currency=source.currency,
                    date=stamp.date(),
                    available_on=stamp.date(),
                    value=str(value),
                )
            )
    if not rates:
        rates.append(
            dict(
                currency=request.base_currency,
                date=request.start,
                available_on=request.start,
                value="1",
            )
        )
    save_dataset(
        output,
        pd.DataFrame(rows),
        pd.DataFrame(rates),
        dict(
            schema_version="1",
            base_currency=request.base_currency,
            source="retrospective_provider_download",
            fetched_at=datetime.now(UTC).isoformat(),
            availability_basis="assumed session close / next-session fund publication; retrospective, not certified point-in-time",
            instruments={i.id: i.price_mode for i in plan.instruments},
            provider_request=request.model_dump(mode="json"),
            notes="Source adjustment and cumulative NAV are not certified reinvested total returns. AKShare timeout only where source API supports it.",
        ),
    )
