#!/bin/bash
set -e

PG_BIN=/usr/lib/postgresql/18/bin
PG_DATA=/var/lib/postgresql/data
POSTGRES_DB=${POSTGRES_DB:-dbguard}
POSTGRES_USER=${POSTGRES_USER:-dbguard}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-DbGuard2026}

# Initialize PostgreSQL data directory if not already done
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "Initializing PostgreSQL data directory..."
    install -d -m 700 -o postgres -g postgres "$PG_DATA"
    su -c "$PG_BIN/initdb -D $PG_DATA --encoding=UTF8 --locale=C" postgres
fi

# Ensure log directory is writable by postgres
mkdir -p /var/log/supervisor && chmod 777 /var/log/supervisor

# Ensure local connections are allowed
grep -q "127.0.0.1/32 trust" "$PG_DATA/pg_hba.conf" || echo "host all all 127.0.0.1/32 trust" >> "$PG_DATA/pg_hba.conf"
grep -q "::1/128 trust" "$PG_DATA/pg_hba.conf" || echo "host all all ::1/128 trust" >> "$PG_DATA/pg_hba.conf"

# Start PostgreSQL temporarily to create user/database
su -c "$PG_BIN/pg_ctl -D $PG_DATA -l /var/log/supervisor/pg_init.log start -w" postgres

# Create database user and database (idempotent)
su -c "psql -v ON_ERROR_STOP=1 postgres -c \"DO \\\$\\\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${POSTGRES_USER}') THEN EXECUTE format('CREATE USER %I WITH PASSWORD %L', '${POSTGRES_USER}', '${POSTGRES_PASSWORD}'); END IF; END \\\$\\\$;\"" postgres

su -c "psql -v ON_ERROR_STOP=1 postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'\" | grep -q 1 || createdb -O '${POSTGRES_USER}' '${POSTGRES_DB}'" postgres

# Stop temporary PostgreSQL instance (supervisord will restart it)
su -c "$PG_BIN/pg_ctl -D $PG_DATA stop -m fast" postgres

echo "PostgreSQL initialization complete."
