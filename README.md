# Value Investment

本项目是一个本地优先的价值投资研究工作台。第一阶段采用 React + Vite + TypeScript 前端、FastAPI 后端和 SQLite 预留结构，先完成最小可运行开发环境。

## 环境说明

- 操作系统：Windows
- 终端：PowerShell
- Python：3.11.x
- Node.js：24.x
- npm：11.x
- 后端：FastAPI
- 前端：React + Vite + TypeScript
- 数据库：SQLite 预留，后续再接迁移和表结构
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

### 首次初始化

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

前端：

```powershell
cd frontend
npm install
```

### 日常启动

后端：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

## 当前范围

- `GET /api/health` 后端健康检查。
- `GET /api/companies` 公司列表和基础搜索。
- `GET /api/companies/{company_id}` 公司档案详情。
- 前端公司搜索页和公司档案页入口。
- SQLite 数据库自动建表和最小种子数据。
- Dashboard 工作台空壳。
- 前后端开发脚本和基础验证命令。
- `memory/` 中保留跨对话开发记录。

## 验证命令

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

```powershell
cd frontend
npm test
npm run build
```
