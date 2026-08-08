# API 草案

当前仅实现开发环境健康检查：

```text
GET /api/health
GET /api/companies
GET /api/companies/{company_id}
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

公司列表：

```text
GET /api/companies?q=护城河&limit=20&offset=0
```

公司档案：

```text
GET /api/companies/1
```

响应：

```json
{
  "id": 1,
  "ticker": "VI0001",
  "exchange": "SIM",
  "name": "护城河消费样本",
  "industry": "消费品",
  "description": "用于验证公司搜索和档案入口的本地示例公司。",
  "listed_date": "2018-01-15",
  "status": "重点跟踪",
  "tags": ["护城河", "高ROIC"],
  "created_at": "2026-08-09T00:00:00Z",
  "updated_at": "2026-08-09T00:00:00Z"
}
```

响应：

```json
{
  "items": [
    {
      "id": 1,
      "ticker": "VI0001",
      "exchange": "SIM",
      "name": "护城河消费样本",
      "industry": "消费品",
      "description": "用于验证公司列表、财务报表和分析结果结构的本地示例公司。",
      "listed_date": "2018-01-15",
      "status": "重点跟踪",
      "tags": ["护城河", "高ROIC", "现金流"],
      "created_at": "2026-08-09T00:00:00Z",
      "updated_at": "2026-08-09T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```
