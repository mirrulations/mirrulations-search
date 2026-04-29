set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRRSEARCH_SERVICE="mirrsearch.service"
MIRRSEARCH_SERVICE_PATH="/etc/systemd/system/${MIRRSEARCH_SERVICE}"
WORKER_SERVICE="mirrulations-worker.service"
WORKER_SERVICE_PATH="/etc/systemd/system/${WORKER_SERVICE}"
DOMAIN="dev.mirrulations.org"

cd "${PROJECT_ROOT}"

# Inject AWS secrets config into db.py if placeholders still exist
if grep -q "YOUR_REGION" src/mirrsearch/db.py; then
    sed -i "s/YOUR_REGION/${AWS_REGION}/" src/mirrsearch/db.py
fi
if grep -q "YOUR_SECRET_NAME" src/mirrsearch/db.py; then
    sed -i "s|YOUR_SECRET_NAME|${AWS_SECRET_NAME}|" src/mirrsearch/db.py
fi

# Install Postgres client tools (needed for psql commands even with RDS)
if ! command -v psql &>/dev/null; then
    if command -v amazon-linux-extras &>/dev/null; then
        sudo amazon-linux-extras enable postgresql14
        sudo yum install -y postgresql
    else
        sudo dnf install -y postgresql15
    fi
fi

if ! command -v node &>/dev/null; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo yum install -y nodejs
fi

# Install Redis if not present                                                  
if ! command -v redis-cli &>/dev/null; then       
    sudo dnf install redis6 -y
    sudo systemctl enable redis6
fi
sudo systemctl start redis6

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
./.venv/bin/pip install -e .
./.venv/bin/pip install -r requirements.txt

(cd frontend && npm install && npm run build)

sudo systemctl stop mirrsearch 2>/dev/null || true
sudo cp "${PROJECT_ROOT}/${MIRRSEARCH_SERVICE}" "${MIRRSEARCH_SERVICE_PATH}"
sudo systemctl stop mirrulations-worker 2>/dev/null || true
sudo cp "${PROJECT_ROOT}/${WORKER_SERVICE}" "${WORKER_SERVICE_PATH}"
sudo systemctl daemon-reload
./prod_up.sh