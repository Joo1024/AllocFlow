import streamlit as st
import yaml

from allocflow.application.errors import error_document
from allocflow.config.loader import UniqueKeyLoader, load_plan
from allocflow.reporting.projections import json_text


def render_forecast(plan, files, scenario_text):
    st.subheader("长期规划与同路径比较")
    result = st.session_state.get("result")
    if result:
        st.json(result.manifest.get("planning_outcomes"))
    alternatives = st.multiselect(
        "对比计划（相同资产与区间，允许提款政策不同）",
        files,
        format_func=lambda p: p.stem,
        key="forecast_alternatives",
    )
    checkpoint = st.text_input("继承账户的检查点路径（可选）", key="forecast_checkpoint")
    if st.button(
        "使用同一组路径比较长期计划",
        disabled=plan is None or not alternatives or not scenario_text.strip(),
    ):
        try:
            from allocflow.adapters.dataset import MarketDataset
            from allocflow.application.checkpoints import load_checkpoint
            from allocflow.application.forecast import compare_scenarios
            from allocflow.config.scenarios import ScenarioSpec

            spec = ScenarioSpec.model_validate(yaml.load(scenario_text, Loader=UniqueKeyLoader))
            market = MarketDataset.load(
                st.session_state.dataset_path, max_stale_days=plan.execution.max_stale_days
            )
            state = load_checkpoint(checkpoint, plan) if checkpoint else None
            summary = compare_scenarios(
                [plan, *[load_plan(p) for p in alternatives]], market, spec, initial_state=state
            )
            st.json(summary)
            st.download_button(
                "下载配对规划结果",
                json_text(summary, indent=2),
                file_name="forecast-comparison.json",
            )
        except (ValueError, OSError, ArithmeticError, ImportError) as exc:
            st.error(error_document(exc))
