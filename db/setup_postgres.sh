#!/bin/bash

DB_NAME="mirrulations"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting PostgreSQL..."
if command -v brew &>/dev/null; then
    brew services start postgresql
    run_pg() { "$@"; }
elif command -v systemctl &>/dev/null; then
    for svc in postgresql postgresql-14 postgresql-15 postgresql-16 postgresql-17; do
        sudo systemctl start "$svc" 2>/dev/null && break
    done
    run_pg() { sudo -u postgres "$@"; }
    PGDATA=$(sudo -u postgres psql -t -A -c "SHOW data_directory" 2>/dev/null | tr -d '[:space:]')
    PGHBA="${PGDATA}/pg_hba.conf"
    if [[ -n "$PGHBA" && -f "$PGHBA" ]]; then
        if grep -q "127.0.0.1/32.*ident" "$PGHBA" 2>/dev/null; then
            sudo sed -i.bak '/127\.0\.0\.1\/32/s/ident$/md5/' "$PGHBA"
            grep -q "::1/128.*ident" "$PGHBA" 2>/dev/null && sudo sed -i.bak '/::1\/128/s/ident$/md5/' "$PGHBA" || true
            run_pg psql -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null || true
            for svc in postgresql postgresql-14 postgresql-15 postgresql-16 postgresql-17; do
                sudo systemctl reload "$svc" 2>/dev/null && break
            done
        fi
    fi
else
    run_pg() { "$@"; }
fi

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
