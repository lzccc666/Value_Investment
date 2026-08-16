# Value Investment

本项目是一个本地优先的价值投资研究工作台。系统把公司主数据、财务底稿、公告、外部证据、分析师视角、投资备忘录、无价格锚定估值和价格决策串成一条可追溯的研究链路。

## 当前能力

研究主链路已实现 8 个模块：

1. `004` 公司搜索与公司档案
2. `005` 财务底稿与财务证据包
3. `006` 公告同步、正文读取与摘要
4. `007` 外部信息搜索与证据库
5. `008` 10 个分析师 Profile、40 条规则
6. `009` 综合投资备忘录与版本管理
7. `010` 五模型无锚定估值
8. `011` 价格对照、安全边际与投资决策

当前产品止于研究结论、估值和价格决策，不扩展到账户或交易管理。

独立运维模块 `012 数据管理` 不计入研究主链路的 8 个模块。它通过侧边栏的“数据管理”入口提供数据库概览、两阶段数据清理、版本保留、SQLite 一致性备份、恢复、初始化和压缩维护；概览页仍显示 `004-011 / 8 / 8`。

## 技术栈

- 后端：Python 3.11、FastAPI、SQLAlchemy、SQLite、Pydantic
- 前端：React 19、TypeScript、Vite、Lucide
- 测试：Pytest、Vitest、Testing Library
- 数据源：东方财富公司档案、行情、财务与公告接口；DuckDuckGo/Bing 外部搜索
- 模型：OpenAI-compatible API，可通过环境变量切换模型与 wire API

## 目录

```text
backend/          FastAPI 服务、领域服务、数据源和测试
frontend/         React 工作台和前端测试
data/             本地 SQLite 数据库
data/backups/     数据库备份、manifest 与自动备份设置
docs/api.md       当前 API 参考
memory/           当前架构与各模块实现说明
scripts/          Windows 初始化与启动脚本
```

## 快速启动

首次初始化：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

日常启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

脚本默认启动前端 `http://127.0.0.1:5173` 和后端 `http://127.0.0.1:8000`，并让 Vite 的 `/api` 代理指向本次后端端口。若端口被占用，可传入脚本支持的端口参数；实际参数以 `Get-Help .\scripts\dev.ps1 -Detailed` 为准。

手动启动后端：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

手动启动前端：

```powershell
Set-Location frontend
$env:VITE_BACKEND_PORT = "8000"
npm run dev
```

## 模型配置

在 `backend/.env` 中配置：

```dotenv
MODEL_BASE_URL=https://example.com/v1
MODEL_API_KEY=your-key
MODEL_NAME=your-model
MODEL_WIRE_API=chat_completions
MODEL_TIMEOUT_SECONDS=180
```

也支持带 `VALUE_INVESTMENT_` 前缀的同名变量。API 不会回传密钥。

## 验证

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m ruff check app
.\.venv\Scripts\python.exe -m pytest

Set-Location ..\frontend
npm test
npm run build
```

## 设计边界

- 008-010 的研究与估值阶段禁止使用市场价格作为计算锚点。
- 011 只绑定已完成的估值版本和对应 Memo，再引入当前价格。
- 模型负责结构化分析，估值与价格决策的核心公式由后端确定性计算。
- 所有研究结果保留来源快照、版本和人工复核入口。
- 所有破坏性数据库维护必须先预览，再用一次性令牌和确认短语执行；执行前默认创建备份。
- 当前是单机研究工具，不包含账户、交易执行、持仓或组合管理。
