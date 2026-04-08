#!/bin/bash

set -e

# CONFIG (edit these if needed)
APP_DIR=${APP_DIR:-/home/ec2-user/mirrulations-search}
APP_USER=${APP_USER:-ec2-user}
VENV_PATH=${VENV_PATH:-$APP_DIR/.venv}
ENV_FILE=${ENV_FILE:-$APP_DIR/.env}

# INSTALL REDIS (Amazon Linux)
echo "=== Installing Redis ==="

if command -v dnf >/dev/null; then
  dnf install -y redis
elif command -v yum >/dev/null; then
  amazon-linux-extras enable redis6 || true
  yum install -y redis
else
  echo "Unsupported OS: expected Amazon Linux"
  exit 1
fi

# CONFIGURE REDIS
echo "=== Configuring Redis ==="

REDIS_CONF="/etc/redis/redis.conf"

# Fallback path (some AMIs use this)
if [ ! -f "$REDIS_CONF" ]; then
  REDIS_CONF="/etc/redis.conf"
fi

# Bind to localhost only
sed -i 's/^#\? *bind .*/bind 127.0.0.1/' "$REDIS_CONF" || true

# Enable systemd supervision if present
sed -i 's/^#\? *supervised .*/supervised systemd/' "$REDIS_CONF" || true

# START REDIS
echo "=== Starting Redis ==="

systemctl enable redis
systemctl restart redis

# VERIFY REDIS
echo "=== Verifying Redis ==="

if redis-cli ping | grep -q PONG; then
  echo "Redis is running"
else
  echo "Redis failed to start"
  exit 1
fi

# VALIDATE APP SETUP
echo "=== Validating app setup ==="

if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: APP_DIR does not exist: $APP_DIR"
  exit 1
fi

if [ ! -f "$VENV_PATH/bin/rq" ]; then
  echo "ERROR: rq not found in virtualenv: $VENV_PATH"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "WARNING: .env file not found at $ENV_FILE"
fi

# CREATE RQ WORKER SERVICE
echo "=== Creating RQ worker service ==="

cat > /etc/systemd/system/rq-worker.service <<EOF
[Unit]
Description=RQ Worker
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_PATH/bin/rq worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# START WORKER
echo "=== Starting RQ worker ==="

systemctl daemon-reload
systemctl enable rq-worker
systemctl restart rq-worker

# VERIFY WORKER
echo "=== Verifying worker ==="

systemctl status rq-worker --no-pager || true

# DONE
echo ""
echo "=== Setup Complete ==="
echo "Redis running on localhost:6379"
echo "RQ worker running"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status redis"
echo "  sudo systemctl status rq-worker"
echo "  sudo systemctl restart rq-worker"
echo "  sudo journalctl -u rq-worker -f"