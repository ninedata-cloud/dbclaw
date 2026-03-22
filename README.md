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
        +--> ChromaDB (vector knowledge base)
        +--> Target Databases / Hosts
```

> 架构截图与界面预览可后续补充到 `docs/`。
>
> Architecture screenshots and UI previews can be added later under `docs/`.

## 🚀 快速开始 / Quick Start

### 环境要求 / Requirements

- Python 3.10+
- PostgreSQL
- 可选：ChromaDB 持久化目录
- 可选：OpenAI 兼容模型服务、博查搜索 API

### 安装 / Installation

```bash
pip install -r requirements.txt
```

### 配置环境变量 / Configure Environment

复制 `.env.example` 为 `.env`，并至少配置以下项目：

Copy `.env.example` to `.env` and configure at least the following values:

```env
ENCRYPTION_KEY=your_fernet_key
DATABASE_URL=postgresql+asyncpg://dbguard:dbguard@localhost:5432/dbguard
JWT_SECRET_KEY=change_me
OPENAI_API_KEY=your_api_key
```

生成 Fernet 密钥：

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 启动服务 / Start the Service

```bash
python run.py
```

默认调试端口为 `9939`，前端静态资源由后端直接提供。

The default development port is `9939`, and the frontend static assets are served directly by the backend.

### 默认管理员账号 / Default Admin Account

- 用户名 / Username: `admin`
- 密码 / Password: `admin1234`

首次启动时会自动创建默认管理员账号。

The default administrator account is created automatically on first startup.

## ⚙️ 配置 / Configuration

| 变量 / Variable | 说明 / Description |
| --- | --- |
| `ENCRYPTION_KEY` | 必填。用于加密数据库密码等敏感信息 / Required. Used to encrypt sensitive credentials |
| `DATABASE_URL` | PostgreSQL 元数据库连接串 / PostgreSQL metadata database URL |
| `JWT_SECRET_KEY` | JWT 签名密钥 / JWT signing secret |
| `JWT_EXPIRE_MINUTES` | JWT 过期时间（分钟）/ JWT expiration in minutes |
| `OPENAI_API_KEY` | AI 模型服务密钥 / API key for AI model service |
| `OPENAI_BASE_URL` | AI 服务基础地址 / Base URL for AI service |
| `OPENAI_MODEL` | 默认模型名称 / Default model name |
| `BOCHA_API_KEY` | 博查 AI 网络搜索密钥（可选）/ Optional Bocha web search API key |
| `CHROMA_PERSIST_DIR` | ChromaDB 持久化目录 / ChromaDB persistence directory |
| `EMBEDDING_MODEL` | 向量化模型名称 / Embedding model name |
| `METRIC_INTERVAL` | 指标采集间隔（秒）/ Metric collection interval in seconds |
| `INSPECTION_DEDUP_WINDOW_MINUTES` | 巡检去重窗口（分钟）/ Inspection deduplication window |
| `ALERT_AGGREGATION_TIME_WINDOW_MINUTES` | 告警聚合窗口（分钟）/ Alert aggregation window |

## 📚 文档 / Documentation

- `CLAUDE.md`：代码库协作说明与架构概览
- `docs/PROGRAMMABLE_ADAPTER_GUIDE.md`：可编程适配器使用指南
- `docs/SYSTEM_MANAGEMENT_SKILLS.md`：系统管理技能说明
- `docs/BOCHA_WEB_SEARCH_SKILL.md`：博查搜索技能说明
- `docs/fixes/`：历史修复记录
- `docs/superpowers/specs/`：功能设计文档

## 📄 许可证 / License

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源协议。你可以自由使用、修改和分发本项目，但如果你分发修改版本，或将其作为网络服务提供给第三方使用，则需要按照 AGPL-3.0 的要求开放相应源码。

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. You are free to use, modify, and redistribute this software, but if you distribute modified versions or provide it to third parties as a network service, you must make the corresponding source code available under the AGPL-3.0 terms.

如果你希望在**闭源环境**中部署、二次开发或以 SaaS 形式提供而不履行 AGPL 开源义务，请联系项目作者获取商业授权。

If you need to deploy, modify, or offer this project in a **closed-source** environment or as a SaaS service without AGPL reciprocity obligations, please contact the project authors for a commercial license.

项目仓库地址占位：`https://github.com/your-org/dbguard`

Repository placeholder: `https://github.com/your-org/dbguard`
