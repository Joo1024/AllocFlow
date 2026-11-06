# 配置与扩展接口 v2

`PlanSpec` 是 SDK、CLI、Web、JSON Schema 的共同契约。业务模型禁止未知字段，Decimal 金额导出为字符串，引用、树权重和规则顺序均在运行前验证。用户参数集中在完整 YAML 或命名 preset 中，不由引擎推断。

## 版本和错误

新计划使用 `schema_version: '2'`，必须显式写 `controls: []` 和 `planning: null` 或相应配置。v1 仍可读取；只有 `config/evolution.py` 的 `V1_COMPATIBILITY` 负责将这两个新增能力解释为关闭。v1 不能偷偷启用 v2 能力。

```bash
uv run allocflow migrate --plan old-plan.yaml --target-version 2 --output migrated.yaml
uv run allocflow materialize --catalog examples/presets/catalog.yaml --name zero-fee-study --output work/resolved.yaml
```

迁移显式执行，不覆盖原文件、不改投资参数。Preset 只能继承同一目录文档中的具名条目：映射递归合并，列表整体替换。循环、未知名称和不完整最终计划报错。物化后完整参数进入计划指纹与运行清单。当前只有 v1→v2 迁移，未知版本拒绝处理。

`application.errors.validate_document(text)` 返回结构化验证结果。错误 `details` 包含 `path/code/message`；`loc` 保留原 CLI 兼容字段。运行接口仍抛异常，CLI 以退出码 2 输出相同错误结构，Web 也展示该结构。

`dump_plan(parse_plan(text))` 保留所有模型值及 Decimal 精度，不保留 YAML 注释、锚点或排版；计划库另外保存未经改写的 `source.yaml` 和规范化的 `resolved.yaml`。

## 规则组合

见 `examples/plans/composed.yaml`。控制配置通过 `rule` 关联有序规则，可用于所有规则的日期/月过滤、AND/OR 条件、冷却、次数和 crossing 重置。投资规则另支持 momentum/underweight 排序、最大标的数、单笔最低预算、总部署上限、保留余额。

条件量纲：`budget` 使用对应预算币种；`total_value` 使用报告币种；`weight/drift/drawdown` 使用比例，drift 是实际持仓权重减目标权重。所有行情条件只看执行日前可见数据。未知引用立即报错；排名所需历史不足的资产排除。

条件按原规则调度时点观察。`crossing` 表示所观察条件从假变真；观察状态即使没有成交也更新。`cooldown_days` 是日历日。`max_fires` 只在至少一个意图即时成交或成功排队后增加；排队后因资金/价格变化拒绝成交，也已消耗一次触发机会。是否采用这样的规则由用户显式选择。

先选合格资产，再排序与限制数量；部署总额按所选资产原分配比例重分配，单笔低于下限则移除，不把移除金额再分配。费用包含在买单金额上限中。控制金额都是 source_budget 币种；非投资规则的金额/排序控制必须保持禁用值，否则报错。

规则按 YAML 顺序竞争预算，每条规则重新读取前序交易与挂单后的可用资金。事件保留执行优先级、可用预算、条件参数、未产生订单或拒绝理由。预算控制不允许透支或重复使用挂单资金。

复杂策略继承 `Strategy` 并定义 Pydantic 参数模型，通过 SDK `StrategyRegistry.register` 注册。YAML 的 `custom.strategy` 只引用已注册名称，不能导入或执行任意代码。自定义策略同样经过调度、组合门控、预算与执行约束。

执行扩展用于自动提款清算时，`fee` 必须使可实现净卖出所得随卖出数量单调不减（标准 CashExecution 满足可成交费用区间内的这一契约）。清算用离散股数搜索，计入到账预算的储备底线、两个换汇环节、费用及资金舍入。
