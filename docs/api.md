# API 草案

当前已实现接口：

```text
GET  /api/health
GET  /api/companies
POST /api/companies
GET  /api/companies/{company_id}
POST /api/companies/{company_id}/profile/refresh
GET  /api/companies/{company_id}/financials
POST /api/companies/{company_id}/financials/sync
DELETE /api/companies/{company_id}/financials/{statement_id}
GET  /api/companies/{company_id}/announcements
POST /api/companies/{company_id}/announcements/sync
POST /api/companies/{company_id}/announcements/summarize-all
POST /api/companies/{company_id}/announcements/summarize-all-deep
POST /api/companies/{company_id}/announcements/{announcement_id}/summarize
DELETE /api/companies/{company_id}/announcements/{announcement_id}
GET  /api/evidence/model-config
POST /api/evidence/model-smoke-test
POST /api/companies/{company_id}/evidence/search
GET  /api/companies/{company_id}/evidence
GET  /api/evidence/{evidence_id}
POST /api/evidence/{evidence_id}/review
DELETE /api/evidence/{evidence_id}
GET  /api/analyst-profiles
GET  /api/companies/{company_id}/analysis/runs/latest
GET  /api/companies/{company_id}/analysis/runs
POST /api/companies/{company_id}/analysis/runs
POST /api/companies/{company_id}/analysis/runs/batch
DELETE /api/companies/{company_id}/analysis/runs/{run_id}
```

## 健康检查

```text
GET /api/health
```

响应：

```json
{
  "status": "ok",
  "service": "Value Investment API",
  "version": "0.1.0",
  "environment": "development",
  "checked_at": "2026-01-01T00:00:00Z"
}
```

## 公司列表

```text
GET /api/companies?q=贵州茅台&limit=20&offset=0
GET /api/companies?q=AAPL&limit=20&offset=0
```

响应：

```json
{
  "items": [
    {
      "id": 1,
      "ticker": "600519.SH",
      "exchange": "SSE",
      "name": "贵州茅台",
      "industry": "白酒",
      "description": "A股白酒公司，真实公司主数据种子；不包含实时行情或投资建议。",
      "listed_date": "2001-08-27",
      "status": "未研究",
      "tags": ["A股", "白酒", "消费"],
      "market_cap": null,
      "current_price": null,
      "pe_ttm": null,
      "pe_dynamic": null,
      "pe_static": null,
      "pb_ratio": null,
      "ps_ratio": null,
      "dividend_yield_ttm": null,
      "dividend_yield_static": null,
      "market_data_source": null,
      "market_data_source_url": null,
      "market_data_updated_at": null,
      "created_at": "2026-08-09T00:00:00Z",
      "updated_at": "2026-08-09T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 60,
  "offset": 0
}
```

## 新增公司

```text
POST /api/companies
```

请求字段：

- `ticker`：必填，证券代码。建议使用 `600519.SH`、`00700.HK`、`AAPL.US` 这类带市场后缀的格式。
- `exchange`：必填，交易所。例如 `SSE`、`SZSE`、`HKEX`、`NASDAQ`、`NYSE`。系统用 `ticker + exchange` 去重。
- `name`：必填，公司名称。
- `industry`：可选，所属行业，用于后续筛选、对比和研究分组。
- `description`：可选，公司简介或研究备注。
- `listed_date`：可选，上市日期，格式 `YYYY-MM-DD`。留空时，A 股公司档案页会尝试通过东方财富公司概况自动补齐。
- `status`：可选，研究状态，默认 `未研究`。
- `tags`：可选，标签数组，会参与公司搜索。

请求示例：

```json
{
  "ticker": "SONY.US",
  "exchange": "NYSE",
  "name": "Sony Group Corporation 索尼集团",
  "industry": "消费电子",
  "description": "手动新增的研究对象。",
  "listed_date": "1970-09-17",
  "status": "观察中",
  "tags": ["美股", "消费电子"]
}
```

重复提交同一个 `ticker + exchange` 时返回 `409`。

## 公司档案

```text
GET /api/companies/1
```

响应：

