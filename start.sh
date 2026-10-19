#!/usr/bin/env bash
set -e
echo "=== [START.SH] Launching Payjust Bot on PORT=${PORT:-8080} ==="
exec python3 -u bot.py
