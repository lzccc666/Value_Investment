# API 参考

## 基础约定

- 本地基址示例：`http://127.0.0.1:8000`
- 统一前缀：`/api`
- 请求与响应：JSON
- 列表响应通常包含 `items`、`total`、`limit`、`offset`
- 时间字段以 ISO 8601 返回，并在主要研究对象 schema 中序列化为 `Asia/Shanghai`
- 业务输入错误通常返回 `400`，资源不存在返回 `404`，身份冲突返回 `409`，模型或上游服务异常返回 `502/503`

交互式 OpenAPI 文档由 FastAPI 提供：`/docs` 和 `/redoc`。

## 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 返回服务状态、名称、版本和 `local_control_enabled` |
| `POST` | `/api/system/shutdown` | 仅托管本机会话可用；校验 loopback 来源及 `X-Local-Control-Token` 后请求监管进程关闭前后端 |

`/api/system/shutdown` 默认未启用并返回 `404`。`scripts/dev.ps1` 在完整前后端模式下为每次运行生成随机令牌和停止请求文件，通过进程环境分别注入后端与 Vite；令牌不持久化到项目配置或运行会话 JSON。远程客户端、非本机 Origin 和错误令牌返回 `403`。

## 公司与档案

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/companies` | `q`、`limit=20`、`offset=0` | 搜索公司池 |
| `POST` | `/api/companies` | `CompanyCreate` | 新增公司 |
| `GET` | `/api/companies/{company_id}` | - | 公司详情 |
| `POST` | `/api/companies/{company_id}/profile/refresh` | - | 主 Listing 兼容入口：刷新档案和行情 |
| `GET` | `/api/companies/{company_id}/listings` | - | 发行人的全部 Listing |
| `POST` | `/api/companies/{company_id}/listings` | `SecurityListingCreate` | 新增 Listing；ADS/ADR 比率不默认猜测 |
| `GET` | `/api/companies/{company_id}/market-capabilities` | 可选 `listing_id` | 返回所选 Listing 的 Provider 能力、原因和修复项 |
| `POST` | `/api/listings/{listing_id}/profile/refresh` | - | 按 Listing/市场刷新发行人档案 |
| `POST` | `/api/listings/{listing_id}/market-snapshots/refresh` | - | 创建不可变行情快照 |
| `GET` | `/api/listings/{listing_id}/market-snapshots/latest` | - | 读取最新不可变行情快照 |
| `POST` | `/api/listings/{listing_id}/primary` | - | 切换主 Listing 并原子更新 Company 兼容镜像 |

新增公司示例：

```json
{
  "ticker": "600519.SH",
  "exchange": "SSE",
  "name": "贵州茅台",
  "industry": "白酒",
  "tags": ["A股", "消费"]
}
```

`CompanyRead` 是发行人级响应，包含 `canonical_key`、法定名称、别名、注册地、报告币种、财政年结、外部 ID 和嵌套 `primary_listing`。旧 ticker/exchange/行情字段在兼容期继续返回主 Listing 镜像。`SecurityListing` 明确市场、交易所、交易币种、证券类型及 `underlying_shares_per_listing_unit`。

行情刷新不会更新旧快照；每次成功创建新的 `MarketSnapshot`，并冻结价格币种、观察/抓取时间、来源 URL 与原始哈希。能力状态为 `available`、`partial`、`unavailable`、`stale` 或 `blocked`。美股分红能力会结合所选发行人已落库的 SEC 标准现金分红事实判断：存在数值事实时返回 `available`，否则保留 Provider 的 `partial`，不把其他发行人的覆盖度套用到当前公司。

## 财务底稿

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/companies/{company_id}/financials` | `limit=60`、`offset=0`、`period_limit`、`period_offset=0` | 财务记录；period 参数按报告期分页 |
| `GET` | `/api/companies/{company_id}/financials/evidence-pack` | - | 当前财务证据包 |
| `POST` | `/api/companies/{company_id}/financials/sync` | `limit=60`、可选 `listing_id` | 使用所选市场 Provider 同步财务 |
| `DELETE` | `/api/companies/{company_id}/financials/{statement_id}` | - | 删除指定记录 |

