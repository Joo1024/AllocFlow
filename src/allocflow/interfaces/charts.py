import pandas as pd
import plotly.graph_objects as go

from allocflow.reporting.projections import tables


def wealth_chart(result):
    values = tables(result)["valuations"]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=values["date"],
            y=values["value"].astype(float),
            name="账户资产",
            line=dict(color="#147d64", width=3),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=values["date"],
            y=values["external_flow"].astype(float).cumsum(),
            name="本窗口净投入",
            line=dict(color="#819aab", dash="dot"),
        )
    )
    figure.update_layout(
        template="plotly_white",
        height=400,
        margin=dict(l=16, r=16, t=20, b=20),
        yaxis_title=result.report_currency,
        legend=dict(orientation="h"),
    )
    return figure


def nav_chart(result):
    values = tables(result)["valuations"]
    nav = pd.to_numeric(values["nav"], errors="coerce")
    figure = go.Figure(
        go.Scatter(x=values["date"], y=nav, name="单位净值", line=dict(color="#2563a5"))
    )
    figure.update_layout(template="plotly_white", height=300, margin=dict(l=16, r=16, t=20, b=20))
    return figure
