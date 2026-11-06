# Goal #3 — 可配置投资计划平台

[GitHub Goal #3](https://github.com/Joo1024/AllocFlow/issues/3)。开发分支 `dev/allocflow-v0.1`，PR #2 保持草稿，不合并 main。

六阶段按 1→2→3→4→5→6 实现并逐阶段测试。业务参数来自显式配置或命名 preset，用户策略不进入核心；v1 兼容开关只在 `config/evolution.py` 定义；v2 要求显式 controls 和 planning。

| 顺序 | 已交付 | 验证入口 |
|---|---|---|
| 1 | v1→v2 显式迁移、集中 preset、统一字段错误、YAML 语义往返、JSON Schema 条件必填 | test_contracts_v2 / test_stage_regressions |
| 2 | 全区间行情/信号/FX 检查、净值时点、真实快照与离线复现 | test_data_quality；LIVE-DATA-VALIDATION.md |
| 3 | 日期/月调度、AND/OR、冷却/次数/crossing、排名、订单上下限、预算竞争解释 | test_composition / test_rules |
| 4 | 资金表单、资产树、规则参数/顺序、保存/复制、不可变版本、运行历史、文件检查点续跑 | test_library / test_interfaces / test_completion |
| 5 | 日度预算/持仓/偏离、配对事件、财富桥、未交易原因 | test_comparison；CLI compare 和导出 |
| 6 | 阶段、通胀、提款边界、应急储备、目标、同路径继承、耗尽/缺口/计算失败区分 | test_planning / test_scenarios / test_stage_regressions |

本地 CLI 已实跑 preset 物化、数据质量检查、组合规则、生命周期 HTML 导出以及 5 条共同路径的两计划对比，5/5 配对完成。真实九资产与中国扩展计划均完成 2021–2023 回放。Web 模板载入与验证使用 Streamlit AppTest；业务编辑事务及计划库另有独立验证。

导出、检查点、未来数据扰动、手算费用、预算/现金/库存不变式和六个原模板继续覆盖。完整 pytest、Ruff、受约束模块的 mypy、wheel/sdist 打包作为提交门槛。mypy 当前覆盖 config/domain/Strategy 接口，不声称全部模块已严格类型化。

## 明确边界

- 累计净值不认证为红利再投资总回报；追溯复权不认证为历史时点可得数据。质量报告不会自动补齐上市前数据或改用代理资产。
- 净值基金仍采用可见净值与延迟执行研究模型。完整基金提交/确认/结算、税务、真实券商限制另设阶段。
- Web 常用字段使用表单，复杂条件与阶段可编辑 JSON 或完整 YAML；未制作任意条件拖拽设计器。
- YAML 往返保留全部模型值，不保留注释排版；计划库另外保留原始源文件。
- 财务目标是财富考核，不自动变成支出；真实支出使用显式提款现金流。
- 归因保留独立资产/FX/费用/现金流，换汇摩擦与舍入仍合并；事件差异不宣称规则级因果收益。
- 计划库为本地同步运行，不承诺后台守护任务或多用户服务。

用户后续验收和任何 main 合并均不属于本次自动操作。
