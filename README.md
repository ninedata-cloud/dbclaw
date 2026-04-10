# DBGuard

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg) ![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)

## 简介 / Overview

DBGuard 是一个 AI 驱动的数据库运维平台，面向多种主流数据库提供智能诊断、主动监控、自动巡检和告警通知能力。它采用 FastAPI + 原生 JavaScript 架构，无需前端构建步骤，开箱即可运行。平台内置技能系统与意图感知 AI Agent，可根据用户问题自动选择合适的诊断能力和响应方式。除了数据库本身，DBGuard 还支持通过 SSH 采集主机级指标，帮助运维人员统一查看数据库与主机健康状态。

DBGuard is an AI-powered database operations platform designed for intelligent diagnostics, proactive monitoring, automated inspections, and alert notifications across multiple database engines. It uses a FastAPI backend with a vanilla JavaScript frontend, so there is no frontend build step required. The platform includes a built-in skills system and an intent-aware AI agent that can adapt its responses based on user intent. In addition to database monitoring, DBGuard can collect host-level metrics over SSH, giving operators a unified view of database and infrastructure health.

## ✨ 核心特性 / Features

- **智能诊断 / Intelligent Diagnostics**：通过 YAML 技能系统扩展数据库诊断能力，支持 AI 自动调用。
- **主动监控 / Proactive Monitoring**：持续采集数据库与主机指标，识别健康状态与异常趋势。
- **自动巡检 / Automated Inspections**：按计划执行巡检任务，支持阈值规则和去重窗口。
- **告警通知 / Alerting & Notifications**：支持活跃告警、自动恢复、Webhook 与钉钉等通知渠道。
- **多数据库支持 / Multi-Database Support**：支持 MySQL、PostgreSQL、Oracle、SQL Server、MongoDB、Redis、TiDB、OceanBase、openGauss 等。
- **无构建前端 / No-Build Frontend**：原生 JavaScript SPA，部署简单，便于定制和排障。

## 🖥 架构 / Architecture

```text
Browser SPA (Vanilla JS)
        |
        v
FastAPI Backend
  ├─ Routers / REST APIs
  ├─ Intent-aware AI Agent
  ├─ Skills Registry / Executor
  ├─ Inspection Service
  ├─ Alert Service / Notification Dispatcher
  ├─ Metric Collector / Host Collector
  └─ Integration Scheduler
        |
        +--> PostgreSQL (metadata)
        +--> PostgreSQL-backed document knowledge
        +--> Target Databases / Hosts
```

> 架构截图与界面预览可后续补充到 `docs/`。
>
> Architecture screenshots and UI previews can be added later under `docs/`.

## 🚀 部署安装 / Production Deployment

### 环境要求 / Requirements

- Python 3.10+
- PostgreSQL 13+
- Linux/macOS 服务器
- 可选：OpenAI 兼容模型服务、博查搜索 API
- 可选：目标数据库访问权限、SSH 主机访问权限

### 1. 获取代码 / Get the Code

```bash
git clone <your-repository-url>
cd smartdba
```

### 2. 安装 Python 依赖 / Install Python Dependencies

建议先创建虚拟环境：

It is recommended to create a virtual environment first:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> `requirements.txt` 已按生产部署场景整理。若你暂时不接入某些数据库，可保留未使用驱动；仅 `pyodbc`、`oracledb`、`dmPython` 等驱动可能需要额外系统库或厂商客户端。
>
> `requirements.txt` is organized for production deployment. You can keep unused drivers installed, but drivers such as `pyodbc`, `oracledb`, and `dmPython` may require extra system libraries or vendor clients.

### 3. 配置环境变量 / Configure Environment

复制 `.env.example` 为 `.env`：

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

本地源码部署至少需要修改以下配置：

At minimum, update the following values:

```env
DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=9939
ENCRYPTION_KEY=<generate-a-random-fernet-key>
DATABASE_URL=postgresql+asyncpg://dbguard:<strong-password>@<db-host>:5432/dbguard
PUBLIC_SHARE_SECRET_KEY=<random-secret>
INITIAL_ADMIN_PASSWORD=<strong-admin-password>
OPENAI_API_KEY=<your-api-key>
OPENAI_BASE_URL=<your-openai-compatible-base-url>
OPENAI_MODEL=<your-model-name>
```

生成 Fernet 密钥：

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. 准备 PostgreSQL / Prepare PostgreSQL

先创建数据库和账号，并确保 `DATABASE_URL` 对应的用户具备建表权限。

Create the database and user first, and make sure the user in `DATABASE_URL` has permission to create tables.

示例：

Example:

```sql
CREATE DATABASE dbguard;
CREATE USER dbguard WITH PASSWORD '<strong-password>';
GRANT ALL PRIVILEGES ON DATABASE dbguard TO dbguard;
```

### 5. 启动服务 / Start the Service

```bash
python run.py
```

如果基础服务未准备好，启动前会先执行一轮中文自检，优先检查：

If the base services are not ready, DBGuard now performs a startup self-check before booting and prints actionable diagnostics for:

- 元数据库连接 / metadata database connectivity
- `ENCRYPTION_KEY` 与 `PUBLIC_SHARE_SECRET_KEY`
- 运行时目录可写性 / runtime directory writability
- 应用监听端口占用 / application port conflicts

首次启动会自动完成：

On first startup, DBGuard will automatically:

- 初始化元数据库表结构 / initialize metadata tables
- 执行内置迁移脚本 / run built-in migrations
- 创建默认管理员账号 / create the default admin account
- 启动指标采集、巡检、通知等后台任务 / start collectors, inspections, and notification workers

