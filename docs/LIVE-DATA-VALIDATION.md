# 真实数据验证 · 2026-11-06

四个接口均实际联网调用并返回 2023-01-03 至 2023-02-03 数据：YFinance VOO（23 条），AKShare 600519、510300、110022（各 19 条）。随后完整下载 2020–2023 行情和 USD/CNY、EUR/USD 汇率，冻结 CSV 与 SHA256 清单，在断网运行入口完成 2021-01-04 至 2023-12-29 模拟。

| 运行 | 标的 | 事件 | 质量检查 | 期末值（CNY） |
|---|---|---:|---|---:|
| user_live | 原九资产计划 | 610 | 通过；复权/时点口径警告保留 | 520413.4850476033751612364144 |
| china_live | 原资产＋中国股票/场内 ETF/场外基金 | 772 | 通过；复权/时点口径警告保留 | 501718.9559263375525730063509 |

这些数值是工程回放结果；两份计划资产配置不同，不用于证明某类资产更优。初始资金和月度现金流沿用用户示例，没有加入第十年支出。中国扩展仍采用明确配置的碎股和可见净值研究模型。

[机器可读证据](evidence/live-data.json) 包含数据集 ID、文件哈希、下载请求、逐序列覆盖、运行参数指纹和源代码指纹。原始数据保存在本次运行导出包的 dataset 目录；不把行情快照混入 Python 包。再次联网下载可能因来源修订产生不同哈希，复现必须使用已冻结快照。

```bash
uv sync --locked --extra providers --extra web --extra scenarios --group dev
uv run allocflow download --plan examples/plans/user_live.yaml --request examples/providers.yaml --output work/live-us
uv run allocflow data-quality --plan examples/plans/user_live.yaml --dataset work/live-us --output work/us-quality.json
uv run allocflow run --plan examples/plans/user_live.yaml --dataset work/live-us --output runs/live-us --html
uv run allocflow download --plan examples/plans/china_live.yaml --request examples/data/china_providers.yaml --output work/live-cn
uv run allocflow run --plan examples/plans/china_live.yaml --dataset work/live-cn --output runs/live-cn --html
```

运行前检查覆盖整个执行时间轴及决策所需的前一日可见价格。缺口、超期数据、缺 FX 或价格口径不符都报错，不自动换代理资产。first_observation 是快照中首条观测，不宣称是已认证上市日；历史发布时点和复权版本同样不宣称为已认证 point-in-time。基金累计净值不等同于红利再投资总回报。

SGOV 的真实历史晚于 2020 年初，因此原合成示例的 2020 全年情景训练窗口不能直接套用到真实快照；需要用户显式选择所有资产共有的训练区间。
