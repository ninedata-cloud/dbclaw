# DbGuard - AI-powered Database Operations Platform
# Single container with PostgreSQL 18 + Application
FROM python:3.11-slim

# Install system dependencies + PostgreSQL 18 from PGDG
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libkrb5-dev \
    curl \
    freetds-dev \
    freetds-bin \
    unixodbc-dev \
    supervisor \
    gnupg \
    lsb-release \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download sentence-transformers embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY run.py .

# Create data directories (can be overridden by volumes)
RUN mkdir -p data/chroma uploads/chat_attachments data/knowledge_bases

# Copy docker helper scripts
COPY docker/ ./docker/
RUN chmod +x /app/docker/entrypoint.sh /app/docker/init-db.sh

# Set up supervisord config
RUN mkdir -p /etc/supervisor/conf.d /var/log/supervisor
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create non-root app user and fix permissions
RUN useradd -m -u 1000 dbguard \
    && chown -R dbguard:dbguard /app \
    && chown -R postgres:postgres /var/lib/postgresql

# PostgreSQL default data directory
VOLUME ["/var/lib/postgresql/data", "/app/data", "/app/uploads"]

# Expose application port
EXPOSE 9939

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:9939/health || exit 1

# Default environment pointing to local PG
ENV DATABASE_URL=postgresql+asyncpg://dbguard:DbGuard2026@localhost:5432/dbguard?ssl=disable

ENTRYPOINT ["/app/docker/entrypoint.sh"]
