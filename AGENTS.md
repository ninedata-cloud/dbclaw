# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

本文件为 Codex 在此代码库中工作时提供指导。
你是一位资深的软件开发工程师，精通AI、数据库、前后端全栈技术，负责本项目的代码研发。
过程中使用中文对话交流。

## 项目概述

DbGuard 是一个 AI 驱动的数据库运维平台，为多种数据库类型（MySQL、PostgreSQL、Oracle、SQL Server、DM、MongoDB、Redis、TiDB、OceanBase、openGauss）提供智能诊断、主动监控、自动巡检和告警通知。

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

**默认管理员账号**：`admin` / `admin1234`（首次启动自动创建）

**环境变量**（`.env` 文件，参考 `.env.example`）：
- `ENCRYPTION_KEY`：Fernet 加密密钥（必需）
- `DATABASE_URL`：PostgreSQL 连接串（默认 `postgresql+asyncpg://dbguard:dbguard@localhost:5432/dbguard`）
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`：AI 配置
- `BOCHA_API_KEY`：博查 AI 网络搜索（可选）

## 架构概述

### 后端结构

**核心应用流程**：`run.py` → `backend/app.py` → 创建带 lifespan 管理的 FastAPI 应用

**Lifespan 启动顺序**：
1. 初始化数据库（PostgreSQL via SQLAlchemy async） + 运行迁移
2. 写入默认系统配置（巡检去重、SMTP、阿里云）
3. 启动 SSH 连接池
4. 启动指标收集器（metric_collector）
5. 初始化知识库处理器（KB processor + ChromaDB）
6. 启动巡检服务（InspectionService）
7. 启动主机指标收集器（host_collector）
8. 启动通知分发器（notification_dispatcher）
9. 加载集成模板 + 启动集成调度器（integration_scheduler）

**已注册的 Router**：
- `backend/routers/`：auth、users、datasources、hosts、metrics、monitor_ws、chat、query、ai_models、knowledge_bases、inspections、system_configs、alerts、integrations
- `backend/api/skills.py`：技能管理 API

**核心架构模式**：

- **技能系统** (`backend/skills/`)：动态可扩展的诊断技能执行框架
  - 技能在 YAML 中定义（`backend/skills/builtin/*.yaml`）
  - Registry → Validator → Executor → Context 管道
  - 带权限控制的沙箱执行，技能自动成为 AI Agent 工具

- **意图感知 AI** (`backend/agent/`)：系统提示根据用户查询意图自适应
  - `intent_detector.py`：检测诊断/信息查询/管理操作意图
  - `prompts.py`：三种提示变体（DIAGNOSTIC / INFORMATIONAL / ADMINISTRATIVE）
  - `conversation_skills.py`：编排带技能选择的 AI 对话
  - `context_builder.py`：为 AI 构建上下文
  - `skill_selector.py`：动态技能到工具的转换

- **巡检服务** (`backend/services/inspection_service.py`)：定时自动巡检，支持按数据源配置计划和阈值规则，触发去重窗口（默认 60 分钟）

- **告警系统**：`threshold_checker.py` → `alert_service.py` / `alert_event_service.py` → `notification_dispatcher.py` → `notification_service.py`（Webhook、钉钉等），告警在指标恢复正常后自动解除

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
await context.search_kb(query, kb_ids, top_k=5)
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

多数据库支持 via `backend/services/db_connector.py`，各数据库专属 Service 在 `backend/services/` 下（mysql_service、postgres_service 等）。通过 `backend/utils/ssh_executor.py` + SSH 连接池支持 SSH 隧道。

## 重要约定

- **全异步**：所有数据库操作使用 async/await
- **Session 管理**：使用 `get_db()` 依赖注入获取 AsyncSession
- **错误处理**：Service 抛出带适当状态码的 HTTPException
- **安全性**：数据库密码用 Fernet 加密
- **元数据库**：PostgreSQL，通过 `DATABASE_URL` 配置
- **WebSocket**：`/ws/monitor` 端点提供实时指标

## 配置

所有设置在 `backend/config.py` 中从 `.env` 加载。关键配置项：
- `METRIC_INTERVAL`：指标收集间隔（默认 60s）
- `JWT_SECRET_KEY` / `JWT_EXPIRE_MINUTES`（默认 1440）
- `CHROMA_PERSIST_DIR` / `EMBEDDING_MODEL`：向量库配置
- `INSPECTION_DEDUP_WINDOW_MINUTES`（默认 60）
- `ALERT_AGGREGATION_TIME_WINDOW_MINUTES`（默认 5）
