# AllocFlow

面向长期投资的现金流与资产配置模拟器。Python 包：`allocflow`。

开发分支：`dev/allocflow-v0.1`。以投资计划为中心，六个 YAML 模板共用一个日级引擎。
用户金额、阈值、预算、资产、费用、时间与规则顺序全部显式配置；缺项和未知字段报错。

## 本地运行

需要 Python 3.12 和 uv。先下载本仓库开发分支，再在仓库目录运行：

```bash
uv sync --locked --extra web --extra scenarios --group dev
uv run allocflow validate --plan examples/user_plan.yaml
uv run allocflow demo-data --plan examples/user_plan.yaml --spec examples/demo_data.yaml --output work/demo-market
uv run allocflow run --plan examples/user_plan.yaml --dataset work/demo-market --output runs/first --html
uv run allocflow web
```

输出目录必须是新目录。演示数据是合成数据，不是历史行情。
Web 中选择模板并载入，填写数据集目录后运行；支持资金表单、资产树和规则编辑、完整 YAML、计划版本/复制、运行历史、检查点续跑、配对比较及事件解释。

## 模板与扩展

- `examples/user_plan.yaml`：用户计划，初始10万元、月投1万元；股票60%、债券24%、SGOV16%。
- `ordinary_dca.yaml`、`growing_contributions.yaml`、`drawdown_buy.yaml`：定投、递增投入、回撤加仓。
- `cashflow_underweight.yaml`、`hierarchical_rebalance.yaml`、`retirement_withdrawal.yaml`：补低配、分层再平衡、退休提款。
- `china_assets.yaml`：增加中国股票、场内基金和场外基金的研究示例。
- `custom_strategy.py`：继承 Strategy，定义参数模型，通过 SDK 登记扩展；YAML 仅引用登记名。

具名模板中的假设可修改：VOO回撤信号、每月重置触发、5个百分点再平衡阈值等，见 [设计基线](docs/DESIGN.md)。
初始股票预算直接建仓；只有后续月度投入拆成DCA与回撤池。预算现金不会被重复计价。

```python
from allocflow import load_plan, run_plan

result = run_plan(load_plan('examples/user_plan.yaml'), 'work/demo-market')
print(result.metrics)
```

## 数据与复现

数据集包含 `manifest.json`、`prices.csv`、`fx.csv`，读取时校验文件哈希。
CSV字段分别为 `instrument,date,available_on,value` 和 `currency,date,available_on,value`。
FX表示一单位币种折合多少数据集基准币种。详细格式见 [数据契约](docs/DATA.md)。

```bash
uv run allocflow schema --output work/plan.schema.json
uv run allocflow compare --plans examples/ordinary_dca.yaml --plans examples/cashflow_underweight.yaml --dataset work/demo-market --output work/comparison.json
uv run allocflow scenarios --plan examples/user_plan.yaml --dataset work/demo-market --spec examples/scenarios.yaml --output work/scenarios.json
```

文件数据集的导出包包含原始数据快照、完整计划、源代码指纹、版本信息、指标、事件、CSV、Decimal Parquet和独立HTML。
SDK传入内存数据对象时，导出包明确标记是否包含快照。原始金额JSON保留精确Decimal文本，Parquet报告投影保留18位小数。

可选行情入口：`uv sync --locked --extra web --extra scenarios --extra providers --group dev`，
然后执行 `uv run allocflow download --plan examples/plans/user_live.yaml --request examples/providers.yaml --output work/history`。
中国扩展使用 `examples/plans/china_live.yaml` 与 `examples/data/china_providers.yaml`。真实数据与演示数据价格口径不同，必须使用对应计划。
2026-11-06 已实测美股/中国股票/场内基金/场外基金接口，并用 2021–2023 年真实快照跑通两份计划；证据见 [数据验证](docs/LIVE-DATA-VALIDATION.md)。第三方接口后续仍可能变化。
SGOV历史始于其上市后，真实数据的训练区间须覆盖全部资产，不能使用演示数据的虚构历史替代。

## 验证与边界

```bash
uv run pytest
uv run ruff check src tests examples/custom_strategy.py
uv run ruff format --check src tests examples/custom_strategy.py
uv run mypy
```

日级执行、合成调整价格和碎股用于长期研究。场外基金使用延迟至可见净值的研究近似，
不还原未知价申赎；延迟资产不能用于当天提款，须提前卖出释放现金。税务、真实券商、
原价与公司行动完整处理暂未实现。skfolio/Optuna/DuckDB仅保留可选依赖分组，未接入普通运行。

[Goal](docs/GOAL.md) · [设计](docs/DESIGN.md) · [检查与验证](docs/REVIEW.md)

## 从文件续跑与比例提款

运行包包含 `checkpoint.json`。将后续计划的 start 设置为检查点日期之后，并使用覆盖前后区间的数据集：

```bash
uv run allocflow resume --plan continuation.yaml --dataset work/demo-market --checkpoint runs/first/checkpoint.json --output runs/continued --html
```

SDK：`from allocflow.application.checkpoints import load_checkpoint`，然后把
`load_checkpoint(path, plan)` 返回值传入 `run_plan(..., initial_state=state)`。
账户/币种契约必须一致。恢复后指标中的TWR针对续跑窗口，XIRR仍使用保存的投资人现金流历史。

提款政策新增必填 `amount_basis` 和 `fraction`：固定金额使用 `fixed`、`null`；
按账户余额提款使用 `portfolio_fraction` 和显式比例，例如 `'0.04'`。
比例模式对应现金流的固定金额与 annual_growth 必须填0。

完整开发测试环境包含providers：
`uv sync --locked --extra web --extra scenarios --extra providers --group dev`。

## 六阶段扩展

新示例采用 schema v2，旧 v1 可读取并显式迁移。所有新增业务能力都要显式填写；兼容值集中在 `config/evolution.py`。

- [配置契约与组合规则](docs/CONFIGURATION.md)：版本、preset、统一错误、AND/OR、冷却、次数、排名及预算边界。
- [本地计划与比较流程](docs/WORKFLOWS.md)：版本、历史、续跑、逐日预算/偏离、财富归因和事件差异。
- [长期规划](docs/PLANNING.md)：阶段、通胀、提款边界、应急储备、目标与同路径账户继承。
- [六阶段 Goal 与验收](docs/GOAL-SIX-STAGES.md)。

组合规则示例 `examples/plans/composed.yaml`，长期规划示例 `examples/plans/lifecycle.yaml`，集中 preset `examples/presets/catalog.yaml`。
