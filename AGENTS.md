# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

本文件为 AI 代理在此代码库中工作时提供指导。
你是一位资深的软件开发工程师，精通 AI、数据库、前后端全栈技术，负责本项目的代码研发。
过程中使用中文对话交流。

## 项目概述

DBClaw（数据库智能卫士）是一个 AI 驱动的数据库运维平台，为多种数据库类型提供智能诊断、主动监控、自动巡检和告警通知。

**支持的数据库类型**：
- MySQL
- PostgreSQL
- Oracle
- SQL Server
- TDSQL-C MySQL
- openGauss
- SAP HANA

**架构**：FastAPI 后端 + 原生 JavaScript 前端（无构建步骤） + PostgreSQL 元数据存储

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端服务（调试模式下自动重载，端口 9939）
python run.py

# 前端从 /frontend 目录静态提供，无需构建

# 运行测试（各功能独立测试文件，无统一测试框架）
python tests/test_skills.py
python tests/test_threshold_checker.py
python tests/test_auto_resolve_alerts.py
python tests/test_deduplication.py

# 数据库迁移（启动时通过 SQLAlchemy create_all 自动执行）
# 手动迁移脚本：python backend/migrations/<migration_name>.py

# 生成加密密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**默认管理员账号**：`admin` / `admin1234`（首次启动自动创建，密码可通过 `INITIAL_ADMIN_PASSWORD` 环境变量覆盖）

**环境变量**（`.env` 文件，参考 `.env.example`）：
- `ENCRYPTION_KEY`：Fernet 加密密钥（必需）
- `PUBLIC_SHARE_SECRET_KEY`：公开分享链接签名密钥（必需）
- `DATABASE_URL`：PostgreSQL 连接串（默认 `postgresql+asyncpg://dbclaw:dbclaw@localhost:5432/dbclaw`）
- `INITIAL_ADMIN_PASSWORD`：初始管理员密码（可选，默认 `admin1234`）
- `BOCHA_API_KEY`：博查 AI 网络搜索（可选）

