# 价值投资工作台_v1_20260823

`Value Investment Workbench`

当前已支持 A 股、港股、美股三市场的公司数据收集、估值分析与安全边际计算，并附带数据管理和参数管理系统。系统把公司主数据、财务底稿、公告、外部证据、分析师视角、投资备忘录、无价格锚定估值和价格决策串成一条本地优先、证据驱动、可追溯的研究链路，并提供与研究主链路隔离的投资小工具。

> **重要声明：工作台所有结论仅供参考，不构成投资建议。**

> 项目状态：代码持续优化中，小工具持续开发中。

## 当前能力

研究主链路已实现 8 个模块：

1. `004` 公司搜索与公司档案
2. `005` 财务底稿与财务证据包
3. `006` 公告同步、正文读取与摘要
4. `007` 外部信息搜索与证据库
5. `008` 8 个分析师 Profile、32 条规则与五状态判断
6. `009` 综合投资备忘录与版本管理
7. `010` 五模型无锚定估值
8. `011` 价格对照、安全边际与投资决策

当前产品止于研究结论、估值和价格决策，不连接券商账户，不执行交易。

系统现已支持 A 股、港交所普通股以及 NASDAQ/NYSE/AMEX 普通股和 ADS 的统一研究合同。`Company` 是发行人级研究根，`SecurityListing` 承载同一发行人的多地上市证券；Apple `AAPL.US`、腾讯 `00700.HK` 和阿里巴巴 `09988.HK`/`BABA.US` 均有固定离线样本覆盖 004-011。行情与 FX 每次刷新创建不可变快照，011 冻结 Listing、币种、证券单位比率、行情、汇率及换算审计。

独立运维模块 `012 数据管理` 不计入研究主链路的 8 个模块。它通过侧边栏的“数据管理”入口提供数据库概览、两阶段数据清理、版本保留、SQLite 一致性备份、恢复、初始化和压缩维护；概览页仍显示 `004-011 / 8 / 8`。

独立配置模块 `013 参数配置` 提供数据采样、财务预警、市场数据、分析师引擎、估值规则矩阵、Memo 决策、估值模型和价格决策八个配置域。参数发布执行完整校验并原子更新；新配置只影响后续运行，不追溯改写历史结果。

独立模块 `015 投资小工具` 同样不计入研究主链路。它提供按具体 Listing 和证券数量记录的历史持仓快照、基于最新行情与 FX 的多币种组合估值、冻结历史 011 结果的买入备忘录，以及 A 股 QVIX、港股 VHSI、美股 VIX 的日频市场温度；不接入账户、交易或收益归因。

## 技术栈

- 后端：Python 3.11、FastAPI、SQLAlchemy、SQLite、Pydantic
- 前端：React 19、TypeScript、Vite、Lucide
- 测试：Pytest、Vitest、Testing Library
- 数据源：东方财富 A 股数据；固定版本 AKShare 与 HKEXnews 港股数据；SEC EDGAR/Company Facts 美股数据；ECB 日参考汇率；Cboe VIX、恒生 VHSI、AKShare 50ETF QVIX；DuckDuckGo/Bing 外部搜索
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

SEC EDGAR JSON/Archives 不需要注册账号或 API Key；真实来源检查只要求在 `backend/.env` 配置包含应用名和有效联系邮箱的 `SEC_USER_AGENT`，用于满足 SEC 自动访问身份声明。AKShare、HKEX 和 ECB 的真实检查脚本位于 `scripts/`；标准 pytest 只使用固定 fixture，不访问外网。

SEC Company Facts 的标准标签覆盖度因发行人和期间而异。系统只映射显式维护的标准 taxonomy/tag，保留原始 `source_tags` 与候选选择 `mapping_diagnostics` 供审计；缺少最新期间事实时显示具体数据缺口，不用历史值或 0 猜测。SEC submissions 通常只提供 `10-Q`、`10-K`、`8-K` 等官方表单代码，公告页会组合表单含义与报告期生成中文可读标题，同时保留原始 form、accession 和官方链接。

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

- 008-010 的输入、输出和对应 UI 禁止出现当前价格、市值、行情快照、FX、目标价或交易动作。
- 010 固定聚合 8 个 Profile、32 条规则、13 个维度和 117 个系数，并独占动态安全边际计算。
- 011 只绑定已完成的估值版本和对应 Memo，再引入目标 Listing 的不可变行情；跨币种时同时绑定不可变 FX 快照。
- 缺失估值币种、share basis、ADS/ADR 比率、行情或汇率时明确阻断，不猜测。
- 模型负责结构化分析，估值与价格决策的核心公式由后端确定性计算。
- 所有研究结果保留来源快照、版本和人工复核入口。
- 所有破坏性数据库维护必须先预览，再用一次性令牌和确认短语执行；执行前默认创建备份。
- 参数中心当前有 8 个域和 377 个实际数值；`market_data` 只开放新 011 的行情与 FX 时效，发布不追溯修改历史。
- 当前是单机研究工具；015 只维护人工录入的持仓数量、用户选定的历史 011 冻结摘要和市场温度缓存，组合金额与权重均为派生值；不包含券商账户同步、成本收益归因或交易执行。
