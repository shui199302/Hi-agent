#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .hi-agent.pid ]]; then
  echo "Hi-agent 当前没有由 start.command 启动的进程。"
  exit 0
fi

PID="$(cat .hi-agent.pid)"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in {1..20}; do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.25
  done
fi
rm -f .hi-agent.pid
echo "Hi-agent 已停止。"

