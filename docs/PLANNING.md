# 生命周期与长期规划

`examples/plans/lifecycle.yaml` 示范积累期→退休期，和原定投模板共用同一引擎。阶段连续、有序、不重叠，并覆盖运行区间。每阶段列明启用的现金流 ID 和规则 ID；阶段切换不会重置持仓、预算、净值或规则记忆。已经排队的订单仍执行。

`planning.inflation` 显式指定基准日、年率、ACT/365F 或 ACT/360 和索引现金流。使用 `(1+年率)^(实际天数/年天数)`。被索引的现金流必须关闭原 annual_growth，比例提款不能再次按通胀放大。`real_terminal_value` 表示报告币种在该单一通胀假设下的基准日购买力，不是多国 CPI 模型。

提款先按固定/组合比例计算，再在指定币种转换后的最低和最高金额之间限幅；上下限可按同一通胀因子调整。资金不足按计划的 partial/reject 处理。原子拒绝时实际未满足金额是完整请求，另记录 liquidity_gap 表示试算的流动性缺口。

应急储备绑定预算，金额用预算币种。余额不足时记录缺口，不凭空补足资金；投资和预算转移不能耗用保留金额。`protect_from_withdrawals` 显式决定提款能否耗用储备。挂单会锁定金额；通胀导致保留额增加时，待执行买单重新检查可用预算。

目标是账户总财富考核，不自动产生支出。需要大额支出时仍显式配置 withdrawal cashflow。目标在目标日之前最后一个运行交易日收盘评估，事件给出目标、账户值和缺口；目标日早于首个估值日时没有可观察结果。续跑只评估该窗口内的目标，其他目标可继续留在完整阶段配置中。

```bash
uv run allocflow run --plan examples/plans/lifecycle.yaml --dataset work/demo-market --output runs/lifecycle --html
uv run allocflow forecast-compare --plans examples/user_plan.yaml --plans examples/plans/lifecycle.yaml --dataset work/demo-market --spec examples/scenarios.yaml --output work/paired-forecast.json
```

`compare_scenarios` 每条路径只生成一次，然后让所有计划从同一账户状态独立运行。比较要求相同资产定义、区间、报告币种和日历；允许未来现金流不同。传入 `initial_state` 或 CLI `--checkpoint` 可继承账户；续跑 start 必须晚于检查点日期，预算/币种契约必须兼容。

配对报告逐路径给出缺口、首次耗尽日期、储备不足、目标达成和期末差额。账户为零与提款未满足是独立事件；有受保护储备时可能提款失败但账户未耗尽。计算失败单列，概率分母是计算成功的配对路径；缺少完整目标观察时不声称目标达成概率。区块重采样为研究情景，不是未来收益概率保证。

延迟净值基金仍不能用于当天提款；完整提交、未知净值确认和结算账务是后续独立阶段。