财务同步响应包含获取、创建、更新数量和当前记录。底稿保留 period start/end/type、fiscal year/period、filing form、taxonomy、amendment、filed_at 与来源哈希。证据包除 facts、metrics、trends、flags、gaps 外，还明确 `reporting_currency`、`accounting_standard`、source coverage 和 mapping diagnostics；同一证据包禁止混合币种。

SEC 底稿 `fields.source_tags` 保存标准字段到原始 XBRL taxonomy/tag 的来源映射，`fields.mapping_diagnostics` 保存候选标签回退或低优先级候选被忽略的选择审计；二者不是财务数值。前端将其显示为中文审计计数，不展开成普通字段。缺口诊断按最新期间判断，历史期间曾出现某字段不代表最新期已经披露，也不能把缺失事实视为 0。

## 公告

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/companies/{company_id}/announcements` | `limit=20`、`offset=0` | 公告列表 |
| `POST` | `/api/companies/{company_id}/announcements/sync` | `years=1`、可选 `listing_id` | 使用 A 股/HKEX/SEC Provider 同步披露，当前保留最多 50 条 |
| `POST` | `/api/companies/{company_id}/announcements/{announcement_id}/summarize` | - | 单条深度摘要 |
| `POST` | `/api/companies/{company_id}/announcements/summarize-all` | `limit` | 快速批量摘要 |
| `POST` | `/api/companies/{company_id}/announcements/summarize-all-deep` | `limit` | 深度批量摘要 |
| `DELETE` | `/api/companies/{company_id}/announcements/{announcement_id}` | - | 删除公告 |

批量摘要响应包含总数、成功数、失败数、跳过数、总体状态和逐条结果。

披露记录可绑定 `listing_id`，并保留来源 document ID、document type、SEC filing form、语言、报告期、content type、正文来源/抓取时间和原文哈希。HKEX PDF 与 SEC HTML/inline XBRL 的正文提取失败会形成明确诊断，不伪造正文。SEC submissions 通常没有发行人另写的公告标题，Provider 因而用官方 form 与报告期生成可读标题，例如“季度报告（10-Q） · 报告期截至 YYYY-MM-DD”；`filing_form`、accession 和官方 URL 仍原样保留。再次同步同一 SEC 文档时会刷新这类权威元数据，但保留已经生成的摘要和正文。

## 外部证据

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/evidence/model-config` | - | 模型配置状态，不返回密钥 |
| `POST` | `/api/evidence/model-smoke-test` | - | 测试模型网关 |
| `POST` | `/api/companies/{company_id}/evidence/search` | `EvidenceSearchRequest` | 搜索并入库证据 |
| `GET` | `/api/companies/{company_id}/evidence` | `limit=10`、`offset=0` | 公司证据列表 |
| `GET` | `/api/evidence/{evidence_id}` | - | 证据详情 |
| `POST` | `/api/evidence/{evidence_id}/review` | - | 标记人工复核 |
| `DELETE` | `/api/evidence/{evidence_id}` | - | 删除证据 |

搜索请求：

```json
{
  "keywords": ["渠道库存", "海外增长"],
  "max_results": 5
}
```

搜索响应包含 `run_id`、`status`、新建数量、证据列表和可选 `diagnostics`。`status` 为 `success`、`partial` 或 `failed`。

## 分析师视角

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/analyst-profiles` | - | 固定 8 个 Profile 与 32 条规则 |
| `GET` | `/api/companies/{company_id}/analysis/runs/latest` | `run_type=analyst_view`、`analyst_profile` | 每个 Profile 最新运行 |
| `GET` | `/api/companies/{company_id}/analysis/runs` | `run_type`、`analyst_profile`、`status`、`limit=20`、`offset=0` | 运行历史 |
| `POST` | `/api/companies/{company_id}/analysis/runs` | `AnalystRunRequest` | 运行单个 Profile |
| `POST` | `/api/companies/{company_id}/analysis/runs/batch` | `AnalystBatchRunRequest` | 批量运行；空列表表示全部 |
| `PATCH` | `/api/companies/{company_id}/analysis/runs/{run_id}/rule-checks/{rule_id}` | `AnalysisRuleStatusUpdateRequest` | 修改规则状态并重算矩阵 |
| `DELETE` | `/api/companies/{company_id}/analysis/runs/{run_id}` | - | 删除运行 |

请求示例：

```json
{
  "analyst_profile": "buffett",
  "user_note": "重点复核现金流质量"
}
```

```json
{
  "status": "warn"
}
```

规则状态只能是 `pass`、`neutral`、`unknown`、`warn`、`fail`。8 Profile、32 规则、13 维与 117 个系数是固定合同；008 输入不含行情或 FX。

## 投资备忘录

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/companies/{company_id}/investment-memos/generate` | `{ "user_note": null }` | 生成新版本 |
| `GET` | `/api/companies/{company_id}/investment-memos/latest` | - | 最新有效 Memo |
| `GET` | `/api/companies/{company_id}/investment-memos` | `limit=20`、`offset=0` | 历史列表 |
| `GET` | `/api/investment-memos/{memo_id}` | - | Memo 详情 |
| `POST` | `/api/investment-memos/{memo_id}/archive` | - | 归档 |
| `DELETE` | `/api/investment-memos/{memo_id}` | - | 删除 |

