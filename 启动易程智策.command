#!/bin/zsh
set -e

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

UV_CACHE_DIR="$PROJECT_DIR/.tooling/uv-cache" \
  "$PROJECT_DIR/.tooling/uv-bootstrap/bin/uv" run \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 &

SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

sleep 2
open "http://127.0.0.1:8000/"
wait "$SERVER_PID"
