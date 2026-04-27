# 数据库智能卫士 DBClaw

![License](https://img.shields.io/badge/license-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)
![Frontend](https://img.shields.io/badge/frontend-Vanilla%20JS-ffb300.svg)
![Version](https://img.shields.io/badge/version-0.9.3-blue.svg)

数据库智能卫士（英文名：DBClaw）是一款面向企业数据库运维场景的 AI 驱动平台，提供数据库监控、告警管理、自动巡检、智能诊断、知识增强和外部集成能力，帮助 DBA、SRE 和运维团队提升日常运维效率与故障定位速度。

## 📋 目录

- [产品定位](#产品定位)
- [核心能力](#核心能力)
- [支持的数据库](#支持的数据库类型)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [Docker 部署](#docker-单容器部署)
- [配置说明](#关键配置说明)
- [开发指南](#开发命令)
- [贡献指南](#贡献)
- [许可证](#license)

## 产品定位

数据库智能卫士聚焦“数据库智能监控诊断”场景，目标不是替代现有监控体系，而是在统一的数据源管理、指标采集、告警处理和 AI 对话能力之上，补齐诊断分析、知识沉淀和自动化巡检能力。

适用场景包括：

- 多数据库并存的企业环境
- 需要统一纳管数据库与主机状态的运维团队
- 希望引入 AI 辅助诊断和自动巡检的 DBA / SRE 团队
- 需要私有化部署、可扩展技能和可对接外部系统的平台团队

## 核心能力

- 数据源统一管理：统一接入和管理多种数据库实例，支持连接测试、标签分类和主机关联
- 主动监控：持续采集数据库指标与主机指标，支持实例详情与实时监控展示
- 告警中心：支持阈值告警、事件追踪、自动恢复、通知分发和历史回溯
- 自动巡检：支持定时巡检、规则检查、AI 辅助分析和结构化巡检报告
- AI 智能诊断：基于意图识别、上下文构建和技能选择，提供对话式诊断能力
- 技能系统：通过 YAML 定义诊断技能，支持持续扩展数据库运维能力
- 知识增强：支持文档知识接入，为 AI 对话和诊断提供上下文补充
- 外部集成：支持集成模板、入站指标采集、Webhook、邮件以及 IM 机器人能力

## 支持的数据库类型

当前产品支持的数据库类型包括：

- MySQL
- PostgreSQL
- Oracle
- SQL Server
- TDSQL-C MySQL
- openGauss
- SAP HANA

## 系统架构

项目采用以下技术架构：

- 后端：FastAPI
- 前端：原生 JavaScript SPA，无构建步骤
- 元数据库：PostgreSQL
- 指标采集：数据库指标采集 + SSH 主机指标采集
- AI 能力：OpenAI 兼容模型接口 + 意图识别 + 技能系统

核心运行链路：

```text
run.py
  -> backend/app.py
  -> FastAPI 应用生命周期初始化
     -> 数据库初始化与迁移
     -> 默认系统参数写入
     -> 指标采集器启动
     -> 巡检服务启动
     -> 主机采集器启动
     -> 通知分发器启动
     -> 集成模板加载与集成调度启动
```

## 目录结构

```text
backend/    FastAPI 后端、业务逻辑、路由、服务、技能系统
frontend/   原生 JavaScript 前端页面与组件
docs/       产品与功能文档
docker/     Docker 启动脚本与 supervisor 配置
tests/      功能测试脚本
run.py      本地开发启动入口
```

## 快速开始

### 环境要求

- Python 3.10+
- PostgreSQL
- Linux / macOS 开发环境
- 可选：可访问的 AI 模型服务，模型连接信息在“AI 大模型管理”中配置

### 1. 获取代码

```bash
git clone <your-repo-url> dbclaw
cd dbclaw
```

### 2. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

最少需要关注以下配置：

```env
APP_NAME=DBClaw
APP_HOST=0.0.0.0
APP_PORT=9939
ENCRYPTION_KEY=<fernet-key>
DATABASE_URL=postgresql+asyncpg://dbclaw:<password>@localhost:5432/dbclaw
PUBLIC_SHARE_SECRET_KEY=<random-secret>
INITIAL_ADMIN_PASSWORD=<admin-password>
```

生成 `ENCRYPTION_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. 启动服务

```bash
python run.py
```

默认访问地址：

- Web 控制台：`http://127.0.0.1:9939`
- 默认管理员账号：`admin`
- 默认管理员密码：`admin1234`，可通过 `INITIAL_ADMIN_PASSWORD` 覆盖

首次登录后，请先进入“AI 大模型管理”页面添加至少一个可用模型，否则 AI 对话、AI 诊断等能力无法使用。

## Docker 单容器部署

项目提供单容器部署方式，镜像内置 PostgreSQL、FastAPI 和静态前端。首次启动时，如果未显式提供运行所需密钥和数据库参数，容器会自动生成并写入 `/app/data/bootstrap/runtime.env`。

```bash
docker build -t dbclaw:latest .

# 发布或测试指定版本时，可注入构建信息
docker build \
  --build-arg APP_VERSION=0.9.10 \
  --build-arg BUILD_COMMIT=$(git rev-parse --short HEAD) \
  --build-arg BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t dbclaw:0.9.10 .

docker run -d \
  --name dbclaw \
  -p 9939:9939 \
  -v dbclaw-pgdata:/var/lib/postgresql/data \
  -v dbclaw-appdata:/app/data \
  -v dbclaw-uploads:/app/uploads \
  dbclaw:latest
```

## 关键配置说明

| 配置项 | 说明 |
| --- | --- |
| `ENCRYPTION_KEY` | 数据库密码等敏感信息的加密密钥 |
| `DATABASE_URL` | PostgreSQL 元数据库连接串 |
| `PUBLIC_SHARE_SECRET_KEY` | 对外分享能力使用的签名密钥 |
| `INITIAL_ADMIN_PASSWORD` | 初始管理员密码 |

## 监控采集周期

- 首次启动时，会使用环境变量 `METRIC_INTERVAL` 作为初始值
- 系统运行后，通过系统参数 `monitoring_collection_interval_seconds` 统一维护

## 健康检查与系统信息接口

- `GET /health`：基础存活检查
- `GET /health/live`：进程存活检查
- `GET /health/ready`：依赖就绪检查
- `GET /health/checks`：启动自检和当前检查结果，需要管理员权限
- `GET /api/app/info`：应用名称、版本号、构建信息


## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
python run.py

# 运行测试
python -m pytest

# 运行特定测试
python -m pytest tests/test_skills.py

# 按分层运行（推荐）
python -m pytest -m unit
python -m pytest -m service
python -m pytest -m api

# 覆盖率门禁（见 pytest.ini）
python -m pytest --cov=backend --cov-report=term-missing

# 生成加密密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 贡献

我们欢迎所有形式的贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与项目。

### 报告问题

如果您发现 Bug 或有功能建议，请在 [GitHub Issues](https://github.com/ninedata/dbclaw/issues) 中创建新问题。

### 安全漏洞

如果您发现安全漏洞，请查看 [SECURITY.md](SECURITY.md) 了解如何负责任地报告。

## 文档

- [更新日志](CHANGELOG.md) - 版本变更记录
- [贡献指南](CONTRIBUTING.md) - 如何为项目做贡献
- [安全策略](SECURITY.md) - 安全最佳实践和漏洞报告
- [项目说明](CLAUDE.md) - 项目架构和开发指南

## 常见问题

### 如何修改管理员密码？

首次登录后，点击右上角用户头像 → 修改密码。

### 如何配置 AI 模型？

登录后进入"AI 大模型管理"页面，添加 OpenAI 兼容的模型配置。

### 支持哪些 AI 模型？

支持所有 OpenAI 兼容接口的模型，包括：
- OpenAI GPT-4/GPT-3.5
- Anthropic Claude
- 国内大模型（通义千问、文心一言、智谱 GLM 等）

### Docker 部署时如何持久化数据？

使用 Docker Volume 挂载以下目录：
- `/var/lib/postgresql/data` - PostgreSQL 数据
- `/app/data` - 应用运行数据
- `/app/uploads` - 上传文件

### 如何备份数据？

备份元数据库即可：
```bash
docker exec dbclaw pg_dump -U dbclaw dbclaw > backup.sql
```

## 技术栈

**后端**：
- FastAPI - Web 框架
- SQLAlchemy - ORM
- AsyncPG - PostgreSQL 异步驱动
- Pydantic - 数据验证
- APScheduler - 任务调度

**前端**：
- 原生 JavaScript (ES6+)
- Monaco Editor - 代码编辑器
- Lucide Icons - 图标库
- Chart.js - 图表库

**数据库驱动**：
- aiomysql - MySQL
- asyncpg - PostgreSQL
- oracledb - Oracle
- pyodbc/pymssql - SQL Server
- hdbcli - SAP HANA

## 性能指标

- 支持管理数据库实例数：1000+
- 单实例指标采集周期：15-60 秒（可配置）
- AI 对话响应时间：< 5 秒（取决于模型）
- 并发用户数：100+（单容器部署）

## 路线图

- [ ] 支持更多数据库类型（MongoDB、Redis、ClickHouse）
- [ ] 增强 AI 诊断能力（根因分析、自动修复建议）
- [ ] 支持多租户和 RBAC
- [ ] 提供 Kubernetes Operator
- [ ] 支持分布式部署
- [ ] 移动端适配

## License

[MIT](LICENSE)
