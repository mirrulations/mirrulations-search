#!/bin/bash
set -euo pipefail

PID_FILE="gunicorn.pid"
WORKER_PID_FILE="worker.pid"
REDIS_HOST="${DEV_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${DEV_REDIS_PORT:-6380}"

if [ ! -f "$PID_FILE" ]; then
  echo "No PID file found, have you run dev_up.sh"
  exit 1
fi

kill -TERM "$(cat "$PID_FILE")" 2>/dev/null || true
rm -f "$PID_FILE"

if [ -f "$WORKER_PID_FILE" ]; then
  kill -TERM "$(cat "$WORKER_PID_FILE")" 2>/dev/null || true
  rm -f "$WORKER_PID_FILE"
fi

if [[ "${STOP_REDIS_ON_DOWN:-0}" == "1" ]] && command -v redis-cli &>/dev/null; then
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" shutdown nosave 2>/dev/null || true
fi

echo "Mirralations Search is down"