```json
{
  "id": 1,
  "ticker": "600519.SH",
  "exchange": "SSE",
  "name": "贵州茅台",
  "industry": "白酒",
  "description": "A股白酒公司，真实公司主数据种子；不包含实时行情或投资建议。",
  "listed_date": "2001-08-27",
  "status": "未研究",
  "tags": ["A股", "白酒", "消费"],
  "market_cap": 1694223093019.29,
  "current_price": 1355.29,
  "pe_ttm": 20.48,
  "pe_dynamic": 15.55,
  "pe_static": 20.58,
  "pb_ratio": 7.18,
  "ps_ratio": 10.57,
  "dividend_yield_ttm": 0.0384,
  "dividend_yield_static": 0.0384,
  "market_data_source": "eastmoney_quote_snapshot,eastmoney_bonus_financing",
  "market_data_source_url": "https://push2delay.eastmoney.com/api/qt/stock/get?...; https://emweb.securities.eastmoney.com/PC_HSF10/BonusFinancing/PageAjax?...",
  "market_data_updated_at": "2026-08-13T22:30:00+08:00",
  "created_at": "2026-08-09T08:00:00+08:00",
  "updated_at": "2026-08-09T08:00:00+08:00"
}
```

`status` 仍保留在接口中兼容公司池管理，但前端基础档案页不再展示研究状态。公司档案相关的 `created_at`、`updated_at` 和 `market_data_updated_at` 返回东八区 ISO 时间。

## 更新公司基础档案和实时基本信息

```text
POST /api/companies/1/profile/refresh
```

该接口会刷新公司档案展示用的基础信息：如果上市日期缺失，会先尝试通过东方财富公司概况补齐；随后通过东方财富行情快照更新市值、价格、TTM市盈率、动态市盈率、静态市盈率、市净率、市销率和行情更新时间，并通过东方财富 F10 分红融资数据计算 TTM 股息率。TTM 股息率按最近 12 个月已实施每股现金分红 / 当前价格计算。静态股息率仍在接口中保留供后续模块兼容。

成功响应：返回更新后的 `CompanyRead`。

错误响应：

- `400`：当前证券代码暂不支持行情快照刷新。
- `404`：公司不存在。
- `502`：外部行情源请求失败或返回不可用数据。

注意：这些价格、市值和估值倍数只用于公司基础档案展示，不作为内在价值估值或分析师视角的默认输入。

## 公司财务数据

```text
GET /api/companies/1/financials?limit=60&offset=0
```

该接口只读取数据库中已有的公司财务数据，不主动访问外部数据源。默认 `limit=60`，用于和 15 年财务同步结果保持一致。

响应：

