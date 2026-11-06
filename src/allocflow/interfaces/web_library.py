import streamlit as st

from allocflow.application.errors import error_document
from allocflow.application.library import PlanLibrary
from allocflow.interfaces.web_editor import queue_plan


def render_library(text):
    st.subheader("本地计划库与运行历史")
    root = st.text_input("计划库目录", key="library_root")
    if not root:
        return
    library = PlanLibrary(root)
    name = st.text_input("保存为计划 ID（字母、数字、下划线或短横线）", key="library_name")
    if st.button("保存新版本", disabled=not text or not name):
        try:
            st.json(library.save(name, text))
        except (ValueError, OSError) as exc:
            st.error(error_document(exc))
    try:
        revisions = library.revisions()
        selected = st.selectbox(
            "选择已保存版本",
            revisions,
            index=None,
            format_func=lambda r: f"{r['name']} · {r['created_at']} · {r['revision'][:8]}",
        )
        if selected:
            if st.button("载入版本"):
                queue_plan(library.load(selected["name"], selected["revision"]))
            destination = st.text_input("复制到新计划 ID")
            if st.button("复制版本", disabled=not destination):
                st.json(library.copy(selected["name"], selected["revision"], destination))
            dataset = st.text_input(
                "此版本使用的数据集目录", value=st.session_state.get("dataset_path", "")
            )
            checkpoint = st.text_input("续跑检查点路径（留空表示从头运行）")
            if st.button("运行所选版本并保存记录", disabled=not dataset):
                metadata, result = library.run(
                    selected["name"],
                    selected["revision"],
                    dataset,
                    html=True,
                    checkpoint=checkpoint or None,
                )
                st.session_state["result"] = result
                st.json(metadata)
        st.dataframe(library.history(), hide_index=True)
    except (ValueError, OSError, ArithmeticError) as exc:
        st.error(error_document(exc))
