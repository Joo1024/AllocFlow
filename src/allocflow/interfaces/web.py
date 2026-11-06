from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

from allocflow.adapters.dataset import MarketDataset
from allocflow.application.service import compare_plans, run_plan
from allocflow.config.loader import UniqueKeyLoader, load_plan, parse_plan
from allocflow.config.plan import PlanSpec
from allocflow.interfaces.charts import nav_chart, wealth_chart
from allocflow.reporting.export import export_run
from allocflow.reporting.projections import json_text, tables


def show_error(exc):
    st.error(str(exc))


def plan_files():
    folder = Path(__file__).resolve().parents[3] / "examples"
    return [
        p
        for p in sorted(folder.glob("*.yaml"))
        if p.stem not in {"demo_data", "scenarios", "stress", "providers"}
    ]


def main():
    st.set_page_config(page_title="AllocFlow · 投资计划实验室", page_icon="◈", layout="wide")
    st.markdown(
        """<style>.block-container{padding-top:2rem;max-width:1500px}h1{letter-spacing:-.04em}div[data-testid=stMetric]{background:#f1f7f5;padding:18px;border-radius:10px}section[data-testid=stSidebar]{background:#edf4f1}</style>""",
        unsafe_allow_html=True,
    )
    st.caption("ALLOCFLOW / 本地投资计划实验室")
    st.title("让资金计划，经得起时间检验。")
    st.write("定义投入与提款、资产配置和投资规则，在同一条市场路径上理解计划如何演变。")
    files = plan_files()
    with st.sidebar:
        st.header("投资计划")
        chosen = st.selectbox(
            "选择具名模板",
            files,
            index=None,
            format_func=lambda p: p.stem,
            placeholder="请选择，或上传 YAML",
        )
        if st.button("载入模板", disabled=chosen is None):
            st.session_state["plan_yaml"] = chosen.read_text(encoding="utf-8")
            st.session_state.pop("plan_editor", None)
        upload = st.file_uploader("上传计划 YAML", type=["yaml", "yml"])
        if upload is not None and st.button("载入上传文件"):
            st.session_state["plan_yaml"] = upload.getvalue().decode("utf-8")
            st.session_state.pop("plan_editor", None)
        st.info("阈值、金额、预算、执行顺序和费用都来自计划 YAML。未填写必填字段会直接报错。")
        st.caption("这是本地研究模拟器。合成数据仅供功能演示。")

    tabs = st.tabs(["01 计划", "02 数据", "03 运行与比较", "04 事件解释", "05 情景与导出"])
    plan = None
    with tabs[0]:
        st.subheader("计划规格")
        text = st.text_area(
            "完整 YAML，可直接编辑所有策略参数",
            value=st.session_state.get("plan_yaml", ""),
            height=500,
            key="plan_editor",
        )
        if text.strip():
            try:
                plan = parse_plan(text)
                st.success(
                    f"配置有效 · {plan.name} · {len(plan.instruments)} 个资产 · {len(plan.rules)} 条有序规则"
                )
                st.download_button(
                    "下载当前计划", text, file_name="plan.yaml", mime="application/yaml"
                )
                with st.expander("目标权重与规则顺序"):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {"资产": i, "目标权重": float(w)}
                                for i, w in plan.allocation.leaves().items()
                            ]
                        ),
                        hide_index=True,
                    )
                    st.write([f"{r.id} · {r.kind} · {r.schedule}" for r in plan.rules])
            except (ValueError, TypeError) as exc:
                show_error(exc)
        st.download_button(
            "下载计划 JSON Schema",
            json_text(PlanSpec.model_json_schema(), indent=2),
            file_name="plan.schema.json",
        )

    with tabs[1]:
        st.subheader("固定数据快照")
        st.text_input("数据集目录（manifest.json、prices.csv、fx.csv）", key="dataset_path")
        if st.button("检查数据集", disabled=plan is None):
            try:
                market = MarketDataset.load(
                    st.session_state.dataset_path, max_stale_days=plan.execution.max_stale_days
                )
                st.json(market.metadata)
            except (ValueError, OSError) as exc:
                show_error(exc)
        st.markdown("**生成离线演示数据**")
        demo_text = st.text_area(
            "合成数据参数 YAML（可从 examples/demo_data.yaml 复制）", height=180, key="demo_spec"
        )
        if st.button("生成到上述目录", disabled=plan is None or not demo_text.strip()):
            try:
                import yaml

                from allocflow.adapters.demo import DemoSpec, create_demo_dataset

                spec = DemoSpec.model_validate(yaml.load(demo_text, Loader=UniqueKeyLoader))
                create_demo_dataset(plan, spec, st.session_state.dataset_path)
                st.success("合成数据已生成；并非历史行情。")
            except (ValueError, OSError) as exc:
                show_error(exc)
        st.caption("真实数据可通过 CLI download 或规范 CSV 导入。快照哈希会在运行前校验。")

    with tabs[2]:
        if st.button(
            "运行当前计划",
            type="primary",
            disabled=plan is None or not st.session_state.get("dataset_path"),
        ):
            try:
                with st.spinner("执行计划并核对账本…"):
                    st.session_state["result"] = run_plan(plan, st.session_state.dataset_path)
            except (ValueError, OSError, ArithmeticError) as exc:
                show_error(exc)
        result = st.session_state.get("result")
        if result:
            st.caption(
                f"已完成的运行：{result.plan_name} · 配置指纹 {result.plan_fingerprint[:16]}"
            )
            if "SYNTHETIC" in result.manifest["dataset_metadata"].get("source", ""):
                st.warning("当前结果基于合成数据，仅用于验证软件行为。")
            columns = st.columns(4)
            for column, key, label, percent in zip(
                columns,
                ["terminal_value", "cash_profit", "twr", "max_drawdown"],
                ["期末资产", "现金盈亏", "时间加权收益", "日度最大回撤"],
                [False, False, True, True],
                strict=True,
            ):
                value = result.metrics[key]["value"]
                column.metric(
                    label,
                    "不可计算"
                    if value is None
                    else (f"{value:.2%}" if percent else f"{value:,.2f} {result.report_currency}"),
                )
            st.plotly_chart(wealth_chart(result), width="stretch")
            st.plotly_chart(nav_chart(result), width="stretch")
        compare = st.multiselect(
            "比较其他模板（要求相同外部现金流、区间和报告币种）",
            files,
            format_func=lambda p: p.stem,
        )
        if st.button("运行比较", disabled=plan is None or not compare):
            try:
                compared = compare_plans(
                    [plan, *[load_plan(p) for p in compare]], st.session_state.dataset_path
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "计划": r.plan_name,
                                "期末资产": r.metrics["terminal_value"]["value"],
                                "TWR": r.metrics["twr"]["value"],
                            }
                            for r in compared
                        ]
                    ),
                    hide_index=True,
                )
            except (ValueError, OSError, ArithmeticError) as exc:
                show_error(exc)

    with tabs[3]:
        result = st.session_state.get("result")
        if result:
            event_table = tables(result)["events"]
            rule = st.selectbox("按规则筛选事件", ["全部", *sorted(event_table["rule"].unique())])
            if rule != "全部":
                event_table = event_table[event_table["rule"] == rule]
            st.dataframe(event_table, hide_index=True, width="stretch")
            if not event_table.empty:
                sequence = st.selectbox("查看事件证据", event_table["sequence"].tolist())
                event = next(e for e in result.final_state.events if e.sequence == sequence)
                st.code(json_text(asdict(event), indent=2), language="json")
            with st.expander("逐日归因"):
                st.dataframe(tables(result)["attribution"], hide_index=True)
        else:
            st.info("运行计划后，可查看规则参数、触发理由、预算、成交和拒绝原因。")

    with tabs[4]:
        scenario_text = st.text_area(
            "情景规格 YAML（examples/scenarios.yaml 或 stress.yaml）", height=200
        )
        if st.button("运行情景", disabled=plan is None or not scenario_text.strip()):
            try:
                import yaml

                from allocflow.application.scenarios import run_scenarios
                from allocflow.config.scenarios import ScenarioSpec

                spec = ScenarioSpec.model_validate(yaml.load(scenario_text, Loader=UniqueKeyLoader))
                market = MarketDataset.load(
                    st.session_state.dataset_path, max_stale_days=plan.execution.max_stale_days
                )
                with st.spinner("运行独立路径…"):
                    summary = run_scenarios(plan, market, spec)
                summary["paths"] = [
                    {**r, "events": [asdict(e) for e in r.get("events", [])]}
                    for r in summary["paths"]
                ]
                st.json(summary)
                st.download_button(
                    "下载情景结果", json_text(summary, indent=2), file_name="scenarios.json"
                )
            except (ValueError, OSError, ArithmeticError, ImportError) as exc:
                show_error(exc)
        if result:
            st.text_input("导出到新目录", key="export_path")
            if st.button("导出运行包", disabled=not st.session_state.get("export_path")):
                try:
                    export_run(result, st.session_state.export_path, html=True)
                    st.success("已导出 HTML、CSV、Parquet、配置与运行信息。")
                except (ValueError, OSError) as exc:
                    show_error(exc)


if __name__ == "__main__":
    main()
