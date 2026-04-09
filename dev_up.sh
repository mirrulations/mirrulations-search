#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EXTRA_SEED_SQL_FILE=""
FORCE_SEED=0

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
    EXTRA_SEED_SQL_FILE="$EXTRA_SEED_SQL_FILE" ./db/setup_postgres.sh
else
    if ! psql -lqt postgres 2>/dev/null | grep -qw mirrulations; then
        ./db/setup_postgres.sh
    fi
fi

# Ensure OpenSearch service is up; start if needed.
if command -v brew &>/dev/null; then
    brew services start opensearch 2>/dev/null || true
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

# Generate JWT_SECRET if not set
if [[ -z "${JWT_SECRET:-}" ]]; then
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "JWT_SECRET=$JWT_SECRET" >> .env
    echo "Generated JWT_SECRET and saved to .env"
fi

# Stop existing Gunicorn if running (so we can start fresh)
if [[ -f gunicorn.pid ]]; then
    sudo kill -TERM "$(cat gunicorn.pid)" 2>/dev/null || true
    rm -f gunicorn.pid
fi

# Start the gunicorn server on port 80 using the configuration in conf/gunicorn.py
export PYTHONPATH="$PWD/src"
sudo OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  PYTHONPATH="$PYTHONPATH" \
  USE_POSTGRES="$USE_POSTGRES" \
  DB_HOST="$DB_HOST" \
  DB_PORT="$DB_PORT" \
  DB_NAME="$DB_NAME" \
  DB_USER="$DB_USER" \
  DB_PASSWORD="$DB_PASSWORD" \
  BASE_URL="$BASE_URL" \
  GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
  GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET" \
  JWT_SECRET="$JWT_SECRET" \
  .venv/bin/gunicorn -c conf/gunicorn.py mirrsearch.app:app
echo "Mirrulations search has been started"
