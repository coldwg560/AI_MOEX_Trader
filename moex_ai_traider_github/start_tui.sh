#!/bin/bash
echo "Starting MOEX AI Trader (TUI)..."

cd "$(dirname "$0")"

export GRPC_DEFAULT_SSL_ROOTS_FILE_PATH="$(./bin/python -c 'import certifi; print(certifi.where())')"

./bin/python tui.py
