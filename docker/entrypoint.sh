#!/bin/bash
# Docker entrypoint: initialize DB on first run, then start supervisord
set -e

# Initialize PostgreSQL if needed
/app/docker/init-db.sh

# Start all services via supervisord
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