生成响应包含生成运行 ID 和 `InvestmentMemoRead`。Memo 的 `sections` 保存纯叙事委员会综合、结构化正文和来源引用；009 不保存评分卡、分析师权重或安全边际。

## 无锚定估值

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/companies/{company_id}/valuation-runs/draft` | `ValuationDraftRequest` | 创建草稿；可带初始假设 |
| `POST` | `/api/valuation-runs/{run_id}/recalculate` | `ValuationRecalculateRequest` | 用用户确认假设创建计算版本 |
| `GET` | `/api/companies/{company_id}/valuation-runs/latest` | - | 最新估值 |
| `GET` | `/api/companies/{company_id}/valuation-runs` | `limit=20`、`offset=0` | 历史列表 |
| `GET` | `/api/valuation-runs/{run_id}` | - | 估值详情 |

请求结构：

```json
{
  "assumptions": {
    "model_weights": {
      "owner_earnings": 0.35,
      "dcf": 0.35,
      "residual_income": 0.15,
      "dividend_discount": 0.1,
      "asset_value": 0.05
    }
  },
  "user_note": "确认估值参数"
}
```

`ValuationRunRead` 保存 price-blind 审计、`valuation_currency`、`share_basis_snapshot`、输入快照、建议/用户/最终假设、方法结果、三情景内在价值、敏感性、置信度和来源图。多股类或发行人普通股基准不可解释时，不生成可用于 011 的每股价值。

## 价格决策

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/companies/{company_id}/price-decision-runs` | `PriceDecisionCreateRequest` | 生成新版本 |
| `GET` | `/api/companies/{company_id}/price-decision-runs/latest` | - | 最新有效版本 |
| `GET` | `/api/companies/{company_id}/price-decision-runs` | `limit=20`、`offset=0`、`include_deleted=false` | 历史列表 |
| `GET` | `/api/price-decision-runs/{run_id}` | - | 版本详情 |
| `DELETE` | `/api/price-decision-runs/{run_id}` | - | 软删除 |

创建请求：

```json
{
  "valuation_run_id": 12,
  "safety_margin_override": 0.25,
  "listing_id": 8
}
```

三个字段都可省略；未指定估值时选择当前公司最新的已完成估值，未覆盖安全边际时读取绑定 010 冻结的动态安全边际，未指定 Listing 时使用主 Listing。新运行必须绑定币种一致且未过期的 `MarketSnapshot`；跨币种时还绑定未过期 `FxRateSnapshot`。换算公式为 `发行人每股价值 × underlying_shares_per_listing_unit × valuation->trading FX`。响应冻结 Listing/行情/FX 外键、换算前后内在价值、汇率计算审计、买入价和价格状态；旧历史允许新外键为空且不回填。

