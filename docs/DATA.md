# 数据契约

manifest 必须包含 schema_version: '1'、base_currency、source、availability_basis、
instruments（instrument_id到price_mode的映射）、files（prices.csv/fx.csv到SHA256的映射）。
可额外保存 fetched_at、provider_request 和来源说明。日期使用 ISO YYYY-MM-DD。

价格与汇率必须是正的有限数，业务联合键唯一；available_on 不早于所属日期。
估值向后对齐且受 max_stale_days 约束；策略只看执行日之前已发布的数据。
每日收盘成交是明确研究假设，不是跨时区盘中撮合。

支持 total_return_synthetic（使用者有总回报语义依据）与 provider_adjusted_synthetic。
二者均不另加现金分红。来源调整价与累计净值不自动等于分红再投资总回报。
AKShare 基金累计净值入口保留这个限制，下载记录会明确写入；软件不会推断不存在的分红数据。

下载适配器按照资产来源分别选择 YFinance、AKShare 股票、ETF、基金接口。
已获取的历史数据不等于当时可见的历史版本；availability_basis 必须说明可用时点依据。
重新下载产生新的快照，不覆盖运行中的数据。

中国股票与基金的symbol、calendar、quantity_step、pricing、execution_delay_sessions均可配置。
非交易日的投资意图排队，买单锁定预算、卖单锁定持仓。
场外基金的确认延迟为研究近似，不支持以延迟资产立即满足当天提款。
