
NineData DBClaw（数据库智能卫士）是一款 AI 原生的数据库诊断开源产品。它将数据库接入、指标监控、告警处理、自动巡检、知识增强和对话式诊断整合在一个私有化部署系统中，帮助 DBA、SRE 和平台团队更快发现问题、定位根因并沉淀运维经验。

## 开源地址
[https://github.com/ninedata-cloud/dbclaw](https://github.com/ninedata-cloud/dbclaw)

## 产品界面

![Database Monitor](https://github.com/ninedata-cloud/dbclaw/raw/main/docs/img/db_monitor.jpg)

![AI Diagnosis](https://github.com/ninedata-cloud/dbclaw/raw/main/docs/img/db_ai_diagnosis.jpg)

## 主要特性
- AI 智能诊断：基于 AI 大模型、意图识别、上下文构建和技能系统提供对话式诊断。
- 可扩展技能系统：通过 YAML 定义诊断技能，内置多类数据库运维技能，并可作为 AI Agent 工具调用。
- 数据源与主机告警、监控、诊断一体化，更全面的发现问题根因。
- 知识增强：支持文档知识接入，为 AI 分析和排障过程补充上下文。
- 云数据库集成：支持阿里云、腾讯云、华为云RDS数据库监控指标接入。
- 主流及时通信软件对接：支持飞书、钉钉、企业微信 webhook 告警对接。
- 机器人对话：支持飞书、钉钉、微信机器人对接。
- 多数据库统一纳管：支持 MySQL、PostgreSQL、Oracle、SQL Server、openGauss 和 SAP HANA。
- 主动监控与实时看板：持续采集数据库指标，并可通过 SSH 关联主机指标。
- 告警与通知分发：支持阈值告警、AI 判警、事件追踪、自动恢复、Webhook、邮件、钉钉、飞书和企业微信通知。
- 自动巡检：支持定时巡检、事件触发巡检、规则检查和结构化巡检报告。
- 任务调度管理：支持按 Cron 或固定间隔创建任务，统一管理启停、手动执行、运行历史和失败通知。



## 快速开始
### Docker 一键安装
```bash
# 使用 dockerhub 中央仓库
docker run -itd -p 9939:9939 --name dbclaw ninedata/dbclaw:latest
```

### 源码安装
### 环境要求

- Python 3.10+
- PostgreSQL 13+
- Linux 或 macOS 开发环境
- AI 大模型服务

### 1. 获取代码

```bash
git clone https://github.com/ninedata-community/dbclaw.git
cd dbclaw
```

### 2. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 准备配置

```bash
cp .env.example .env
```

至少需要为本地开发确认这些配置：

```env
APP_HOST=0.0.0.0
APP_PORT=9939
DATABASE_URL=postgresql+asyncpg://dbclaw:your-postgres-password@localhost:5432/dbclaw
ENCRYPTION_KEY=your-fernet-key-here
PUBLIC_SHARE_SECRET_KEY=replace-with-random-public-share-secret
INITIAL_ADMIN_PASSWORD=admin1234
```

生成 `ENCRYPTION_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

生产环境请使用强随机值替换 `PUBLIC_SHARE_SECRET_KEY` 和默认管理员密码。

### 4. 启动服务

```bash
python run.py
```

启动后访问：

- Web 控制台：`http://127.0.0.1:9939`
- 默认管理员：`admin`
- 默认密码：`admin1234`，可通过 `INITIAL_ADMIN_PASSWORD` 覆盖

首次登录后，建议先进入“AI 大模型管理”添加至少一个可用模型。未配置模型时，监控、巡检、数据源管理等基础能力仍可使用，但 AI 对话和 AI 诊断能力不可用。

## 任务调度管理

DBClaw 提供统一的任务调度能力，用于执行周期性运维任务，例如巡检触发、指标同步、通知分发或自定义自动化流程。

操作入口：

```text
左侧导航 -> 任务调度管理
```

主要能力包括：

- 新建任务：支持按 Cron 表达式或固定间隔（秒）配置执行计划。
- 状态管理：支持启用、停用任务，避免维护窗口期间误触发。
- 立即执行：支持手动触发单个任务，快速验证任务配置是否生效。
- 运行历史：查看每次运行的开始时间、结束时间、执行状态和错误信息。
- 失败通知：可按任务配置通知集成渠道，在任务异常时及时告警。

## Docker 自己 Build 单容器部署

项目提供单容器镜像，容器内包含 PostgreSQL、FastAPI 服务和静态前端。首次启动时，如果未显式提供运行密钥和数据库参数，容器会自动生成并持久化到 `/app/data/bootstrap/runtime.env`。

```bash
docker build -t dbclaw:latest .

docker run -d \
  --name dbclaw \
  -p 9939:9939 \
  -v dbclaw-pgdata:/var/lib/postgresql/data \
  -v dbclaw-appdata:/app/data \
  -v dbclaw-uploads:/app/uploads \
  dbclaw:latest
```

发布指定版本镜像时可注入构建信息：

```bash
docker build \
  --build-arg APP_VERSION=0.10.0 \
  --build-arg BUILD_COMMIT=$(git rev-parse --short HEAD) \
  --build-arg BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t dbclaw:0.10.0 .
```

持久化目录：

- `/var/lib/postgresql/data`：容器内 PostgreSQL 数据
- `/app/data`：应用运行数据、日志和自动生成配置
- `/app/uploads`：上传附件

## 配置说明

常用环境变量：

- `APP_HOST` / `APP_PORT`：服务监听地址和端口，默认 `0.0.0.0:9939`
- `DATABASE_URL`：PostgreSQL 元数据库连接串
- `ENCRYPTION_KEY`：数据库密码等敏感信息的 Fernet 加密密钥
- `PUBLIC_SHARE_SECRET_KEY`：公开分享链接签名密钥
- `INITIAL_ADMIN_PASSWORD`：初始管理员密码，默认 `admin1234`
- `METRIC_INTERVAL`：首次启动时的指标采集周期，默认 `60` 秒

AI 模型配置优先在 Web 控制台的“AI 大模型管理”中维护。`OPENAI_*` 环境变量仅作为兜底兼容配置。

## 健康检查

- `GET /health`：基础健康检查

## 开发

常用命令：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

运行测试：

```bash
python -m pytest
python -m pytest -m unit
python -m pytest -m service
python -m pytest -m api
python -m pytest --cov=backend --cov-report=term-missing
```

添加数据库诊断能力时，通常在 `backend/skills/builtin/` 中新增技能 YAML，并为技能声明参数、权限和异步执行逻辑。更多项目约定可参考 `AGENTS.md` 和 `CLAUDE.md`。

## 安全建议

- 部署后立即修改默认管理员密码。
- 生产环境必须使用强随机 `ENCRYPTION_KEY` 和 `PUBLIC_SHARE_SECRET_KEY`。
- 使用 HTTPS 或反向代理保护管理入口。
- 限制元数据库、数据库实例和 SSH 主机的网络访问范围。
- 定期备份 PostgreSQL 元数据库和 `/app/data`、`/app/uploads`。
- 对可编程适配器和自定义技能保持审计，它们可能访问敏感运维资源。

## 技术架构

DBClaw 采用轻量、易部署的架构：

- 后端：Python
- 前端：JavaScript SPA
- 数据库：PostgreSQL
- AI大模型：兼容OpenAI、Anthropic 大模型通用接口，支持DeepSeek、Qwen、MiniMax、GLM、Kimi、GPT、Claude 等主流大模型
- 部署方式：本地 Python 运行或 Docker 单容器运行

核心目录：

```text
backend/     FastAPI 后端、路由、服务、模型、技能系统
frontend/    原生 JavaScript 前端页面、组件和静态资源
docs/        产品、设计和实施文档
docker/      单容器启动脚本与 supervisor 配置
tests/       pytest 测试用例
run.py       本地启动入口
```

## 文档

- [更新日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)
- [数据库 Schema](docs/DATABASE_SCHEMA.md)

## 贡献

欢迎提交 Issue、功能建议、文档改进和代码补丁。参与贡献前，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

NineData DBClaw is released under the [MIT License](LICENSE).