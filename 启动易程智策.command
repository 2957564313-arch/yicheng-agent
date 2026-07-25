#!/bin/zsh
set -e

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "尚未配置项目环境，请先在项目目录执行：uv sync"
  read -r "?按回车键关闭..."
  exit 1
fi

"$PYTHON_BIN" -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 &

SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

sleep 2
open "http://127.0.0.1:8000/"
wait "$SERVER_PID"
