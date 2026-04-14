#!/bin/bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <log-name> <command> [args...]" >&2
    exit 1
fi

LOG_NAME="$1"
shift

LOG_DIR="${LOG_DIR:-/app/data/logs}"
LOG_FILE="$LOG_DIR/${LOG_NAME}.log"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

"$@" 2>&1 | tee -a "$LOG_FILE"
exit "${PIPESTATUS[0]}"
