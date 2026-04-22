#!/bin/bash

DB_NAME="mirrulations"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting PostgreSQL..."
PG_VERSION="${PG_VERSION:-$(brew list | grep -oE 'postgresql@[0-9]+' | sort -t@ -k2 -n | tail -1 | cut -d@ -f2)}"
if [ -z "$PG_VERSION" ]; then
    echo "Error: No PostgreSQL installation found via Homebrew."
    exit 1
fi
export PATH="/opt/homebrew/opt/postgresql@${PG_VERSION}/bin:$PATH"
pg_isready -q 2>/dev/null || brew services start postgresql@${PG_VERSION}

#TODO: Change so database doesn't get dropped when prod ready.
echo "Dropping database if it exists..."
dropdb --if-exists $DB_NAME

echo "Creating database..."
createdb $DB_NAME

echo "Creating schema..."
psql -d $DB_NAME -f "$SCRIPT_DIR/schema-postgres.sql"

echo "Inserting seed data..."
psql -d $DB_NAME -f "$SCRIPT_DIR/sample-data.sql"

if [ -n "${EXTRA_SEED_SQL_FILE:-}" ]; then
  if [ -f "$EXTRA_SEED_SQL_FILE" ]; then
    echo "Applying extra seed data: $EXTRA_SEED_SQL_FILE"
    psql -d $DB_NAME -f "$EXTRA_SEED_SQL_FILE"
  else
    echo "Warning: EXTRA_SEED_SQL_FILE set but file not found: $EXTRA_SEED_SQL_FILE"
  fi
fi

echo ""
echo "Database '$DB_NAME' is fully initialized."
echo "Connect with:"
echo "psql $DB_NAME"