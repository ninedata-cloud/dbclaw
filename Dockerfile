# DBClaw - 单容器部署（内置 PostgreSQL + FastAPI + 静态前端）
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=9939 \
    DEBUG=false

WORKDIR /app

# 安装系统依赖、数据库驱动编译依赖、PostgreSQL 18 和 supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    gnupg \
    lsb-release \
    supervisor \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libkrb5-dev \
    unixodbc \
    unixodbc-dev \
    freetds-bin \
    freetds-dev \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-18 \
    postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

# 先安装 Python 依赖，提升缓存命中率
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 复制项目运行所需文件
COPY backend ./backend
COPY frontend ./frontend
COPY docker ./docker
COPY run.py ./
COPY .env.example ./

# 创建运行目录并设置权限
RUN mkdir -p \
    /app/data/bootstrap \
    /app/uploads/chat_attachments \
    /var/log/supervisor \
    /etc/supervisor/conf.d \
    && chmod +x /app/docker/entrypoint.sh /app/docker/init-db.sh \
    && useradd -m -u 1000 dbclaw \
    && chown -R dbclaw:dbclaw /app \
    && chown -R postgres:postgres /var/lib/postgresql

# supervisor 配置
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 数据卷：PostgreSQL 数据、应用运行数据、上传附件
VOLUME ["/var/lib/postgresql/data", "/app/data", "/app/uploads"]

EXPOSE 9939

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:9939/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
