#!/bin/bash
# Create a Postgres database with schema and sample data.
# Usage: [DB_NAME=mirrulations] ./db/create_sample_db.sh
# For testing: DB_NAME=mirrulations_test ./db/create_sample_db.sh

set -e

DB_NAME="${DB_NAME:-mirrulations}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/schema-postgres.sql"
SAMPLE_FILE="$SCRIPT_DIR/sample-data.sql"

# Ensure Postgres is running (Homebrew macOS)
PG_VERSION="${PG_VERSION:-$(brew list 2>/dev/null | grep -oE 'postgresql@[0-9]+' | sort -t@ -k2 -n | tail -1 | cut -d@ -f2)}"
if [ -n "$PG_VERSION" ]; then
    export PATH="/opt/homebrew/opt/postgresql@${PG_VERSION}/bin:$PATH"
fi
if ! pg_isready -q 2>/dev/null; then
    echo "Starting PostgreSQL..."
    brew services start postgresql@${PG_VERSION:-14} 2>/dev/null || brew services start postgresql 2>/dev/null || true
    sleep 2
fi
if ! pg_isready -q 2>/dev/null; then
    echo "Error: PostgreSQL is not running. Start it with: brew services start postgresql"
    exit 1
fi

# Check if database already exists → prompt before overwrite (unless OVERWRITE_YES=1)
if psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
    echo "Warning: Database '$DB_NAME' already exists."
    if [ "$OVERWRITE_YES" != "1" ]; then
        read -p "Overwrite it? (y/n): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "Aborted. Database was not modified."
            exit 0
        fi
    fi
fi

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Error: Schema file not found at $SCHEMA_FILE"
    exit 1
fi
if [ ! -f "$SAMPLE_FILE" ]; then
    echo "Error: Sample data file not found at $SAMPLE_FILE"
    exit 1
fi

echo "Dropping database if it exists..."
dropdb --if-exists "$DB_NAME"

echo "Creating database..."
createdb "$DB_NAME"

echo "Loading schema..."
psql -v ON_ERROR_STOP=1 -d "$DB_NAME" -f "$SCHEMA_FILE"

echo "Loading sample data..."
psql -v ON_ERROR_STOP=1 -d "$DB_NAME" -f "$SAMPLE_FILE"

# Verify: tables that have sample data should have rows.
TABLES=("dockets" "documents" "links" "cfrparts" "federal_register_documents")
for table_name in "${TABLES[@]}"; do
    row_count=$(psql -d "$DB_NAME" -tAc "SELECT count(*) FROM $table_name;")
    if [ "${row_count:-0}" -lt 1 ]; then
        echo "Error: Sample data verification failed for table '$table_name' (count=$row_count)."
        exit 1
    fi
done

echo "Successfully created database '$DB_NAME' with schema and sample data."
echo "Connect with: psql $DB_NAME"
