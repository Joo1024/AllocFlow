import plotly.graph_objects as go
from jinja2 import Environment, select_autoescape

from allocflow.reporting.projections import json_text

TEMPLATE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>{{ name }} · AllocFlow</title><style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 24px;color:#15312c}table{border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style>
<h1>{{ name }}</h1><p>AllocFlow · 报告币种 {{ currency }} · {{ source }}</p>
{{ chart | safe }}<h2>指标</h2><table><tr><th>指标</th><th>数值</th><th>状态</th></tr>
{% for key,m in metrics.items() if m is mapping %}<tr><td>{{ key }}</td><td>{{ m.value }}</td><td>{{ m.status }}</td></tr>{% endfor %}</table>
<h2>财富变化来源</h2><pre>{{ bridge }}</pre><h2>复现信息</h2><p>Dataset {{ dataset }}</p><p>Plan {{ fingerprint }}</p>
<p>事件与逐笔成交见同目录 CSV / Parquet / JSON。费用、FX和舍入已进入结果。</p>
<details><summary>完整配置</summary><pre>{{ plan }}</pre></details></html>"""


def render_report(result):
    from allocflow.analysis.comparison import wealth_bridge

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[v.date for v in result.valuations],
            y=[float(v.value) for v in result.valuations],
            name="账户资产",
        )
    )
    cumulative = 0.0
    flows = []
    for v in result.valuations:
        cumulative += float(v.external_flow)
        flows.append(cumulative)
    figure.add_trace(
        go.Scatter(
            x=[v.date for v in result.valuations], y=flows, name="净投入", line=dict(dash="dot")
        )
    )
    figure.update_layout(template="plotly_white", yaxis_title=result.report_currency)
    chart = figure.to_html(full_html=False, include_plotlyjs=True)
    env = Environment(autoescape=select_autoescape(default=True))
    return env.from_string(TEMPLATE).render(
        name=result.plan_name,
        bridge=json_text(wealth_bridge(result), indent=2),
        currency=result.report_currency,
        chart=chart,
        metrics=result.metrics,
        dataset=result.dataset_id,
        fingerprint=result.plan_fingerprint,
        source=result.manifest["dataset_metadata"].get("source", "unknown"),
        plan=json_text(result.manifest["plan"], indent=2),
    )