```json
{
  "items": [
    {
      "id": 1,
      "company_id": 1,
      "period": "2025A",
      "statement_type": "income_statement",
      "currency": "CNY",
      "fields": {
        "revenue": 100.0,
        "gross_margin": 0.58,
        "net_profit": 24.0,
        "operating_cash_flow": 28.0
      },
      "source": "manual_import",
      "source_url": null,
      "created_at": "2026-08-09T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

## 搜索并同步公司财务数据

```text
POST /api/companies/1/financials/sync?limit=60
```

该接口会按公司 `ticker` 到外部数据源搜索财务数据，当前第一版默认接入东方财富 F10 主要财务指标。默认 `limit=60`，用于覆盖近 15 年左右的季度/半年度/年度主要财务指标。同步成功后，数据会按 `company_id + period + statement_type` 写入或更新到 `financial_statements`，然后公司财务数据读取接口会立即返回这些记录。

响应：

```json
{
  "company_id": 1,
  "source": "eastmoney_f10_main_finance",
  "fetched": 2,
  "created": 2,
  "updated": 0,
  "items": [
    {
      "id": 10,
      "company_id": 1,
      "period": "2025年报",
      "statement_type": "main_financial_indicators",
      "currency": "CNY",
      "fields": {
        "report_date": "2025-12-31 00:00:00",
        "report_type": "年报",
        "notice_date": "2026-04-17 00:00:00",
        "revenue": 172054171890.91,
        "net_profit": 82320067101.68,
        "roe": 0.3253,
        "gross_margin": 0.9118
      },
      "source": "eastmoney_f10_main_finance",
      "source_url": "https://datacenter.eastmoney.com/...",
      "created_at": "2026-08-09T00:00:00Z"
    }
  ]
}
```

如果外部数据源请求失败，接口返回 `502`，前端会展示失败原因。

## 删除公司财务数据

```text
DELETE /api/companies/1/financials/10
```

删除某家公司下的一条已入库财务记录。接口会校验财务记录必须属于当前 `company_id`；不存在或不属于该公司时返回 `404`。

响应：

```json
{
  "id": 10,
  "deleted": true
}
```

注意：删除的是本地数据库记录。如果之后再次点击“搜索财务数据”，外部数据源仍然返回同一期间数据，系统会重新写入。

## 公司公告

```text
GET /api/companies/1/announcements?limit=20&offset=0
```

响应：

```json
{
  "items": [
    {
      "id": 1,
      "company_id": 1,
      "title": "年度经营摘要已导入",
      "published_at": "2026-01-15T00:00:00Z",
      "category": "annual_report",
      "content": null,
      "raw_content": null,
      "summary": "公告摘要由后续读取流程或人工复核补充。",
      "source": "manual_import",
      "source_url": null,
      "raw_url": null,
      "created_at": "2026-08-09T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

## 搜索并同步公司公告

```text
POST /api/companies/1/announcements/sync?years=1
```

该接口会按公司 `ticker` 到外部公告源搜索最近一年内最多 50 条公告，当前第一版默认接入东方财富公告接口，优先支持 A 股公司，例如 `600519.SH`。默认 `years=1`，后端按页读取直到达到 50 条或公告发布时间早于回看边界。同步成功后会清理该公司一年窗口外以及超过 50 条保留上限的旧公告。006 只读取公告基础字段和原文链接，不生成摘要、不调用模型，也不按情绪、价格或标题关键词过滤公告。同步时如果公告已存在，后端会跳过该公告，不覆盖已有摘要；新公告按 `source_url` 或 `company_id + title + published_at` 去重写入 `announcements`。

响应：

```json
{
  "company_id": 1,
  "source": "eastmoney_announcements",
  "fetched": 50,
  "created": 18,
  "updated": 0,
  "skipped": 2,
  "pruned": 6,
  "errors": [],
  "items": [
    {
      "id": 10,
      "company_id": 1,
      "title": "贵州茅台:贵州茅台重大事项公告",
      "published_at": "2026-07-18T00:00:00Z",
      "category": "其他",
      "content": null,
      "raw_content": null,
      "summary": null,
      "source": "eastmoney_announcements",
      "source_url": "https://data.eastmoney.com/notices/detail/600519/AN202607171827064564.html",
      "raw_url": "https://pdf.dfcfw.com/pdf/H2_AN202607171827064564_1.pdf",
      "key_facts": [],
      "impact_direction": null,
      "sentiment": null,
      "positive_impacts": [],
      "negative_impacts": [],
      "neutral_impacts": [],
      "risk_tips": [],
      "review_questions": [],
      "tags": [],
      "summary_status": "unprocessed",
      "summary_model_name": null,
      "summary_prompt_version": null,
      "summarized_at": null,
      "created_at": "2026-08-09T00:00:00Z"
    }
  ]
}
```

如果公司代码暂不支持，接口返回 `400`；如果外部公告源请求失败，接口返回 `502`，前端会展示失败原因。

公告列表展示状态由 `summary_model_name` 区分：

- 空摘要：`未摘要`
- `metadata_keyword`：`已快速摘要`
- 其他非空模型名：`已深度摘要`

## 生成公告智能摘要

```text
POST /api/companies/1/announcements/10/summarize
```

该接口对单条已入库公告生成结构化摘要。后端会优先使用 `raw_content/content`；如果为空，会按 `raw_url/source_url` 尝试读取公告 PDF 或 HTML 原文。模型调用复用后端 `ModelGateway`，但每次只发送当前公司、当前公告和当前公告正文，不复用历史 messages，不传 conversation/thread id，也不自动读取历史 `analysis_runs`。

公告摘要不再写入 `analysis_runs` 历史，后端只保存每条公告的最新一次智能摘要。成功时会把最新可展示摘要写回 `announcements`，包括 `summary/key_facts/category/impact_direction/tags/risk_tips/review_questions/summary_status/summary_model_name`。旧版已产生的 `announcement_summary` 历史会在应用初始化时清理。若 PDF/HTML 原文无法读取，后端不会直接让该公告失败，而是基于标题、分类、发布时间和来源生成低置信度关键词摘要，并在 `review_questions` 中说明需要人工打开来源复核。

响应：

```json
{
  "company_id": 1,
  "announcement_id": 10,
  "run_id": null,
  "status": "success",
  "summary_status": "summarized",
  "announcement": {
    "id": 10,
    "company_id": 1,
    "title": "贵州茅台:贵州茅台重大事项公告",
    "summary": "类别：定期报告；性质：定期披露；影响：中性",
    "key_facts": ["可复核事实"],
    "category": "定期报告",
    "impact_direction": "neutral",
    "tags": ["财报"],
    "summary_status": "summarized"
  }
}
```

未配置模型时返回 `400`；模型接口或结构化校验失败时返回 `502`，不写入 `analysis_runs`。公告原文读取失败会走 metadata keyword 兜底，不再默认失败。

## 一键生成全部公告摘要

```text
POST /api/companies/1/announcements/summarize-all?limit=50&only_missing=false&include_failed=true
```

该接口用于公司详情页“一键快速摘要”。它不会读取 PDF/HTML 原文，也不会调用模型 API，只基于每条公告的标题、分类、发布时间、来源和来源链接生成短关键词摘要。默认最多处理 50 条，且跳过已经深度摘要过的公告。每条公告仍然独立生成摘要并分别写回各自公告卡片，不会合并成一条总摘要，也不会保存历史版本。

查询参数：

- `limit`：最多处理多少条，默认 `50`，范围 `1-50`。
- `only_missing`：默认 `false`，表示重新生成当前范围内所有公告的最新摘要；传 `true` 时只处理未摘要公告。
- `include_failed`：默认 `true`，传 `only_missing=true` 时是否把失败状态公告纳入重试。

响应：

```json
{
  "company_id": 1,
  "requested": 23,
  "processed": 23,
  "remaining": 0,
  "succeeded": 23,
  "failed": 0,
  "status": "success",
  "items": [
    {
      "announcement_id": 10,
      "status": "success",
      "summary_status": "summarized",
      "run_id": null,
      "announcement": {
        "id": 10,
        "title": "贵州茅台:贵州茅台重大事项公告",
        "summary": "类别：其他事项；性质：公告事项；影响：未知；正文：未读取",
        "summary_status": "summarized",
        "summary_model_name": "metadata_keyword"
      }
    }
  ]
}
```

批量快速摘要的输出是元数据关键词，不代表已经完成公告正文解读。需要深读公告时，可调用单条 `/summarize` 接口，或使用批量深度摘要接口逐条处理。

## 一键生成全部公告深度摘要

```text
POST /api/companies/1/announcements/summarize-all-deep?limit=50
```

该接口用于公司详情页“一键深度摘要”。后端会读取当前公司尚未深度摘要的公告，逐条复用单条深度摘要流程；已经深度摘要过的公告会跳过。每条公告仍然分别写回自己的摘要字段，不合并结果，也不保存历史版本。

## 公告证据字段

后续分析师视角读取公告作为证据时，只传递以下字段：

- `id`
- `title`
- `published_at`
- `category`
- `summary`

## 删除公司公告

```text
DELETE /api/companies/1/announcements/10
```

该接口只删除指定公司名下的公告条目，用于移除用户不需要的公告。不会删除其他公司的同 ID 公告。

响应：

```json
{
  "id": 10,
  "deleted": true
}
```

如果公告不存在，或公告不属于该公司，返回 `404`。

## 模型配置与外部证据

```text
GET /api/evidence/model-config
POST /api/evidence/model-smoke-test
POST /api/companies/1/evidence/search
GET /api/companies/1/evidence?limit=10&offset=0
GET /api/evidence/10
POST /api/evidence/10/review
DELETE /api/evidence/10
```

外部证据模块用于把联网搜索、模型摘要、证据可信度和人工复核状态写入本地数据库。搜索入口依赖后端模型网关配置；未配置模型时返回 `400`，模型调用或结构化校验失败时返回 `502`。证据列表默认每次最多返回 10 条，删除操作会真实移除本地证据记录。

## 分析师视角

```text
GET /api/analyst-profiles
GET /api/companies/1/analysis/runs/latest
GET /api/companies/1/analysis/runs?run_type=analyst_view&status=success
POST /api/companies/1/analysis/runs
POST /api/companies/1/analysis/runs/batch
DELETE /api/companies/1/analysis/runs/10
```

分析师视角模块只读取当前已入库的公司、财务、公告和外部证据快照，不主动联网搜索，也不继承历史 run。单个生成请求使用 `analyst_profile` 指定一个 Profile；批量生成请求可传多个 Profile，单个失败不会阻断其他 Profile。最新 run 接口默认返回同公司同 Profile 的最新成功分析。
