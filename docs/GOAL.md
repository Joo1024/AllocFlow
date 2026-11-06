# Goal：完成 AllocFlow v0.1 开发方案与首版验收

跟踪：https://github.com/Joo1024/AllocFlow/issues/1
开发分支：`dev/allocflow-v0.1`；审阅：https://github.com/Joo1024/AllocFlow/pull/2

交付一个以投资计划为核心、本地可运行且可复现的 Python 产品。用户参数通过显式 YAML、
公开模型和可信 Python 策略扩展表达；必填缺失报错。首版必要范围按下表验收，
可选研究功能与真实券商执行不纳入本轮。

## 需求、实现与验收

| 首版要求 | 实现位置 | 验收证据 |
|---|---|---|
| 显式配置、资产树、账户、预算、未知字段拒绝 | config/ | test_config.py |
| 用户精确计划；初始资金与月度分池区别 | examples/user_plan.yaml | test_economics.py |
| 现金/库存/预算守恒、原子拒绝、费用及舍入 | accounting/、execution/ | test_economics.py、test_review_regressions.py |
| 六模板、组合规则、阈值与选择器、预算上限 | policies/、examples/ | test_rules.py、test_integration.py |
| 固定金额和账户比例提款，缺口与拒绝回滚 | config/cashflows.py、accounting/flows.py | test_withdrawals.py、test_completion.py |
| 固定数据、日历、可知时点、多币种 | adapters/ | test_interfaces.py、test_integration.py |
| 单位化收益、XIRR状态、日度归因 | analysis/、engine/ | test_metrics.py、test_withdrawals.py、test_integration.py |
| 压力/联合路径、状态继承、失败统计 | application/scenarios.py | test_scenarios.py |
| SDK、CLI、Web、解释和报告 | interfaces/、reporting/ | test_interfaces.py及CLI离线完整运行 |
| 数据快照随结果导出、文件续跑、契约校验 | application/checkpoints.py、reporting/export.py | test_completion.py、test_review_regressions.py |
| 自定义策略参数在执行前验证 | policies/base.py、application/service.py | test_completion.py |
| 数据源输入映射、FX方向和来源标识 | adapters/providers.py | test_completion.py（离线替身；不等于真实服务认证） |

## 完成条件

- 必要能力实现并具备上述测试；完整套件、格式检查、静态检查通过。
- 可构建 wheel 和源码包；README 有安装、运行、导出和续跑步骤。
- 所有已知近似与外部服务验证边界公开记录。
- 实现提交到开发分支并更新 PR；用户验收和合并 main 是后续独立动作。

## 已知边界

本地Web以完整YAML编辑为主，这是首版配置入口；独立可视化参数表单不是本轮阻塞项。
场外基金使用延迟可见净值的研究模型；未知价申赎、真实资金结算、税务、实盘和原价公司行动留到后续。
联网行情适配器提供入口，实际服务的长期可用性与历史修订准确性不由本地测试保证。
skfolio、Optuna、DuckDB为可选研究分组，未作为首版必要功能实现。

见 docs/REVIEW.md 的验证结果与限制；Goal在用户验收前保持打开。

后续六阶段扩展由 [Goal #3](GOAL-SIX-STAGES.md) 单独跟踪；首版的开发分支与不合并 main 的约束继续有效。
