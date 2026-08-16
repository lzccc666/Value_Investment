# Value Investment API

FastAPI 后端为本地价值投资研究工作台提供数据采集、证据整理、模型分析、确定性估值和价格决策能力。

## 启动

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：`GET http://127.0.0.1:8000/api/health`

## 结构

```text
app/api/routes/       HTTP 路由
app/analysis/         模型网关、Profile 与 Prompt
app/data_sources/     东方财富与搜索提供方
app/db/               SQLAlchemy 模型、初始化和轻量迁移
app/schemas/          Pydantic 请求与响应模型
app/services/         领域服务和确定性计算
app/tests/            API、服务和数据源测试
```

## 数据库

默认数据库为项目根目录的 `data/value_investment.db`。启动时执行：

1. `Base.metadata.create_all()` 创建缺失表。
2. 轻量 SQLite 迁移补齐新增列、索引和兼容数据。
3. 幂等写入真实公司种子。

核心实体：`Company`、`FinancialStatement`、`Announcement`、`Evidence`、`AnalysisRun`、`InvestmentMemo`、`ValuationRun`、`PriceDecisionRun`。

SQLite 连接统一启用外键约束。`app/services/backup_service.py` 使用 SQLite Backup API 创建一致性备份，默认写入项目根目录 `data/backups/`；每份备份包含数据库文件和带 SHA-256、schema version、记录数及创建原因的 manifest。

## API 分组

- `/api/health`
- `/api/companies`
- `/api/evidence` 与公司证据接口
- `/api/analyst-profiles` 与公司分析接口
- `/api/companies/{id}/investment-memos`
- `/api/companies/{id}/valuation-runs`
- `/api/companies/{id}/price-decision-runs`
- `/api/data-management`

完整端点见 `../docs/api.md`。

## 模型网关

配置项位于 `app/core/config.py`，可通过 `backend/.env` 设置：

- `MODEL_BASE_URL`
- `MODEL_API_KEY`
- `MODEL_NAME`
- `MODEL_WIRE_API`
- `MODEL_REASONING_EFFORT`
- `MODEL_DISABLE_RESPONSE_STORAGE`
- `MODEL_TIMEOUT_SECONDS`

支持 OpenAI-compatible `chat_completions` 和 Responses 风格响应解析。证据搜索提供配置状态与 smoke test，但不会暴露 API key。

## 关键约束

- 分析、Memo 和估值输入保留来源引用及快照。
- 010 强制 price-blind，市场价格不得进入估值计算。
- 011 必须绑定同公司、已计算完成的 `ValuationRun` 及其固定 `InvestmentMemo`。
- 财务证据包、估值和价格决策均由确定性服务生成，模型输出不能直接覆盖公式结果。
- `PriceDecisionRun` 使用软删除；其他历史对象按各自接口管理。
- 数据管理使用 Preview/Execute 两阶段协议。一次性令牌绑定操作参数和数据库状态；维护期间其他写请求返回 `503`。
- `evidence_search`、`evidence_import_text` 和公告摘要运行不属于全局派生分析清理范围。

## 验证

```powershell
.\.venv\Scripts\python.exe -m ruff check app
.\.venv\Scripts\python.exe -m pytest
```