## 汇率快照

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/fx-rates/refresh` | `base_currency`、`quote_currency` | 从 ECB 日度数据创建不可变汇率快照 |
| `GET` | `/api/fx-rates/latest` | `base_currency`、`quote_currency` | 读取指定方向最新快照 |

ECB 交叉汇率只使用同一 rate date，公式为 `quote_per_eur / base_per_eur`；响应的 `calculation_audit` 保留两个 EUR 基准值、共同日期、公式和来源哈希。同币种 identity FX 固定为 1，但不创建伪造快照。

## 投资小工具

`015` 是独立于 `004-011` 研究主链路的持久化 API，统一前缀为 `/api/investment-tools`。

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/investment-tools/portfolio-owners` | - | 持仓人列表 |
| `POST` | `/api/investment-tools/portfolio-owners` | `name`、`owner_type=self/investor`、可选 `notes` | 新增持仓人 |
| `PUT` | `/api/investment-tools/portfolio-owners/reorder` | `{ "ordered_ids": [...] }` | 持久化全部持仓人顺序；ID 集合不完整或重复时拒绝 |
| `GET` | `/api/investment-tools/portfolio-owners/{owner_id}` | - | 持仓人详情 |
| `PATCH` | `/api/investment-tools/portfolio-owners/{owner_id}` | 可更新字段 | 编辑持仓人 |
| `DELETE` | `/api/investment-tools/portfolio-owners/{owner_id}` | - | 删除无快照依赖的持仓人；有依赖返回 `409` |
| `GET` | `/api/investment-tools/portfolio-owners/{owner_id}/snapshots` | - | 持仓人的历史快照列表 |
| `POST` | `/api/investment-tools/portfolio-owners/{owner_id}/snapshots` | `title`、`as_of_date`、`base_currency`、可选复制源 | 新建快照，可从同一持仓人的历史快照复制持仓 |
| `PUT` | `/api/investment-tools/portfolio-owners/{owner_id}/snapshots/reorder` | `{ "ordered_ids": [...] }` | 持久化该持仓人的全部快照顺序 |
| `GET` | `/api/investment-tools/portfolio-listings/search` | `q`、可选 `limit=20` | 直接搜索 015 可录入的启用中具体 Listing |
| `GET` | `/api/investment-tools/portfolio-listings/ah-catalog/search` | `q`、可选 `limit=20` | 搜索尚未导入的沪深北/港股普通股目录候选；过滤 ETF、基金、优先股、权证及港股人民币柜台 |
| `POST` | `/api/investment-tools/portfolio-listings/ah-catalog/import` | `quote_id` | 再次核对东方财富目录后幂等导入本地 Company/Listing |
| `GET` | `/api/investment-tools/portfolio-listings/us-catalog/search` | `q`、可选 `limit=20` | 搜索尚未导入且证券类型已确认为普通股/ADS 的 SEC Nasdaq/NYSE 目录候选 |
| `POST` | `/api/investment-tools/portfolio-listings/us-catalog/import` | `cik`、`symbol` | 复核 SEC submissions 后幂等导入本地 Company/Listing |
| `GET` | `/api/investment-tools/buy-memo-entries` | 无 | 获取已冻结的买入备忘录条目 |
| `POST` | `/api/investment-tools/buy-memo-entries` | `price_decision_run_id` | 从指定 011 投资决策版本导入不可变结果快照 |
| `DELETE` | `/api/investment-tools/buy-memo-entries/{entry_id}` | 无 | 删除一条买入备忘录，不删除 011 来源结果 |
| `GET` | `/api/investment-tools/buy-memo-companies` | 可选 `q`、`limit` | 搜索至少有一个有效 011 投资决策结果的公司 |
| `GET` | `/api/investment-tools/buy-memo-companies/{company_id}/price-decisions` | 无 | 获取公司可导入的 011 历史版本及已导入状态 |
| `GET` | `/api/investment-tools/reading-books` | 无 | 获取全部书籍及各自多轮阅读进度 |
| `POST` | `/api/investment-tools/reading-books` | `title`、`status`、`initial_progress`，可选 `author/notes` | 手工新增书籍并创建第一轮进度 |
| `GET` | `/api/investment-tools/reading-books/{book_id}` | 无 | 获取一本书及全部历史阅读轮次 |
| `PATCH` | `/api/investment-tools/reading-books/{book_id}` | 可更新 `title/author/status/notes` | 编辑书籍，不覆盖阅读轮次 |
| `DELETE` | `/api/investment-tools/reading-books/{book_id}` | 无 | 删除书籍并显式级联全部阅读进度 |
| `POST` | `/api/investment-tools/reading-books/{book_id}/progress` | 可选 `progress_percent`，默认 0 | 按历史最大编号新增一轮阅读 |
| `PATCH` | `/api/investment-tools/reading-progress/{progress_id}` | `progress_percent` | 更新指定轮次的百分比 |
| `DELETE` | `/api/investment-tools/reading-progress/{progress_id}` | 无 | 删除非最后一轮阅读记录；最后一轮返回 `409` |
| `GET` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}` | - | 快照详情 |
| `PATCH` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}` | 可更新字段 | 编辑快照 |
| `DELETE` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}` | - | 删除快照并显式级联其持仓 |
| `GET` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}/holdings` | - | 快照持仓列表 |
| `POST` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}/holdings` | `listing_id`、`quantity`、可选备注/顺序 | 新增具体 Listing 持仓；重复 Listing 返回 `409` |
| `GET` | `/api/investment-tools/portfolio-holdings/{holding_id}` | - | 持仓详情 |
| `PATCH` | `/api/investment-tools/portfolio-holdings/{holding_id}` | 可更新字段 | 编辑股数、Listing、备注或顺序 |
| `DELETE` | `/api/investment-tools/portfolio-holdings/{holding_id}` | - | 删除持仓 |
| `GET` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}/valuation` | - | 按最新可用行情与 FX 返回派生估值 |
| `POST` | `/api/investment-tools/portfolio-snapshots/{snapshot_id}/refresh-quotes` | - | 去重刷新组合行情和所需 FX，隔离单项失败并返回重算结果 |
| `GET` | `/api/investment-tools/market-fear` | - | 读取 A/H/美三市场最近成功的日频温度缓存 |
| `POST` | `/api/investment-tools/market-fear/refresh` | 可选查询参数 `market=A_SHARE/HK/US` | 刷新全部或单个市场，失败时返回过期缓存和错误 |

