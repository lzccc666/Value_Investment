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
| `GET` | `/api/health` | 返回服务状态、名称和版本 |

## 公司与档案

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/companies` | `q`、`limit=20`、`offset=0` | 搜索公司池 |
| `POST` | `/api/companies` | `CompanyCreate` | 新增公司 |
| `GET` | `/api/companies/{company_id}` | - | 公司详情 |
| `POST` | `/api/companies/{company_id}/profile/refresh` | - | 刷新档案和行情 |

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

`CompanyRead` 包含公司身份、行业、描述、上市日期、状态、标签、当前价格、市值、总股本、行情来源和行情更新时间。

## 财务底稿

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/companies/{company_id}/financials` | `limit=60`、`offset=0`、`period_limit`、`period_offset=0` | 财务记录；period 参数按报告期分页 |
| `GET` | `/api/companies/{company_id}/financials/evidence-pack` | - | 当前财务证据包 |
| `POST` | `/api/companies/{company_id}/financials/sync` | `limit=60` | 同步四类财务报表 |
| `DELETE` | `/api/companies/{company_id}/financials/{statement_id}` | - | 删除指定记录 |

财务同步响应包含获取、创建、更新数量和当前记录。证据包包含 facts、metrics、trends、flags、gaps、现金流质量、资本结构、估值准备度和来源信息。

## 公告

| 方法 | 路径 | 参数 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/companies/{company_id}/announcements` | `limit=20`、`offset=0` | 公告列表 |
| `POST` | `/api/companies/{company_id}/announcements/sync` | `years=1` | 同步公告，当前保留最多 50 条 |
| `POST` | `/api/companies/{company_id}/announcements/{announcement_id}/summarize` | - | 单条深度摘要 |
| `POST` | `/api/companies/{company_id}/announcements/summarize-all` | `limit` | 快速批量摘要 |
| `POST` | `/api/companies/{company_id}/announcements/summarize-all-deep` | `limit` | 深度批量摘要 |
| `DELETE` | `/api/companies/{company_id}/announcements/{announcement_id}` | - | 删除公告 |

批量摘要响应包含总数、成功数、失败数、跳过数、总体状态和逐条结果。

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
| `GET` | `/api/analyst-profiles` | - | 10 个 Profile 与 40 条规则 |
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

规则状态只能是 `pass`、`warn`、`fail`、`unknown`。

## 投资备忘录

| 方法 | 路径 | 参数/请求 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/companies/{company_id}/investment-memos/generate` | `{ "user_note": null }` | 生成新版本 |
| `GET` | `/api/companies/{company_id}/investment-memos/latest` | - | 最新有效 Memo |
| `GET` | `/api/companies/{company_id}/investment-memos` | `limit=20`、`offset=0` | 历史列表 |
| `GET` | `/api/investment-memos/{memo_id}` | - | Memo 详情 |
| `POST` | `/api/investment-memos/{memo_id}/archive` | - | 归档 |
| `DELETE` | `/api/investment-memos/{memo_id}` | - | 删除 |

生成响应包含生成运行 ID 和 `InvestmentMemoRead`。Memo 的 `sections` 保存委员会账本、评分卡、结构化正文和来源引用。

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

`ValuationRunRead` 保存 price-blind 审计、输入快照、建议/用户/最终假设、方法结果、三情景内在价值、敏感性、置信度和来源图。

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
  "safety_margin_override": 0.25
}
```

两个字段都可省略；未指定估值时选择当前公司最新的已完成估值，未覆盖安全边际时使用绑定 Memo 的建议值。响应保存绑定版本、行情快照、三情景内在价值和买入价、当前安全边际及价格状态。

## 数据范围边界

- API 不提供账户、持仓、组合或交易执行端点。
- 008-010 不接受市场价格作为估值输入。
- 011 只读取已完成估值、其绑定 Memo 和当前公司行情。