**AI 模型配置**：
- 统一由前端”AI 大模型管理”模块维护
- 环境变量 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` 仅作兜底

## 架构概述

### 后端结构

**核心应用流程**：`run.py` → `backend/app.py` → 创建带 lifespan 管理的 FastAPI 应用

**Lifespan 启动顺序**：
1. 运行启动自检（`startup_self_check`）：检查加密密钥、公开分享密钥、运行时目录、数据库连接
2. 初始化数据库（PostgreSQL via SQLAlchemy async）+ 运行 `create_all`
3. 写入默认系统配置（巡检去重、AI 告警、SMTP、阿里云、华为云、腾讯云等）
4. 启动 SSH 连接池（`ssh_connection_pool`）
5. 启动指标收集器（`metric_collector`）
6. 初始化文档知识与内置文档种子
7. 启动巡检服务（`InspectionService`）
8. 启动主机指标收集器（`host_collector`）
9. 启动通知分发器（`notification_dispatcher`）
10. 加载集成模板 + 启动集成调度器（`integration_scheduler`）
11. 启动 IM 机器人（飞书长连接、钉钉 Stream、企业微信轮询器）

**已注册的 Router**：
- `backend/routers/`：auth、user、datasource、host、host_detail、terminal_ws、metrics、monitor_ws、chat、query、instances、ai_model、documents、inspections、system_config、alerts、alert_ai、integration、integration_bots、feishu_bot、dingtalk_bot、weixin_bot
- `backend/api/skills.py`：技能管理 API

**核心架构模式**：

- **技能系统** (`backend/skills/`)：动态可扩展的诊断技能执行框架
  - 技能在 YAML 中定义（`backend/skills/builtin/*.yaml`，当前约 77 个内置技能）
  - Registry → Validator → Executor → Context 管道
  - 带权限控制的沙箱执行，技能自动成为 AI Agent 工具
  - 支持多种数据库类型的专属技能（MySQL、PostgreSQL、Oracle、SQL Server、HANA 等）

- **意图感知 AI** (`backend/agent/`)：系统提示根据用户查询意图自适应
  - `intent_detector.py`：检测诊断/信息查询/管理操作意图
  - `prompts.py`：三种提示变体（DIAGNOSTIC / INFORMATIONAL / ADMINISTRATIVE）
  - `conversation_skills.py`：编排带技能选择的 AI 对话
  - `context_builder.py`：为 AI 构建上下文
  - `skill_selector.py`：动态技能到工具的转换

- **巡检服务** (`backend/services/inspection_service.py`)：定时自动巡检，支持按数据源配置计划和阈值规则，触发去重窗口（默认 60 分钟）

- **告警系统**：
  - 阈值告警：`threshold_checker.py` → `alert_service.py` / `alert_event_service.py`
  - AI 告警：`alert_ai_service.py` 实现 AI 判警、置信度阈值、冷却期、连续确认次数等逻辑
  - 通知分发：`notification_dispatcher.py` → `notification_service.py`（Webhook、邮件、钉钉、飞书、企业微信等）
  - 告警在指标恢复正常后自动解除

- **主机监控**：`host_collector.py` 通过 SSH 连接池（`ssh_connection_pool.py`）收集 OS 级指标

- **适配器系统** (`backend/adapters/`)：可编程适配器对接第三方监控系统，用户在前端编写 Python 代码，以完整权限执行（无沙箱）。详见 `docs/PROGRAMMABLE_ADAPTER_GUIDE.md`

### AI Agent 对话流程

用户消息 → `chat.py` → 意图检测 → 上下文构建 → 技能选择 → 技能执行 → AI 综合响应

### 前端结构

原生 JavaScript SPA（`frontend/`），无构建步骤：
- `index.html`：主入口
- `js/pages/`：页面逻辑，`js/components/`：可复用组件
- `js/api.js`：集中式 API 客户端
- `lib/`：第三方库（CodeMirror、marked、highlight.js）

## 技能系统

添加数据库诊断能力时，在 `backend/skills/builtin/` 中创建技能 YAML，包含唯一 ID、参数定义、所需权限、Python 异步代码。

**技能中可用的 Context API**：
```python
await context.get_connection(connection_id)
await context.execute_query(query, connection_id)
await context.execute_command(command, connection_id)  # 需要主机配置
await context.get_metrics(connection_id, minutes=60)
await context.call_skill(skill_id, params)
```

**注意**：需要 OS 级访问的技能必须先检查数据源是否配置了 `host_id`，未配置时返回 `{"success": false, "error": "no_host_configured"}` 而非崩溃。

## 常见模式

### 添加新 API 端点

1. `backend/schemas/` 定义 Pydantic Schema
2. `backend/models/` 创建/更新 Model
3. `backend/services/` 实现业务逻辑
4. `backend/routers/` 创建 Router
5. `backend/app.py` 的 `create_app()` 中注册 Router

### 添加新后台任务

在 `backend/app.py` lifespan 中：`asyncio.create_task(your_function())`

### 加密凭据

```python
from backend.utils.encryption import encrypt_password, decrypt_password
```

### 数据库连接

多数据库支持 via `backend/services/db_connector.py`，各数据库专属 Service 在 `backend/services/` 下：
- `mysql_service.py`：MySQL 专属操作
- `postgres_service.py`：PostgreSQL 专属操作
- `oracle_service.py`：Oracle 专属操作
- `sqlserver_service.py`：SQL Server 专属操作
- `hana_service.py`：SAP HANA 专属操作
- `opengauss_service.py`：openGauss 专属操作

通过 `backend/utils/ssh_executor.py` + SSH 连接池支持 SSH 隧道连接。

## 重要约定

- **全异步**：所有数据库操作使用 async/await
- **Session 管理**：使用 `get_db()` 依赖注入获取 AsyncSession
- **错误处理**：Service 抛出带适当状态码的 HTTPException
- **安全性**：数据库密码用 Fernet 加密（`ENCRYPTION_KEY`）
- **元数据库**：PostgreSQL，通过 `DATABASE_URL` 配置
- **WebSocket**：`/ws/monitor` 端点提供实时指标，`/ws/terminal` 提供 Web 终端
- **启动自检**：`run.py` 启动前会执行 `startup_self_check`，检查关键配置和依赖
- **健康检查**：`/health`、`/health/live`、`/health/ready`、`/health/checks`（管理员）

## 配置

所有设置在 `backend/config.py` 中从 `.env` 加载。关键配置项：
- `ENCRYPTION_KEY`：Fernet 加密密钥（必需）
- `PUBLIC_SHARE_SECRET_KEY`：公开分享链接签名密钥（必需）
- `DATABASE_URL`：PostgreSQL 元数据库连接串
- `INITIAL_ADMIN_PASSWORD`：初始管理员密码（可选，默认 `admin1234`）
- `METRIC_INTERVAL`：指标收集间隔（默认 60s）
- `JWT_SECRET_KEY` / `JWT_EXPIRE_MINUTES`（默认 1440）
- `INSPECTION_DEDUP_WINDOW_MINUTES`（默认 60）
- `ALERT_AGGREGATION_TIME_WINDOW_MINUTES`（默认 5）
- `APP_HOST` / `APP_PORT`：服务监听地址和端口（默认 0.0.0.0:9939）
