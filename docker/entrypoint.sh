#!/bin/bash
# Docker entrypoint: bootstrap runtime secrets, initialize DB, then start supervisord
set -euo pipefail

RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE:-/app/data/bootstrap/runtime.env}"
BOOTSTRAP_DIR="$(dirname "$RUNTIME_ENV_FILE")"
DEFAULT_ADMIN_PASSWORD="${DEFAULT_ADMIN_PASSWORD:-admin1234}"
LOG_DIR="${LOG_DIR:-/app/data/logs}"
UPLOAD_DIR="${UPLOAD_DIR:-/app/uploads}"
CHAT_ATTACHMENTS_DIR="${CHAT_ATTACHMENTS_DIR:-$UPLOAD_DIR/chat_attachments}"
DBCLAW_FIX_UPLOAD_PERMISSIONS="${DBCLAW_FIX_UPLOAD_PERMISSIONS:-true}"

generate_fernet_key() {
    python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
}

generate_hex_secret() {
    openssl rand -hex 32
}

generate_password() {
    openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 24
    echo
}

build_database_url() {
    python - "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$POSTGRES_DB" <<'PY'
import sys
from urllib.parse import quote

user, password, database = sys.argv[1:4]
print(f"postgresql+asyncpg://{quote(user)}:{quote(password)}@127.0.0.1:5432/{quote(database)}")
PY
}

mkdir -p "$BOOTSTRAP_DIR"
chmod 700 "$BOOTSTRAP_DIR"
install -d -m 775 -o dbclaw -g dbclaw "$LOG_DIR/app"
install -d -m 775 -o postgres -g postgres "$LOG_DIR/postgresql"
touch "$LOG_DIR/app/app.log" "$LOG_DIR/app/error.log" "$LOG_DIR/postgresql/postgresql.log"
chown dbclaw:dbclaw "$LOG_DIR/app/app.log" "$LOG_DIR/app/error.log"
chown postgres:postgres "$LOG_DIR/postgresql/postgresql.log"
chmod 664 "$LOG_DIR/app/app.log" "$LOG_DIR/app/error.log" "$LOG_DIR/postgresql/postgresql.log"

if [ "$DBCLAW_FIX_UPLOAD_PERMISSIONS" = "true" ]; then
    install -d -m 775 "$UPLOAD_DIR"
    chown dbclaw:dbclaw "$UPLOAD_DIR"
    chmod 775 "$UPLOAD_DIR"
    install -d -m 775 -o dbclaw -g dbclaw "$CHAT_ATTACHMENTS_DIR"
    chown dbclaw:dbclaw "$CHAT_ATTACHMENTS_DIR"
    chmod 775 "$CHAT_ATTACHMENTS_DIR"
else
    install -d -m 775 "$CHAT_ATTACHMENTS_DIR"
fi

if [ -f "$RUNTIME_ENV_FILE" ]; then
    set -a
    . "$RUNTIME_ENV_FILE"
    set +a
fi

POSTGRES_DB="${POSTGRES_DB:-dbclaw}"
POSTGRES_USER="${POSTGRES_USER:-dbclaw}"

if [ -z "${ENCRYPTION_KEY:-}" ]; then
    ENCRYPTION_KEY="$(generate_fernet_key)"
fi

if [ -z "${PUBLIC_SHARE_SECRET_KEY:-}" ]; then
    PUBLIC_SHARE_SECRET_KEY="$(generate_hex_secret)"
fi

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    POSTGRES_PASSWORD="$(generate_password)"
fi

if [ -z "${INITIAL_ADMIN_PASSWORD:-}" ]; then
    INITIAL_ADMIN_PASSWORD="$DEFAULT_ADMIN_PASSWORD"
fi

if [ -z "${DATABASE_URL:-}" ]; then
    DATABASE_URL="$(build_database_url)"
fi

export ENCRYPTION_KEY
export PUBLIC_SHARE_SECRET_KEY
export POSTGRES_DB
export POSTGRES_USER
export POSTGRES_PASSWORD
export INITIAL_ADMIN_PASSWORD
export DATABASE_URL
export LOG_DIR

umask 077
cat > "$RUNTIME_ENV_FILE" <<EOF
ENCRYPTION_KEY=$ENCRYPTION_KEY
PUBLIC_SHARE_SECRET_KEY=$PUBLIC_SHARE_SECRET_KEY
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
INITIAL_ADMIN_PASSWORD=$INITIAL_ADMIN_PASSWORD
DATABASE_URL=$DATABASE_URL
EOF
chmod 600 "$RUNTIME_ENV_FILE"

echo "Bootstrap runtime config ready: $RUNTIME_ENV_FILE"
if [ "$INITIAL_ADMIN_PASSWORD" = "$DEFAULT_ADMIN_PASSWORD" ]; then
    echo "Default admin credentials: admin / $DEFAULT_ADMIN_PASSWORD"
    echo "Please change the admin password after first login."
fi

/app/docker/init-db.sh

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