### 6. 访问系统 / Access the UI

- 地址 / URL: `http://<server-ip>:9939`
- 用户名 / Username: `admin`
- 密码 / Password: `INITIAL_ADMIN_PASSWORD` 对应的值

健康检查接口：

Health endpoints:

- `GET /health`：进程存活检查 / liveness
- `GET /health/live`：进程存活检查 / liveness
- `GET /health/ready`：关键依赖就绪检查 / readiness
- `GET /health/checks`：启动自检结果与当前检查详情 / startup and current self-check details

### Docker 单容器部署 / Single-Container Docker

内置 PostgreSQL 元数据库，首次启动不再强制要求你手工准备 `ENCRYPTION_KEY`、`PUBLIC_SHARE_SECRET_KEY`、`POSTGRES_PASSWORD`。容器会自动生成这些值并持久化到 `/app/data/bootstrap/runtime.env`。

The single-container image bundles PostgreSQL for metadata storage. On first startup, the container automatically generates and persists `ENCRYPTION_KEY`, `PUBLIC_SHARE_SECRET_KEY`, and `POSTGRES_PASSWORD` under `/app/data/bootstrap/runtime.env`.

```bash
docker build -t dbguard:latest .

docker run -d \
  --name dbguard \
  -p 9939:9939 \
  -v dbguard-pgdata:/var/lib/postgresql/data \
  -v dbguard-appdata:/app/data \
  -v dbguard-uploads:/app/uploads \
  dbguard:latest
```

首次登录信息：

First-login credentials:

- 用户名 / Username: `admin`
- 密码 / Password: `admin1234`

建议首次登录后立即修改管理员密码。

Change the admin password immediately after the first login.

### 生产环境建议 / Production Notes

- 将 `DEBUG` 设置为 `false`
- 如需自定义或纳管密钥，可显式传入 `ENCRYPTION_KEY`、`PUBLIC_SHARE_SECRET_KEY`、`POSTGRES_PASSWORD`
- 建议显式覆盖 `INITIAL_ADMIN_PASSWORD`，或在首次登录后立即修改默认密码 `admin1234`
- 通过 systemd、supervisor 或容器编排守护 `python run.py`
- 确保 PostgreSQL、目标数据库、SSH 网络访问策略已放通
- 若需通过 HTTPS 对外提供，建议在 Nginx / Caddy 后挂载运行

## ⚙️ 配置 / Configuration

| 变量 / Variable | 说明 / Description |
| --- | --- |
| `ENCRYPTION_KEY` | Docker 单容器下可自动生成并持久化；本地源码部署建议显式设置 / Auto-generated in single-container Docker; set explicitly for local source deployment |
| `DATABASE_URL` | PostgreSQL 元数据库连接串 / PostgreSQL metadata database URL |
| `PUBLIC_SHARE_SECRET_KEY` | Docker 单容器下可自动生成并持久化 / Auto-generated and persisted in single-container Docker |
| `INITIAL_ADMIN_PASSWORD` | 默认 `admin1234`，可通过环境变量覆盖 / Defaults to `admin1234`, can be overridden |
| `POSTGRES_PASSWORD` | Docker 单容器下可自动生成并持久化 / Auto-generated and persisted in single-container Docker |
| `OPENAI_API_KEY` | AI 模型服务密钥 / API key for AI model service |
| `OPENAI_BASE_URL` | AI 服务基础地址 / Base URL for AI service |
| `OPENAI_MODEL` | 默认模型名称 / Default model name |
| `BOCHA_API_KEY` | 博查 AI 网络搜索密钥（可选）/ Optional Bocha web search API key |
| `METRIC_INTERVAL` | 指标采集间隔（秒）/ Metric collection interval in seconds |
| `INSPECTION_DEDUP_WINDOW_MINUTES` | 巡检去重窗口（分钟）/ Inspection deduplication window |
| `ALERT_AGGREGATION_TIME_WINDOW_MINUTES` | 告警聚合窗口（分钟）/ Alert aggregation window |

## 📚 文档 / Documentation

- `AGENTS.md`：仓库协作说明与架构概览
- `docs/PRODUCT_INTRODUCTION.md`：产品介绍文档
- `docs/INTEGRATION_QUICKSTART.md`：集成系统快速上手
- `docs/DATASOURCE_SELECTOR_GUIDE.md`：数据源选择器说明
- `docs/SYSTEM_MANAGEMENT_SKILLS.md`：系统管理技能说明
- `docs/BOCHA_WEB_SEARCH_SKILL.md`：博查搜索技能说明
- `docs/archive/`：历史修复记录、设计稿与手工验证资料归档

## 📄 许可证 / License

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源协议。你可以自由使用、修改和分发本项目，但如果你分发修改版本，或将其作为网络服务提供给第三方使用，则需要按照 AGPL-3.0 的要求开放相应源码。

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. You are free to use, modify, and redistribute this software, but if you distribute modified versions or provide it to third parties as a network service, you must make the corresponding source code available under the AGPL-3.0 terms.

如果你希望在**闭源环境**中部署、二次开发或以 SaaS 形式提供而不履行 AGPL 开源义务，请联系项目作者获取商业授权。

If you need to deploy, modify, or offer this project in a **closed-source** environment or as a SaaS service without AGPL reciprocity obligations, please contact the project authors for a commercial license.

项目仓库地址占位：`https://github.com/your-org/dbguard`

Repository placeholder: `https://github.com/your-org/dbguard`
