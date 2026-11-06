import json

import streamlit as st

from allocflow.application.errors import error_document
from allocflow.config.editing import FieldEdit, edit_plan, reorder_rules
from allocflow.config.loader import dump_plan


def queue_plan(text):
    st.session_state["pending_plan_yaml"] = text
    st.rerun()


def render_editor(plan):
    with st.expander("表单编辑 · 计划 / 资金 / 配置树 / 规则"):
        with st.form("structured_editor"):
            name = st.text_input("计划名称", value=plan.name)
            start = st.date_input("开始", value=plan.start)
            end = st.date_input("结束", value=plan.end)
            currency = st.text_input("报告币种", value=plan.report_currency)
            flow_values = []
            for f in plan.cashflows:
                st.caption(f"现金流 {f.id} · {f.direction} · {f.money.currency}")
                amount = st.text_input(
                    "金额（十进制）", value=str(f.money.amount), key=f"amount_{f.id}"
                )
                growth = st.text_input("年增长率", value=str(f.annual_growth), key=f"growth_{f.id}")
                flow_values.append((amount, growth))
            allocation = st.text_area(
                "资产树 JSON（节点、权重和叶资产）",
                value=json.dumps(
                    plan.allocation.model_dump(mode="json"), ensure_ascii=False, indent=2
                ),
                height=200,
            )
            order = st.text_input(
                "规则执行顺序（逗号分隔 ID）", value=",".join(r.id for r in plan.rules)
            )
            advanced = st.text_area(
                "规则、组合条件与长期规划 JSON",
                value=json.dumps(
                    {
                        "rules": [r.model_dump(mode="json") for r in plan.rules],
                        "controls": [c.model_dump(mode="json") for c in plan.controls],
                        "planning": plan.planning.model_dump(mode="json")
                        if plan.planning
                        else None,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                height=240,
            )
            st.caption(
                "提交时原子验证所有修改；规则 ID 有变化时，请同步修改执行顺序。其他字段可在完整 YAML 中编辑。"
            )
            submitted = st.form_submit_button("应用表单并生成完整 YAML")
        if submitted:
            try:
                edits = [
                    FieldEdit(path=(k,), value=v)
                    for k, v in {
                        "name": name,
                        "start": start,
                        "end": end,
                        "report_currency": currency,
                        "allocation": json.loads(allocation),
                    }.items()
                ]
                changes = json.loads(advanced)
                if not isinstance(changes, dict) or set(changes) != {
                    "rules",
                    "controls",
                    "planning",
                }:
                    raise ValueError("高级编辑须包含 rules、controls 和 planning")
                edits.extend(FieldEdit(path=(key,), value=value) for key, value in changes.items())
                for i, (amount, growth) in enumerate(flow_values):
                    edits.extend(
                        [
                            FieldEdit(path=("cashflows", i, "money", "amount"), value=amount),
                            FieldEdit(path=("cashflows", i, "annual_growth"), value=growth),
                        ]
                    )
                updated = reorder_rules(
                    edit_plan(plan, tuple(edits)),
                    [i.strip() for i in order.split(",") if i.strip()],
                )
                queue_plan(dump_plan(updated))
            except (ValueError, TypeError) as exc:
                st.error(error_document(exc))
