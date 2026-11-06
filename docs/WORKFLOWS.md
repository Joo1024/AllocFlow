# 本地计划、运行与解释

Web 的计划页提供常用资金表单、资产树、规则顺序以及规则/组合/阶段 JSON 编辑。完整 YAML 保留全部能力；每次表单提交以一个事务验证，错误时原计划不变。

“计划库”页的目录由用户指定。保存创建不可变版本，保留源 YAML 与指纹；可以复制为新计划、加载旧版本、运行并查看历史或指定 checkpoint 续跑。运行同步执行，进程被杀时 running 记录不会伪装成成功。输出保留完整快照、检查点和状态；失败记录保留结构化错误。

```bash
uv run allocflow library save work/library my-plan --plan examples/user_plan.yaml
uv run allocflow library list work/library
# 使用 list 返回的 revision：
uv run allocflow library copy work/library my-plan REVISION my-copy
uv run allocflow library run work/library my-plan REVISION --dataset work/demo-market --no-html
uv run allocflow library history work/library
```

运行导出新增 `budgets`、`drift`、`non_trades` CSV/Parquet：预算原币余额、扣除挂单与储备后的可用额、报告币值；每个资产实际权重与目标偏离；零意图决策和拒绝原因。持仓表含数量。总资产权重中的现金不算股票持仓，因此股票预算 60% 不表示每一天实际股票仓位 60%。

`compare` 输出日度财富差异、配对事件、第一处事件差异及财富桥。正差额方向明确是“右计划减左计划”。财富桥核对：期初财富＋净外部现金流＋资产价格效应＋汇率效应＋利息－费用－换汇摩擦与舍入＋算术残差＝期末财富。外部现金流不等于投资收益。

实际提款金额可能随路径与策略不同，因此报告另标注实际现金流是否相等。事件差异是执行证据，不声称单条规则产生了可独立分离的因果收益。换汇摩擦与舍入仍合并报告；不同归因顺序可能对资产/FX交互项采用不同分摊方式，这里沿用资产价格变化用期末汇率、旧资产值用汇率变化的口径。

## Review 后的指标与恢复契约

顶层指标现在统一使用本次窗口，scope 明确起止及期初财富；累计指标放在 since_inception。严格 compare 同时核对完整现金流政策和实际支付结果。检查点 v2 锁定资产身份与估值口径，SDK initial_state 也遵守同一契约。详见 [修复说明](REVIEW-FIXES.md)。
