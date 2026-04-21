# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

本文件为 Claude Code 在此代码库中工作时提供指导。
你是一位资深的软件开发工程师，精通 AI、数据库、前后端全栈技术，负责本项目的代码研发。
过程中使用中文对话交流。

## 项目概述

DBClaw（数据库智能卫士）是一个 AI 驱动的数据库运维平台，提供数据库诊断、监控、巡检和告警能力。

**架构**：FastAPI 后端 + 原生 JavaScript SPA（无构建步骤） + PostgreSQL 元数据库。

**支持的数据库类型**：
- MySQL
- PostgreSQL
- Oracle
- SQL Server
- TDSQL-C MySQL
- openGauss
- SAP HANA

**关键约束**：
- 元数据库只支持 PostgreSQL。
- 前端没有 npm / Vite / Webpack 构建链。
- AI 模型配置统一在前端"AI 大模型管理"中维护，环境变量 `OPENAI_*` 仅作兜底。
- 更完整的部署/环境变量说明优先看 `README.md`。

## 常用命令

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python run.py

# 生成加密密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 单个 pytest 测试
python -m pytest tests/test_alert_ai_service.py
python -m pytest tests/test_alert_ai_service.py -k compute_ai_transition

# 旧脚本式测试（部分测试仍可直接运行）
python tests/test_threshold_checker.py
python tests/test_skills.py

# 手动迁移
python backend/migrations/<migration_name>.py

# Docker 镜像
# docker build -t dbclaw:latest .
```

说明：
- 测试是 **pytest + 脚本式测试混合**。
- 当前仓库未看到统一的 lint / format / build 配置；不要假设存在 `npm run build`、`make lint`、`ruff` 或 `eslint`。

## 启动与运行时结构

- `run.py`：读取配置，先执行 `backend/services/startup_self_check.py`，再启动 Uvicorn。
- `backend/app.py`：FastAPI 入口，lifespan 中启动全部后台组件。
- `backend/database.py`：创建 async engine/session，`create_all`，创建默认管理员，加载内置技能和内置文档。

启动自检会阻断：
- `ENCRYPTION_KEY` 非法或未配置
- `PUBLIC_SHARE_SECRET_KEY` 未配置
- 运行时目录不可写
- PostgreSQL 元数据库不可连接
- 启动端口被占用（仅 `run.py` 启动路径）

健康接口：
- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /health/checks`（管理员）

`backend/app.py` lifespan 启动的关键后台组件：
1. 数据库初始化（`init_db`）+ 默认系统配置种子数据
2. SSH 连接池（`ssh_connection_pool`）
3. 指标收集器（`metric_collector`）
4. 文档知识初始化 + 内置文档种子
5. 巡检服务（`InspectionService`）
6. 主机指标收集器（`host_collector`）
7. 通知分发器（`notification_dispatcher`）
8. 集成模板加载 + 集成调度器（`integration_scheduler`）
9. IM 机器人：飞书长连接、钉钉 Stream、企业微信轮询器

## 核心业务链路

### 指标 → 告警 → 巡检

系统有两条指标入口，但都会汇总到 `DatasourceMetric(metric_type="db_status")`：

1. `backend/services/metric_collector.py`
   - 直连采集数据库状态
   - 有 `host_id` 时附加 SSH 主机指标
   - 写入快照后再进入阈值、基线、AI 判警
   - 连接失败走单独 `system_error` 告警分支

2. `backend/services/integration_scheduler.py`
   - 执行 `inbound_metric` 集成
   - 将外部指标与最近一次 `db_status` 快照合并后写回

巡检在 `backend/services/inspection_service.py`：
- 同时处理定时巡检和事件触发巡检
- 先写 `InspectionTrigger`，报告异步生成
- 会补默认 `InspectionConfig` 和默认告警模板
- 存在触发去重窗口

告警不只有阈值模式：
- `backend/services/alert_ai_service.py` 中实现了 AI 判警、置信度阈值、冷却期、连续确认次数等逻辑
- 当前存在 `threshold` / `ai` / `inherit` 等模式，改告警逻辑时不要只看阈值检查器

## AI / 技能 / 聊天

聊天主链路：
- `backend/routers/chat.py`：REST / WebSocket 入口、附件、审批、会话管理
- `backend/services/chat_orchestration_service.py`：拼装消息历史、知识库上下文、审批状态、诊断事件落库
- `backend/agent/conversation.py`：执行模型流式对话和工具调用循环

重要行为：
- 模型选择顺序：当前会话指定模型 → 数据库中首个启用模型 → 环境变量 `OPENAI_*`
- tool call / tool result / diagnosis event 会持久化
- 高风险工具带审批流

技能系统：
- 内置技能源码在 `backend/skills/builtin/*.yaml`（当前约 77 个内置技能）
- 启动时会加载进数据库；运行态主要读取数据库中的 skill 记录
- 核心文件：`backend/skills/registry.py`、`backend/skills/executor.py`、`backend/skills/context.py`
- `/api/skills/{id}/test` 当前只允许 builtin skill，自定义 skill 测试被禁用
- 技能分类包括：诊断类、查询类、系统命令类、网络工具类等
- 技能支持权限控制和沙箱执行，自动成为 AI Agent 工具

## 前端结构

- `frontend/index.html` 直接按顺序加载所有脚本，**script 顺序就是依赖顺序**
- `frontend/js/router.js` 是 hash 路由
- `frontend/js/app.js` 注册页面入口
- `frontend/js/api.js` 是集中式 API 客户端

`frontend/js/pages/instance-detail.js` 是当前单实例工作台主入口：
- 串联监控、流量、会话、AI 对话、SQL 窗口、告警、巡检、参数等视图
- `Router.navigate('sqlConsole')` 会重定向到 `instance-detail?datasource=<id>&tab=sqlConsole`

## 关键约定

- 全部数据库访问使用 async/await。
- 通过 `backend.database.get_db()` 注入 `AsyncSession`。
- 默认管理员用户名固定为 `admin`；密码优先取 `INITIAL_ADMIN_PASSWORD`，未配置时才回落到 `admin1234`。
- Schema 变更通常要同时考虑 `create_all` 和增量迁移脚本。
- 前端静态资源由 FastAPI 直接挂载 `/css`、`/js`、`/assets`、`/lib`，根路径 `/` 返回 `frontend/index.html`。
- 前端资源带版本号缓存控制（`?build=<version>`），有版本号的资源长期缓存，无版本号的强制重新验证。

## 已注册的 API Router

- `auth`：认证登录
- `user`：用户管理
- `datasource`：数据源管理
- `host`：主机管理
- `host_detail`：主机详情
- `terminal_ws`：WebSocket 终端
- `metrics`：指标查询
- `monitor_ws`：WebSocket 实时监控
- `chat`：AI 对话
- `query`：SQL 查询执行
- `instances`：实例管理
- `ai_model`：AI 模型管理
- `documents`：文档知识管理
- `skills`：技能管理
- `inspections`：巡检管理
- `system_config`：系统配置
- `alerts`：告警管理
- `alert_ai`：AI 告警策略
- `integration`：外部集成
- `integration_bots`：集成机器人
- `feishu_bot`：飞书机器人
- `dingtalk_bot`：钉钉机器人
- `weixin_bot`：企业微信机器人