快照 `base_currency` 只允许 `CNY/HKD/USD`；`as_of_date` 不能晚于当天。`quantity` 必须大于 0、总精度最多 28 位且小数最多 8 位，A/H 普通股在服务层要求整数。JSON 中的 quantity、价格、汇率、市值、权重和温度数值按 Pydantic Decimal 合同序列化，调用方不得使用二进制浮点数回写。持仓数量表示所选 Listing 的实际证券单位；ADS 数量直接乘 ADS 市价，不乘 `underlying_shares_per_listing_unit`。

持仓人和快照读取响应包含 `display_order`。重排请求必须无重复地提交当前作用域的完整 ID 集合，服务按数组顺序写入连续 `0..N-1`；遗漏当前记录、混入其他持仓人的快照或包含未知 ID 返回 `400`。Listing 搜索只返回启用中的 A/H/美普通股或 ADS，支持公司名、别名、ticker/symbol、点号归一化和 A股/港股/美股市场词。A/H 外部目录只接受沪深北普通股和港股 HKD 普通股，导入前按 `quote_id` 二次核验并与本地完全同名/别名发行人合并；ETF、基金、优先股、权证和币种无法确定的港股人民币柜台不会进入候选。SEC 搜索与导入均要求外部证券目录确认普通股或 ADS，因此 ETF、优先股、权证等不会出现在候选中或被导入；导入接受 Nasdaq/NYSE `operating` issuer，对 `entityType=other` 仅在 SEC submissions 存在 `20-F/6-K` 时放行。未核验的证券单位比例保持空值，不绕过 011 门禁。

买入备忘录按选定的 `PriceDecisionRun` 冻结公司与 Listing、中性内在价值、建议买入价、生效安全边际、最新报告期和 011 版本。同一来源只能导入一次，重复返回 `409`；011 来源随后删除时仅将 `source_price_decision_run_id` 置空，冻结字段继续保留。删除备忘条目不删除来源 011，也不触发重算。

阅读书单由用户手工维护，不关联 Company、Listing 或 004-011 运行。书籍状态只允许 `planned/reading/finished`；阅读进度为 `0-100` 整数。每一轮以服务端生成的正整数 `round_number` 独立保存，同一本书的轮次编号唯一，因此后续重读不会覆盖此前进度。状态与进度彼此独立，API 不根据百分比自动改变状态。

估值公式为 `local_market_value = quantity × latest_price`、`base_market_value = local_market_value × applicable_fx_rate`、`weight = base_market_value / priced_total`。缺价格或 FX 的条目标记为未计价，不以 0 代替，也不进入总市值和权重分母。行情和汇率响应同时给出数据日期、来源和状态；这里的“最新”不表示交易级实时。

