# AllocFlow

面向长期投资的现金流与资产配置模拟器。Python 包：`allocflow`。

首版开发分支：`dev/allocflow-v0.1`。以投资计划为中心，六个 YAML 模板共用一个日级引擎。
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
Web 中选择模板并载入，填写数据集目录后运行；可以编辑全部 YAML、比较计划、查看逐笔事件和导出结果。

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
然后执行 `uv run allocflow download --plan examples/user_plan.yaml --request examples/providers.yaml --output work/history`。
联网入口是可替换适配器；当前验证以离线契约为主，不保证第三方接口持续可用。
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
