#!/bin/bash

set -e

# CONFIG
APP_DIR=${APP_DIR:-$HOME/mirrulations-search}
APP_USER=${APP_USER:-$(whoami)}
VENV_PATH=${VENV_PATH:-$APP_DIR/.venv}
ENV_FILE=${ENV_FILE:-$APP_DIR/.env}

OS="$(uname)"

# INSTALL REDIS (MAC vs AMAZON LINUX)
echo "=== Installing Redis ==="

if [[ "$OS" == "Darwin" ]]; then
  # macOS
  if ! command -v brew >/dev/null; then
    echo "Homebrew not found. Install it first: https://brew.sh/"
    exit 1
  fi

  brew install redis || true
  brew services start redis

elif command -v dnf >/dev/null || command -v yum >/dev/null; then
  # Amazon Linux
  if command -v dnf >/dev/null; then
    dnf install -y redis
  else
    amazon-linux-extras enable redis6 || true
    yum install -y redis
  fi

  echo "=== Configuring Redis ==="
  REDIS_CONF="/etc/redis/redis.conf"
  if [ ! -f "$REDIS_CONF" ]; then
    REDIS_CONF="/etc/redis.conf"
  fi

  sed -i 's/^#\? *bind .*/bind 127.0.0.1/' "$REDIS_CONF" || true
  sed -i 's/^#\? *supervised .*/supervised systemd/' "$REDIS_CONF" || true

  systemctl enable redis
  systemctl restart redis

else
  echo "Unsupported OS"
  exit 1
fi

# VERIFY REDIS
echo "=== Verifying Redis ==="

if redis-cli ping | grep -q PONG; then
  echo "Redis is running"
else
  echo "Redis failed to start"
  exit 1
fi

# SETUP RQ WORKER (ONLY ON LINUX)
if [[ "$OS" != "Darwin" ]]; then
  echo "=== Setting up RQ worker (systemd) ==="

  if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: APP_DIR does not exist: $APP_DIR"
    exit 1
  fi

  if [ ! -f "$VENV_PATH/bin/rq" ]; then
    echo "ERROR: rq not found in virtualenv: $VENV_PATH"
    exit 1
  fi

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

  systemctl daemon-reload
  systemctl enable rq-worker
  systemctl restart rq-worker

  echo "=== RQ worker started ==="
fi

# DONE
echo ""
echo "=== Setup Complete ==="
echo "Redis running on localhost:6379"

if [[ "$OS" == "Darwin" ]]; then
  echo "(macOS) Redis managed by brew services"
else
  echo "RQ worker running via systemd"
fi
