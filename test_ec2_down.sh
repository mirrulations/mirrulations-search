#!/usr/bin/env bash
set -euo pipefail
# Tears down the test EC2 deployment: stops the service, drops the database,
# and stops OpenSearch / Postgres if desired.

PROJECT_DIR="${1:-$HOME/SEARCHTEST_mirrulations}"

echo "Using project: ${PROJECT_DIR}"

echo "Stopping mirrsearch service..."
sudo systemctl stop mirrsearch 2>/dev/null || true
sudo systemctl disable mirrsearch 2>/dev/null || true

echo "Dropping test database..."
sudo -u postgres dropdb mirrulations 2>/dev/null || true

echo "Stopping OpenSearch..."
sudo systemctl stop opensearch 2>/dev/null || true

echo "Stopping Postgres..."
for svc in postgresql postgresql-14 postgresql-15 postgresql-16 postgresql-17; do
  sudo systemctl stop "$svc" 2>/dev/null && break
done

echo "Cleaning up temp SQL files..."
rm -f /tmp/schema-postgres.sql /tmp/sample-data.sql

echo "Test environment is down."
