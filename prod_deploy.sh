set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRRSEARCH_SERVICE="mirrsearch.service"
MIRRSEARCH_SERVICE_PATH="/etc/systemd/system/${MIRRSEARCH_SERVICE}"

DOMAIN="dev.mirrulations.org"

cd "${PROJECT_ROOT}"

# Inject AWS secrets config into db.py if placeholders still exist
if grep -q "YOUR_REGION" src/mirrsearch/db.py; then
    sed -i "s/YOUR_REGION/${AWS_REGION}/" src/mirrsearch/db.py
fi
if grep -q "YOUR_SECRET_NAME" src/mirrsearch/db.py; then
    sed -i "s|YOUR_SECRET_NAME|${AWS_SECRET_NAME}|" src/mirrsearch/db.py
fi

# Create .env if missing (systemd loads it; edit for RDS or custom DB credentials)
if [[ ! -f .env ]]; then
    cat > .env <<'ENVEOF'
USE_POSTGRES=1
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mirrulations
DB_USER=postgres
DB_PASSWORD=postgres
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USE_SSL=true
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD='M1rrulations!Search'
ENVEOF
    echo "Created .env with defaults (edit for RDS or custom credentials)"
fi

# Older servers: .env may predate OpenSearch TLS lines (template only runs when file is missing).
if [[ -f .env ]] && ! grep -q '^OPENSEARCH_USER=' .env; then
    cat >> .env <<'ENVEOF'

# OpenSearch (HTTPS + basic auth; must match install_demo_configuration password)
OPENSEARCH_USE_SSL=true
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD='M1rrulations!Search'
ENVEOF
    echo "Appended OpenSearch TLS/auth to .env — set OPENSEARCH_PASSWORD if yours differs."
fi

# Load .env for DB_HOST check
[[ -f .env ]] && source .env
DB_HOST="${DB_HOST:-localhost}"

# Add swap if not already present (needed for OpenSearch on small instances)
if ! swapon --show | grep -q /swapfile; then
    sudo dd if=/dev/zero of=/swapfile bs=128M count=4
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
fi

# Install OpenSearch
if [[ ! -f /usr/share/opensearch/bin/opensearch ]]; then
    sudo curl -SL https://artifacts.opensearch.org/releases/bundle/opensearch/3.x/opensearch-3.x.repo \
        -o /etc/yum.repos.d/opensearch-3.x.repo
    export OPENSEARCH_INITIAL_ADMIN_PASSWORD='M1rrulations!Search'
    sudo -E yum install -y opensearch

    # Run demo config manually with password (install scriptlet fails without it)
    sudo OPENSEARCH_INITIAL_ADMIN_PASSWORD='M1rrulations!Search' \
        /usr/share/opensearch/plugins/opensearch-security/tools/install_demo_configuration.sh -y -i -s

    # Lower heap for small EC2 instances
    sudo sed -i 's/-Xms1g/-Xms256m/' /etc/opensearch/jvm.options
    sudo sed -i 's/-Xmx1g/-Xmx256m/' /etc/opensearch/jvm.options

    sudo systemctl enable opensearch
    sudo systemctl start opensearch
fi

# Install Postgres (AL2: amazon-linux-extras + yum; AL2023: dnf)
if ! command -v psql &>/dev/null || [[ "$DB_HOST" == "localhost" || "$DB_HOST" == "127.0.0.1" ]]; then
    if command -v amazon-linux-extras &>/dev/null; then
        sudo amazon-linux-extras enable postgresql14
        sudo yum install -y postgresql-server postgresql
    else
        sudo dnf install -y postgresql15 postgresql15-server
    fi
fi

# Local Postgres: ensure running, allow app (root) to connect, setup DB if needed
if [[ "$DB_HOST" == "localhost" || "$DB_HOST" == "127.0.0.1" ]]; then
    sudo postgresql-setup --initdb 2>/dev/null || sudo postgresql-setup initdb 2>/dev/null || true
    for svc in postgresql postgresql-14 postgresql-15 postgresql-16 postgresql-17; do
        sudo systemctl start "$svc" 2>/dev/null && break
    done
    # Fix ident auth: app runs as root, ident fails. Switch localhost to md5 and set password.
    PGDATA=$(sudo -u postgres psql -t -A -c "SHOW data_directory" 2>/dev/null | tr -d '[:space:]')
    PGHBA="${PGDATA}/pg_hba.conf"
    if [[ -n "$PGDATA" && -f "$PGHBA" ]] && grep -q "127.0.0.1/32.*ident" "$PGHBA" 2>/dev/null; then
        sudo sed -i.bak '/127\.0\.0\.1\/32/s/ident$/md5/' "$PGHBA"
        grep -q "::1/128.*ident" "$PGHBA" 2>/dev/null && sudo sed -i.bak '/::1\/128/s/ident$/md5/' "$PGHBA" || true
        sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null || true
        for svc in postgresql postgresql-14 postgresql-15 postgresql-16 postgresql-17; do
            sudo systemctl reload "$svc" 2>/dev/null && break
        done
    fi
    # Ensure .env has password when using local Postgres (may exist from before with empty DB_PASSWORD)
    if [[ -f .env ]] && grep -q '^DB_PASSWORD=$' .env 2>/dev/null; then
        sed -i.bak 's/^DB_PASSWORD=$/DB_PASSWORD=postgres/' .env
    fi
    if ! PGPASSWORD=postgres psql -h localhost -U postgres -lqt postgres 2>/dev/null | grep -qw mirrulations; then
        ./db/setup_postgres.sh
    fi
fi

if ! command -v node &>/dev/null; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo yum install -y nodejs
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    ./.venv/bin/pip install -e .
    ./.venv/bin/pip install -r requirements.txt
fi

(cd frontend && npm ci --no-audit --no-fund && npm run build)

sudo ln -sf "${PROJECT_ROOT}/.venv/bin/certbot" /usr/bin/certbot

sudo systemctl stop mirrsearch 2>/dev/null || true

sudo .venv/bin/certbot certonly --standalone -d "${DOMAIN}"
sudo cp "${PROJECT_ROOT}/${MIRRSEARCH_SERVICE}" "${MIRRSEARCH_SERVICE_PATH}"
sudo systemctl daemon-reload
./prod_up.sh