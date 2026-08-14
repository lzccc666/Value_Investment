# Value Investment

本项目是一个本地优先的价值投资研究工作台。当前采用 React + Vite + TypeScript 前端、FastAPI 后端和 SQLite 本地数据库，已经具备公司档案、财务同步、公告摘要、外部证据和分析师视角的本地开发闭环。

## 环境说明

- 操作系统：Windows
- 终端：PowerShell
- Python：3.11.x
- Node.js：24.x
- npm：11.x
- 后端：FastAPI
- 前端：React + Vite + TypeScript
- 数据库：SQLite，启动时自动建表并写入基础公司种子数据
- 本地依赖目录：`backend/.venv`、`frontend/node_modules`

## 快速启动

```powershell
.\scripts\setup.ps1
.\scripts\dev.ps1
```

`setup.ps1` 会先使用默认 PyPI，若 Python 依赖安装失败且未设置 `PIP_INDEX_URL`，会自动用清华 PyPI 镜像重试一次。

启动后访问：

- 前端：http://127.0.0.1:5173
- 后端健康检查：http://127.0.0.1:8000/api/health
- 后端 OpenAPI：http://127.0.0.1:8000/docs

## 手动启动

### 完整流程

#### 1. 检查端口占用

```powershell
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen | Select-Object LocalPort,OwningProcess
```

如果看到输出，说明旧进程还在占端口。先看 PID 对应什么进程：

```powershell
Get-Process -Id 7668
```

#### 2. 关闭占用进程

如果你要一次性关闭 8000 和 5173 上的旧进程：

```powershell
$ports = 8000,5173
$pids = Get-NetTCPConnection -State Listen |
  Where-Object { $ports -contains $_.LocalPort } |
  Select-Object -ExpandProperty OwningProcess -Unique

$pids | ForEach-Object { Stop-Process -Id $_ -Force }
```

如果只想关某一个 PID：

```powershell
Stop-Process -Id 7668 -Force
```

如果 `Get-NetTCPConnection` 还显示端口被占用，但 `Stop-Process` 提示找不到 PID，说明这个监听记录已经不同步或被系统短暂挂住。此时直接换端口启动，或者重启 Windows 后再试。

#### 3. 首次初始化

只在第一次使用时执行一次：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

cd ..\frontend
npm install
```

#### 4. 日常启动

优先用一键脚本：

```powershell
cd D:\study\Python.Project\Value_Investment
.\scripts\dev.ps1
```

如果脚本提示端口占用，先执行第 2 步，再重启脚本。

如果你不想用默认端口，也可以改端口启动：

```powershell
.\scripts\dev.ps1 -BackendPort 8001 -FrontendPort 5174
```

如果 8000 迟迟释放不了，推荐直接这样启动：

```powershell
cd D:\study\Python.Project\Value_Investment
.\scripts\dev.ps1 -BackendPort 8001 -FrontendPort 5174
```

如果后端已经在其他端口运行，只想单独启动前端：

```powershell
cd D:\study\Python.Project\Value_Investment
.\scripts\dev.ps1 -FrontendOnly -BackendPort 8001 -FrontendPort 5174
```

如果只想单独启动后端：

```powershell
cd D:\study\Python.Project\Value_Investment
.\scripts\dev.ps1 -BackendOnly -BackendPort 8001
```

如果你要强行清理系统能看到的占用进程，可以用：

```powershell
.\scripts\dev.ps1 -Force
```

#### 5. 验证

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

```powershell
(Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing).StatusCode
```

#### 6. 停止

当前终端里运行 `.\scripts\dev.ps1` 时，直接按 `Ctrl+C`。

如果有残留后台进程，回到第 2 步按 PID 结束。

### 模型配置

模型网关默认走 DeepSeek 官方 OpenAI-compatible Chat Completions，不再使用中转站。

在 `backend/.env` 中配置：

```powershell
MODEL_PROVIDER=openai_compatible
MODEL_BASE_URL=https://api.deepseek.com
MODEL_API_KEY=你的DeepSeek官方APIKey
MODEL_NAME=deepseek-v4-pro
MODEL_WIRE_API=chat_completions
MODEL_DISABLE_RESPONSE_STORAGE=false
MODEL_TIMEOUT_SECONDS=180
```

前端公司工作台的“外部信息”区可以点击“模型自检”，先验证 key、base_url、model_name 和 JSON 输出能力，再运行外部信息搜索或分析师视角。

### 日志位置

`scripts/dev.ps1` 会把日志写入：

- `logs/backend.out.log`
- `logs/backend.err.log`
- `logs/frontend.out.log`
- `logs/frontend.err.log`

## 当前范围

- `GET /api/health` 后端健康检查。
- `GET /api/companies` 公司列表和基础搜索。
- `POST /api/companies` 手动新增公司主数据。
- `GET /api/companies/{company_id}` 公司档案详情。
- `POST /api/companies/{company_id}/profile/refresh` 更新公司上市日期和实时基本信息；股息率通过东方财富 F10 分红融资数据计算。
- `GET /api/companies/{company_id}/financials` 公司财务数据列表。
- `GET /api/companies/{company_id}/announcements` 公司公告列表。
- 前端公司搜索页和公司档案页入口。
- 公司搜索页在未选择公司时固定提供新增公司表单。
- 公司档案页展示基础简介、上市日期、东八区档案更新时间、东八区行情更新时间、实时基本信息、财务数据和公告区块；实时基本信息当前展示市值、价格、TTM市盈率、动态市盈率、静态市盈率、市净率、市销率、TTM股息率。
- 外部信息区支持模型配置自检、联网搜索、证据入库、人工复核和删除。
- 分析师视角区支持读取当前已入库快照，按多个投资框架生成独立分析 run，并支持历史查看和删除。
- SQLite 数据库自动建表，并增量写入常见 A 股、港股、美股真实公司主数据种子。
- Dashboard 工作台空壳。
- 前后端开发脚本和基础验证命令。
- `memory/` 中保留跨对话开发记录。

## 验证命令

```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
```

```powershell
cd frontend
npm test -- --run
npm run build
```
