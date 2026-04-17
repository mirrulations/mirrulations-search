#!/usr/bin/env bash
set -euo pipefail
# SHOULD BE DONE INSIDE OF THE test_mirrulations-search ec2 INSTANCE
# Safe helper for test EC2 deployment flow.
# - Linux-safe DB bootstrap (avoids Homebrew-only script)
# - Ensures postgres localhost password auth
# - Runs production deploy and quick verification

PROJECT_DIR="${1:-$HOME/SEARCHTEST_mirrulations}"
DOMAIN="${2:-test.mirrulations.org}"

echo "Using project: ${PROJECT_DIR}"
echo "Using domain:  ${DOMAIN}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project directory not found: ${PROJECT_DIR}"
  exit 1
fi

cd "${PROJECT_DIR}"

if [[ ! -f "prod_deploy.sh" ]]; then
  echo "prod_deploy.sh not found in ${PROJECT_DIR}"
  exit 1
fi

echo "Writing mirrsearch.service for test deployment..."
cat > mirrsearch.service <<SVCEOF
[Unit]
Description=Mirrulations-Search
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${PROJECT_DIR}/.env
Environment="PATH=${PROJECT_DIR}/.venv/bin"
Environment="PYTHONPATH=${PROJECT_DIR}/src"
Environment="USE_AWS_SECRETS=true"
Environment="USE_TEST_OAUTH=true"
Environment="OPENSEARCH_MATCH_DOCKET_BUCKET_SIZE=50000"
Environment="OPENSEARCH_COMMENT_ID_TERMS_SIZE=50000"
ExecStart=${PROJECT_DIR}/.venv/bin/gunicorn \
    --certfile /etc/letsencrypt/live/${DOMAIN}/fullchain.pem \
    --keyfile /etc/letsencrypt/live/${DOMAIN}/privkey.pem \
    --bind 0.0.0.0:443 \
    --timeout 120 \
    --worker-class gthread --workers 2 --threads 4 mirrsearch.app:app
Restart=always

[Install]
WantedBy=multi-user.target
SVCEOF

echo "Checking domain references in prod_deploy.sh..."
if grep -q "dev.mirrulations.org" prod_deploy.sh 2>/dev/null; then
  echo "Replacing dev.mirrulations.org -> ${DOMAIN}"
  sed -i "s/dev\.mirrulations\.org/${DOMAIN}/g" prod_deploy.sh || true
fi

echo "Ensuring Postgres is running..."
for svc in postgresql postgresql-14 postgresql-15 postgresql-16 postgresql-17; do
  sudo systemctl start "$svc" 2>/dev/null && break
done

echo "Preparing DB SQL files in /tmp..."
cp db/schema-postgres.sql /tmp/schema-postgres.sql
cp db/sample-data.sql /tmp/sample-data.sql
chmod 644 /tmp/schema-postgres.sql /tmp/sample-data.sql

echo "Dropping existing database (clean slate for test)..."
sudo -u postgres dropdb mirrulations 2>/dev/null || true

echo "Creating and loading database..."
sudo -u postgres createdb mirrulations
sudo -u postgres psql -d mirrulations -f /tmp/schema-postgres.sql
sudo -u postgres psql -d mirrulations -f /tmp/sample-data.sql

echo "Configuring postgres localhost auth..."
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" >/dev/null
PGDATA=$(sudo -u postgres psql -t -A -c "SHOW data_directory" | tr -d '[:space:]')
sudo sed -i.bak -E 's#^(host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1/32[[:space:]]+).*$#\1md5#' "$PGDATA/pg_hba.conf"
sudo sed -i.bak -E 's#^(host[[:space:]]+all[[:space:]]+all[[:space:]]+::1/128[[:space:]]+).*$#\1md5#' "$PGDATA/pg_hba.conf"
sudo systemctl restart postgresql || true

echo "Validating DB visibility..."
PGPASSWORD=postgres psql -h localhost -U postgres -lqt postgres | grep -w mirrulations >/dev/null


echo "Patching db.py to use correct RDS secret..."
sed -i '/response = client.get_secret_value/s|SecretId="[^"]*"|SecretId="mirrulationsdb/postgres/master"|' src/mirrsearch/db.py
sed -i '/_get_secrets_from_aws/,/return json/s|region_name="[^"]*"|region_name="us-east-1"|' src/mirrsearch/db.py

echo "Running deployment..."
chmod +x prod_deploy.sh
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_SECRET_NAME="${AWS_SECRET_NAME:-mirrulationsdb/postgres/master}"
./prod_deploy.sh

echo "Verifying service..."
sudo systemctl status mirrsearch --no-pager || true
curl -Ik "https://${DOMAIN}" || true

echo "Done."
