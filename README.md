# DBClaw

[简体中文](README.md) | [English](README_EN.md)

![License](https://img.shields.io/badge/license-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)
![Frontend](https://img.shields.io/badge/frontend-Vanilla%20JS-ffb300.svg)
![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)

NineData DBClaw is an open-source, AI-native database diagnostics platform. It provides AI-powered diagnostics, monitoring and alerting, automated inspections, and other capabilities for multiple database systems. It also integrates with platforms such as Feishu, DingTalk, and WeChat, helping DBAs, SREs, and other technical teams identify problems, locate root causes, and retain operational knowledge more efficiently.

## Product Screenshots

![Database performance monitoring](docs/img/db_monitor.jpg)

![AI-powered diagnostics](docs/img/db_ai_diagnosis.jpg)

## Key Features

- AI-powered diagnostics: Provides conversational diagnostics through large language models, intent recognition, context construction, and a skill system.
- Extensible skill system: Defines diagnostic skills in YAML, includes built-in database operations skills, and exposes skills as tools for AI agents.
- Unified alerting, monitoring, and diagnostics for data sources and hosts, enabling more comprehensive root-cause analysis.
- Knowledge augmentation: Supports document-based knowledge sources to enrich the context available during AI analysis and troubleshooting.
- Cloud database integration: Supports database monitoring metrics from Alibaba Cloud, Tencent Cloud, and Huawei Cloud RDS.
- Integration with popular instant-messaging platforms: Supports webhook alerts for Feishu, DingTalk, and WeCom.
- Chatbots: Supports Feishu, DingTalk, and WeChat bots.
- Unified management for multiple databases: Supports MySQL, PostgreSQL, Oracle, SQL Server, openGauss, OceanBase MySQL, and SAP HANA.
- Proactive monitoring and real-time dashboards: Continuously collects database metrics and can associate them with host metrics over SSH.
- Alerting and notification delivery: Supports threshold alerts, AI-assisted alert evaluation, event tracking, automatic recovery, webhooks, email, DingTalk, Feishu, and WeCom notifications.
- Automated inspections: Supports scheduled inspections, event-triggered inspections, rule checks, and structured inspection reports.
- Task scheduling: Supports Cron-based and fixed-interval tasks, with centralized controls for activation, manual execution, execution history, and failure notifications.

## Quick Start

### One-Command Docker Installation

```bash
# Use Docker Hub
docker run -itd -p 9939:9939 --name dbclaw ninedata/dbclaw:latest

# Use Huawei Cloud Container Registry
docker run -itd -p 9939:9939 --name dbclaw swr.cn-east-3.myhuaweicloud.com/ninedata/dbclaw:latest
```

### Install from Source

#### Requirements

- Python 3.10+
- PostgreSQL 13+ (the **TimescaleDB** extension is recommended to optimize time-series storage for monitoring metrics; the connection string remains `postgresql+asyncpg://...`)
- A Linux or macOS development environment
- Access to a large language model service

#### 1. Clone the Repository

```bash
git clone https://github.com/ninedata-community/dbclaw.git
cd dbclaw
```

#### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### 3. Prepare the Configuration

```bash
cp .env.example .env
```

At a minimum, verify the following settings for local development:

```env
APP_HOST=0.0.0.0
APP_PORT=9939
DATABASE_URL=postgresql+asyncpg://dbclaw:your-postgres-password@localhost:5432/dbclaw
ENCRYPTION_KEY=your-fernet-key-here
PUBLIC_SHARE_SECRET_KEY=replace-with-random-public-share-secret
INITIAL_ADMIN_PASSWORD=admin1234
```

Generate an `ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

In production, replace `PUBLIC_SHARE_SECRET_KEY` and the default administrator password with strong random values.

#### 4. Start the Service

```bash
python run.py
```

After startup, open:

- Web console: `http://127.0.0.1:9939`
- Default administrator: `admin`
- Default password: `admin1234` (override it with `INITIAL_ADMIN_PASSWORD`)

After signing in for the first time, we recommend adding at least one available model under **AI Model Management**. Core features such as monitoring, inspections, and data source management remain available without a configured model, but AI chat and AI diagnostics will be unavailable.

## Task Scheduling

DBClaw provides unified task scheduling for recurring operational work, such as triggering inspections, synchronizing metrics, delivering notifications, and running custom automation workflows.

Navigation:

```text
Left navigation -> Task Scheduling
```

Key capabilities include:

- Create tasks: Configure schedules with Cron expressions or fixed intervals in seconds.
- Manage status: Enable or disable tasks to prevent unintended execution during maintenance windows.
- Run immediately: Manually trigger an individual task to quickly verify its configuration.
- Execution history: Review the start time, end time, status, and error details for each run.
- Failure notifications: Configure notification integrations for each task to receive alerts when execution fails.

## Build and Deploy a Single Docker Container

The project provides a single-container image that includes PostgreSQL, the FastAPI service, and the static frontend. On first startup, if runtime keys and database settings are not explicitly provided, the container generates them automatically and persists them to `/app/data/bootstrap/runtime.env`.

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

To publish an image for a specific version, pass build metadata:

```bash
docker build \
  --build-arg APP_VERSION=1.0.0 \
  --build-arg BUILD_COMMIT=$(git rev-parse --short HEAD) \
  --build-arg BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t dbclaw:1.0.0 .
```

Persistent directories:

- `/var/lib/postgresql/data`: PostgreSQL data inside the container
- `/app/data`: Application runtime data, logs, and auto-generated configuration
- `/app/uploads`: Uploaded attachments

## Configuration

Common environment variables:

- `APP_HOST` / `APP_PORT`: Service listen address and port; defaults to `0.0.0.0:9939`
- `DATABASE_URL`: PostgreSQL metadata database connection string (the same connection string is used with TimescaleDB)
- `TIMESCALE_*`: Optional settings that control Timescale migrations, whether startup should stop if the extension is unavailable, chunk intervals, compression, metric retention, and more. See `.env.example` for details.
- `ENCRYPTION_KEY`: Fernet encryption key for database passwords and other sensitive values
- `PUBLIC_SHARE_SECRET_KEY`: Signing key for public share links
- `INITIAL_ADMIN_PASSWORD`: Initial administrator password; defaults to `admin1234`
- `METRIC_INTERVAL`: Metric collection interval on first startup; defaults to `60` seconds

AI model settings should preferably be managed through **AI Model Management** in the web console. The `OPENAI_*` environment variables are retained only as fallback compatibility settings.

### Metadata Database and TimescaleDB

DBClaw writes data source and host monitoring snapshots to tables such as `datasource_metric` and `host_metric`. Using **TimescaleDB**, an extension for PostgreSQL, enables time-based partitioning (hypertables), chunk-level compression, and optional data retention policies for this time-series data.

- **Single-container Docker image**: TimescaleDB is preinstalled, and PostgreSQL starts with `shared_preload_libraries=timescaledb`. During initial database setup, the container runs `CREATE EXTENSION IF NOT EXISTS timescaledb`.
- **Self-managed PostgreSQL**: Install the TimescaleDB version that matches your PostgreSQL major version, set `shared_preload_libraries = 'timescaledb'` in `postgresql.conf` or the startup command, restart PostgreSQL, and then run `CREATE EXTENSION timescaledb;` in the target database as a superuser or another authorized role. If you do not want to install the extension yet, leave `TIMESCALE_REQUIRE_EXTENSION=false` (the default). The application will log a notice, skip the hypertable step, and continue using standard PostgreSQL.
- **Upgrading an existing instance**: During startup, migrations adjust the primary keys of these tables to `(id, collected_at)` when required and create hypertables. On large tables, altering the primary key may briefly lock the table. Perform the upgrade during off-peak hours and create a backup first.
- **Automatic metric deletion**: A retention policy is added only when `TIMESCALE_RETENTION_INTERVAL` is explicitly set to a PostgreSQL `interval` value such as `90 days`. If it is empty, historical metrics are not deleted automatically based on age.

## Console Languages

The web console supports Simplified Chinese (`zh-CN`) and English (`en-US`) through a registry that can accept additional BCP 47 locales. Locale and IANA time-zone preferences are stored on the account through `PUT /api/auth/me/locale`. Before login, the locale selection is stored in the browser's `localStorage`. Switching languages preserves the current URL and login state; if an editor or form contains unsaved changes, the console asks for confirmation first.

Console API requests include `X-DBClaw-Locale`. The server selects the response language in the following order: request header, account preference, `Accept-Language`, then Simplified Chinese. It also returns `Content-Language`. Error responses retain the backward-compatible `detail` field while providing a stable error code and interpolation parameters:

```json
{
  "detail": "Datasource not found",
  "error_code": "datasource.not_found",
  "params": { "datasource_id": 12 }
}
```

AI chat passes the resolved language to the model as the target output language. Inspection jobs snapshot locale and time zone when they are created; reports preserve those generation settings. Alert messages store a stable message code and structured parameters where possible, and notifications render per recipient or subscription override. Built-in documents are seeded as independent Chinese and English editions linked by `translation_group_id`; built-in skill YAML files carry bilingual names, descriptions, parameter help, and permission help. SQL, commands, identifiers, user input, vendor-specific technical details, and quoted source text are never automatically translated. Historical natural-language content is preserved and labelled with its known language or `und`.

## Health Check

- `GET /health`: Basic health check

## Development

Common commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Run tests:

```bash
python -m pytest
python -m pytest -m unit
python -m pytest -m service
python -m pytest -m api
python -m pytest --cov=backend --cov-report=term-missing
npm install
npm run lint:i18n
npm run test:i18n
npx playwright install chromium
npm run test:e2e
```

`lint:i18n` uses JavaScript and Python AST checks to reject hard-coded UI copy, raw HTTP error details, and exception strings sent to clients. It also validates all built-in document translation groups and skill metadata; the required result is zero violations, with no compatibility baseline. `test:i18n` validates Chinese/English key and interpolation parity. Playwright covers first visits, account preferences, unsaved-change protection, and bilingual rendering across key console routes. Node.js and Playwright are not required in production.

To add database diagnostic capabilities, you will usually create a skill YAML file under `backend/skills/builtin/` and declare the skill's parameters, permissions, and asynchronous execution logic. See `AGENTS.md` and `CLAUDE.md` for additional project conventions.

## Security Recommendations

- Change the default administrator password immediately after deployment.
- Use strong random values for `ENCRYPTION_KEY` and `PUBLIC_SHARE_SECRET_KEY` in production.
- Protect the management endpoint with HTTPS or a reverse proxy.
- Restrict network access to the metadata database, managed database instances, and SSH hosts.
- Regularly back up the PostgreSQL metadata database, `/app/data`, and `/app/uploads`.
- Audit programmable adapters and custom skills because they may access sensitive operational resources.

## Technical Architecture

DBClaw uses a lightweight architecture designed for easy deployment:

- Backend: Python
- Frontend: JavaScript SPA
- Database: PostgreSQL
- Large language models: Compatible with general OpenAI and Anthropic APIs, with support for popular models including DeepSeek, Qwen, MiniMax, GLM, Kimi, GPT, and Claude
- Deployment: Run locally with Python or in a single Docker container

Core directories:

```text
backend/     FastAPI backend, routes, services, models, and skill system
frontend/    Vanilla JavaScript frontend pages, components, and static assets
docs/        Product, design, and implementation documentation
docker/      Single-container startup scripts and supervisor configuration
tests/       pytest test cases
run.py       Local startup entry point
```

## Documentation

- [Changelog](CHANGELOG.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)

## Contributing

Issues, feature suggestions, documentation improvements, and code contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

## License

NineData DBClaw is released under the [MIT License](LICENSE).
