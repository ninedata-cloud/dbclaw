#!/bin/bash
set -e

PG_BIN=/usr/lib/postgresql/18/bin
PG_DATA=/var/lib/postgresql/data

# Initialize PostgreSQL data directory if not already done
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "Initializing PostgreSQL data directory..."
    install -d -m 700 -o postgres -g postgres "$PG_DATA"
    su -c "$PG_BIN/initdb -D $PG_DATA --encoding=UTF8 --locale=C" postgres
fi

# Ensure log directory is writable by postgres
mkdir -p /var/log/supervisor && chmod 777 /var/log/supervisor

# Start PostgreSQL temporarily to create user/database
su -c "$PG_BIN/pg_ctl -D $PG_DATA -l /var/log/supervisor/pg_init.log start -w" postgres

# Create database user and database (idempotent)
su -c "psql -v ON_ERROR_STOP=0 -c \"CREATE USER dbguard WITH PASSWORD 'DbGuard2026';\" 2>/dev/null || true" postgres
su -c "psql -v ON_ERROR_STOP=0 -c \"CREATE DATABASE dbguard OWNER dbguard;\" 2>/dev/null || true" postgres

# Disable SSL in pg_hba.conf (local connections don't need SSL)
echo "host all all 127.0.0.1/32 trust" >> "$PG_DATA/pg_hba.conf"
echo "host all all ::1/128 trust" >> "$PG_DATA/pg_hba.conf"

# Stop temporary PostgreSQL instance (supervisord will restart it)
su -c "$PG_BIN/pg_ctl -D $PG_DATA stop -m fast" postgres

echo "PostgreSQL initialization complete."
