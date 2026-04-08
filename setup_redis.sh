#!/bin/bash

set -e  # exit immediately if any command fails

echo "=== Installing Redis ==="
apt-get update -y
apt-get install -y redis-server

echo "=== Configuring Redis ==="
# Bind to localhost only — Redis should never be exposed to the public internet
sed -i 's/^bind .*/bind 127.0.0.1/' /etc/redis/redis.conf

# Set Redis to restart automatically if it crashes
sed -i 's/^# supervised no/supervised systemd/' /etc/redis/redis.conf

echo "=== Starting Redis ==="
systemctl enable redis-server   # start on boot
systemctl restart redis-server

echo "=== Verifying Redis is running ==="
redis-cli ping  # should print PONG

echo "=== Creating RQ Worker systemd service ==="
# This keeps the RQ worker alive as a background process
# Update the WorkingDirectory and ExecStart paths to match your project

cat > /etc/systemd/system/rq-worker.service << 'EOF'
[Unit]
Description=RQ Worker for Mirrulations Download Tasks
After=network.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/mirrulations-search
EnvironmentFile=/home/ubuntu/mirrulations-search/.env
ExecStart=/home/ubuntu/mirrulations-search/.venv/bin/rq worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== Starting RQ Worker service ==="
systemctl daemon-reload
systemctl enable rq-worker
systemctl start rq-worker

echo "=== Verifying RQ Worker is running ==="
systemctl status rq-worker --no-pager

echo ""
echo "=== Setup Complete ==="
echo "Redis is running on localhost:6379"
echo "RQ worker is running and will restart automatically on reboot"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status redis-server   # check Redis"
echo "  sudo systemctl status rq-worker      # check RQ worker"
echo "  sudo systemctl restart rq-worker     # restart worker after code changes"
echo "  sudo journalctl -u rq-worker -f      # tail worker logs"