市场温度只使用最新日频收盘：美股 Cboe VIX、港股恒生指数公司 VHSI、A 股 AKShare 50ETF QVIX。A 股响应固定包含第三方代理说明。三个市场分别按自身过去 3 年历史百分位映射 0-100 温度，不能直接比较绝对值；响应固定提示波动率不代表价格方向，也不是买卖建议。

## 参数配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/parameter-config/current` | 当前活动配置、hash、来源、校验与中文元数据 |
| `GET` | `/api/parameter-config/defaults` | 内置默认配置 |
| `POST` | `/api/parameter-config/validate` | 完整校验，不写文件 |
| `PUT` | `/api/parameter-config/current` | 校验后原子发布活动配置 |

当前配置有 8 个域、377 个实际数值；其中 `market_data.quote_max_age_hours` 范围为 1-720 小时，`market_data.fx_max_age_days` 范围为 1-90 天，且都必须是整数。发布只影响新同步和新运行，历史继续读取自身 `config_snapshot`。SEC User-Agent、Provider URL、凭据和缓存路径属于环境配置，不通过此 API 发布。

## 数据管理

`012` 是独立运维 API，不属于 `004-011` 研究主链路。所有破坏性操作先调用 Preview，再提交后端返回的一次性令牌和精确确认短语。

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/data-management/summary` | - | 数据库大小、各表数量、软删除、最近备份、自动备份和完整性状态 |
| `POST` | `/api/data-management/operations/preview` | `DataOperationPreviewRequest` | 生成影响计划和一次性令牌 |
| `POST` | `/api/data-management/operations/execute` | `DataOperationExecuteRequest` | 校验令牌、数据库状态和确认短语后执行 |
| `GET` | `/api/data-management/backups` | - | 备份列表 |
| `POST` | `/api/data-management/backups` | `{ "reason": "manual" }` | 手动创建并校验一致性备份 |
| `POST` | `/api/data-management/backups/{backup_id}/verify` | - | 校验 SHA-256 和 SQLite integrity check |
| `POST` | `/api/data-management/backups/{backup_id}/restore/preview` | - | 生成指定备份的恢复预览 |
| `DELETE` | `/api/data-management/backups/{backup_id}` | 令牌与确认短语 | 删除已通过通用 Preview 绑定的备份 |
| `GET` | `/api/data-management/settings` | - | 自动备份设置 |
| `PUT` | `/api/data-management/settings` | `enabled`、`interval_hours`、`max_backups` | 更新自动备份与保留策略 |

Preview 示例：

```json
{
  "operation_type": "prune_versions",
  "parameters": {
    "company_id": 1,
    "keep_count": 3
  }
}
```

操作类型包括 `reset_company_research_data`、`clear_analysis_history`、`initialize_database`、`prune_versions`、`purge_deleted_and_vacuum`、`restore_backup` 和 `delete_backup`。Preview 响应包含各表影响数量、受引用保护记录、预计释放空间、是否自动备份、确认短语和过期时间。统计、操作指纹和备份 manifest 均包含 `security_listings`、`market_snapshots`、`fx_rate_snapshots` 以及 015 的 `portfolio_owners`、`portfolio_snapshots`、`portfolio_holdings`、`market_fear_snapshots`、`buy_memo_entries`、`reading_books`、`reading_progress_entries`。公司研究重置和全局分析历史清理保留 015；完整初始化只有在预览、精确确认和操作前备份后才会删除 015 数据。

Execute 示例：

```json
{
  "operation_token": "preview 返回的一次性令牌",
  "confirmation_phrase": "清理旧版本"
}
```

令牌过期、重复使用或数据库状态变化返回 `409`。另一个维护操作正在执行时返回 `409`；维护期间非数据管理写请求返回 `503`。恢复和初始化成功时响应可包含 `restart_required=true`。

## 数据范围边界

- API 不提供券商账户同步、成本收益归因或交易执行端点；015 的持仓、买入备忘录、市场温度与阅读书单均保持独立工具边界。
- 首轮完整链路只支持 A 股普通股、港交所普通股及 NASDAQ/NYSE/AMEX 普通股/ADS；ETF、基金、衍生品、OTC 不在范围内。
- 008-010 的输入、输出和对应 UI 不接受市场价格、市值、MarketSnapshot、FX、目标价或交易动作。
- 011 只读取已完成估值、其绑定 Memo、目标 Listing、不可变行情和必要的 FX；缺失币种、share basis、证券单位比率、行情或汇率时明确阻断。
