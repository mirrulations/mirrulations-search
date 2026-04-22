#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PATH="/opt/homebrew/bin:$PATH"

EXTRA_SEED_SQL_FILE=""
FORCE_SEED=0
DEV_PORT="${DEV_PORT:-8000}"

# Optional CLI flags:
#   --sql-opensearch-integration  Use the OpenSearch-integration Postgres fixture.
for arg in "$@"; do
  case "$arg" in
    --sql-opensearch-integration)
      EXTRA_SEED_SQL_FILE="$SCRIPT_DIR/db/sample-data-opensearch-integration.sql"
      FORCE_SEED=1
      ;;
  esac
done

# Install Postgres if missing (Mac/Homebrew)
if ! command -v psql &>/dev/null && command -v brew &>/dev/null; then
    echo "Installing PostgreSQL via Homebrew..."
    brew install postgresql
    brew services start postgresql
fi

# Install OpenSearch if missing (Mac/Homebrew)
if ! command -v curl &>/dev/null; then
    echo "curl is required but not installed."
    exit 1
fi
if ! curl -sSf "http://localhost:9200" >/dev/null 2>&1 && command -v brew &>/dev/null; then
    echo "Ensuring OpenSearch is installed via Homebrew..."
    if ! brew list --formula | grep -qx "opensearch"; then
        brew install opensearch
    fi
    brew services start opensearch 2>/dev/null || true
fi

# Setup Postgres DB if not already initialized
brew services start postgresql 2>/dev/null || true
if [[ "$FORCE_SEED" == "1" ]]; then
    EXTRA_SEED_SQL_FILE="$EXTRA_SEED_SQL_FILE" ./db/setup_postgres_local.sh
else
    if ! psql -lqt postgres 2>/dev/null | grep -qw mirrulations; then
        ./db/setup_postgres_local.sh
    fi
fi

# Ensure OpenSearch service is up; start if needed.
if command -v brew &>/dev/null; then
    brew services start opensearch 2>/dev/null || true
fi

# Ensure the project virtualenv exists and has current dependencies.
if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c "import redis" >/dev/null 2>&1; then
    echo "Installing/updating Python dependencies..."
    .venv/bin/pip install -r requirements.txt
fi

# Seed OpenSearch indices/data for search numerators/denominators.
if [[ -x ".venv/bin/python" ]]; then
    PYTHONPATH="$PWD/src" .venv/bin/python db/ingest_opensearch.py
else
    PYTHONPATH="$PWD/src" python db/ingest_opensearch.py
fi

# Build the React frontend
(cd frontend && npm ci --no-audit --no-fund && npm run build)

# Load .env variables
[[ -f .env ]] && source .env
WORKER_PID_FILE="worker.pid"
WORKER_LOG_FILE="worker.log"
GUNICORN_ACCESS_LOG="gunicorn-access.log"
GUNICORN_ERROR_LOG="gunicorn-error.log"
REDIS_DATA_DIR="$PWD/.redis-data"
REDIS_PID_FILE="$REDIS_DATA_DIR/redis.pid"
REDIS_LOG_FILE="$REDIS_DATA_DIR/redis.log"
REDIS_HOST="${DEV_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${DEV_REDIS_PORT:-6380}"
REDIS_DB="${DEV_REDIS_DB:-0}"
FETCH_REPO_DIR="${FETCH_REPO_DIR:-$PWD/../mirrulations-fetch}"
CSV_REPO_DIR="${CSV_REPO_DIR:-$PWD/../mirrulations-csv}"

# Install mirrulations-fetch and mirrulations-csv into the venv.
./setup_workers.sh

# Install Redis if missing (Mac/Homebrew)
if ! command -v redis-cli &>/dev/null && command -v brew &>/dev/null; then
    echo "Installing Redis via Homebrew..."
    brew install redis
fi
if ! command -v redis-cli &>/dev/null; then
    echo "redis-cli is required but not found. Install Redis and re-run."
    exit 1
fi
mkdir -p "$REDIS_DATA_DIR"
if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    echo "Starting Redis..."
    redis-server \
      --daemonize yes \
      --bind "$REDIS_HOST" \
      --port "$REDIS_PORT" \
      --dir "$REDIS_DATA_DIR" \
      --pidfile "$REDIS_PID_FILE" \
      --logfile "$REDIS_LOG_FILE" \
      --dbfilename dump.rdb \
      --save "" \
      --appendonly no \
      --stop-writes-on-bgsave-error no
fi

# Generate JWT_SECRET if not set
if [[ -z "${JWT_SECRET:-}" ]]; then
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "JWT_SECRET=$JWT_SECRET" >> .env
    echo "Generated JWT_SECRET and saved to .env"
fi

# Restart worker if it is already running.
if [[ -f "$WORKER_PID_FILE" ]]; then
    if kill -0 "$(cat "$WORKER_PID_FILE")" 2>/dev/null; then
        echo "Stopping existing worker..."
        kill -TERM "$(cat "$WORKER_PID_FILE")" 2>/dev/null || true
    fi
    rm -f "$WORKER_PID_FILE"
fi

# Start the download worker in the background.
echo "Starting download worker..."
PYTHONPATH="$PWD/src" \
  OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  USE_POSTGRES="${USE_POSTGRES:-}" \
  DB_HOST="${DB_HOST:-}" \
  DB_PORT="${DB_PORT:-}" \
  DB_NAME="${DB_NAME:-}" \
  DB_USER="${DB_USER:-}" \
  DB_PASSWORD="${DB_PASSWORD:-}" \
  BASE_URL="${BASE_URL:-}" \
  GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}" \
  GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}" \
  JWT_SECRET="${JWT_SECRET:-}" \
  REDIS_HOST="$REDIS_HOST" \
  REDIS_PORT="$REDIS_PORT" \
  REDIS_DB="$REDIS_DB" \
  FETCH_REPO_DIR="$FETCH_REPO_DIR" \
  CSV_REPO_DIR="$CSV_REPO_DIR" \
  .venv/bin/python worker.py >"$WORKER_LOG_FILE" 2>&1 &
echo $! > "$WORKER_PID_FILE"

# Stop existing Gunicorn if running (so we can start fresh)
if [[ -f gunicorn.pid ]]; then
    kill -TERM "$(cat gunicorn.pid)" 2>/dev/null || true
    rm -f gunicorn.pid
fi

# Start the gunicorn server on a non-privileged local dev port.
export PYTHONPATH="$PWD/src"
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  PYTHONPATH="$PYTHONPATH" \
  USE_POSTGRES="${USE_POSTGRES:-}" \
  DB_HOST="${DB_HOST:-}" \
  DB_PORT="${DB_PORT:-}" \
  DB_NAME="${DB_NAME:-}" \
  DB_USER="${DB_USER:-}" \
  DB_PASSWORD="${DB_PASSWORD:-}" \
  BASE_URL="${BASE_URL:-http://localhost:${DEV_PORT}}" \
  GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}" \
  GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}" \
  JWT_SECRET="${JWT_SECRET:-}" \
  REDIS_HOST="$REDIS_HOST" \
  REDIS_PORT="$REDIS_PORT" \
  REDIS_DB="$REDIS_DB" \
  .venv/bin/gunicorn \
    --bind "0.0.0.0:${DEV_PORT}" \
    --workers 4 \
    --timeout 120 \
    --access-logfile "$GUNICORN_ACCESS_LOG" \
    --error-logfile "$GUNICORN_ERROR_LOG" \
    --capture-output \
    --pid gunicorn.pid \
    --daemon \
    mirrsearch.app:app
echo "Mirrulations search has been started on http://localhost:${DEV_PORT}"
