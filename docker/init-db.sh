#!/bin/bash
set -euo pipefail

PG_BIN=/usr/lib/postgresql/18/bin
PG_DATA=/var/lib/postgresql/data
POSTGRES_DB=${POSTGRES_DB:-dbclaw}
POSTGRES_USER=${POSTGRES_USER:-dbclaw}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-}

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "POSTGRES_PASSWORD is empty after bootstrap; refusing to initialize PostgreSQL." >&2
    exit 1
fi

# Initialize PostgreSQL data directory if not already done
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "Initializing PostgreSQL data directory..."
    install -d -m 700 -o postgres -g postgres "$PG_DATA"
    su -c "$PG_BIN/initdb -D $PG_DATA --encoding=UTF8 --locale=C --auth-local=peer --auth-host=scram-sha-256" postgres
fi

# Ensure log directory is writable by postgres
install -d -m 775 -o postgres -g postgres /var/log/supervisor

# Start PostgreSQL temporarily to create user/database
su -c "$PG_BIN/pg_ctl -D $PG_DATA -l /var/log/supervisor/pg_init.log start -w" postgres

# Create or update database user, then ensure database exists
su -c "psql -v ON_ERROR_STOP=1 postgres -c \"DO \\\$\\\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${POSTGRES_USER}') THEN EXECUTE format('CREATE USER %I WITH LOGIN PASSWORD %L', '${POSTGRES_USER}', '${POSTGRES_PASSWORD}'); ELSE EXECUTE format('ALTER ROLE %I WITH PASSWORD %L', '${POSTGRES_USER}', '${POSTGRES_PASSWORD}'); END IF; END \\\$\\\$;\"" postgres

su -c "psql -v ON_ERROR_STOP=1 postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'\" | grep -q 1 || createdb -O '${POSTGRES_USER}' '${POSTGRES_DB}'" postgres

# Stop temporary PostgreSQL instance (supervisord will restart it)
su -c "$PG_BIN/pg_ctl -D $PG_DATA stop -m fast" postgres

echo "PostgreSQL initialization complete."
