#! /bin/bash
sudo systemctl daemon-reload
sudo systemctl enable mirrsearch
sudo systemctl restart mirrsearch
sudo systemctl enable mirrulations-worker
sudo systemctl restart mirrulations-worker

sudo systemctl status mirrulations-worker --no-pager
sudo systemctl status mirrsearch --no-pager