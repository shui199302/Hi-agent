#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.tools/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT_DIR/.tools/python}"
export PATH="$ROOT_DIR/.tools/bin:$ROOT_DIR/.tools/node/bin:$PATH"

UV_BIN="$(command -v uv 2>/dev/null || true)"
if [[ -z "$UV_BIN" && -x "$ROOT_DIR/.tools/bin/uv" ]]; then
  UV_BIN="$ROOT_DIR/.tools/bin/uv"
fi
if [[ -z "$UV_BIN" ]]; then
  echo "未找到 uv。请先运行 scripts/bootstrap.sh"
  exit 1
fi

if [[ ! -f web/dist/index.html ]]; then
  PNPM_BIN="$(command -v pnpm 2>/dev/null || true)"
  if [[ -z "$PNPM_BIN" ]]; then
    echo "Web 尚未构建且未找到 pnpm。请先运行 scripts/bootstrap.sh"
    exit 1
  fi
  "$PNPM_BIN" --dir web build
fi

mkdir -p logs data
APP_URL="$("$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" --print-url)"

if [[ -f .hi-agent.pid ]] && kill -0 "$(cat .hi-agent.pid)" 2>/dev/null; then
  echo "Hi-agent 已在运行：$APP_URL"
  open "$APP_URL" 2>/dev/null || true
  exit 0
fi

echo "正在启动 Hi-agent…"
"$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" \
  >logs/hi-agent.log 2>&1 &
PID=$!
echo "$PID" > .hi-agent.pid

cleanup() {
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
  fi
  rm -f .hi-agent.pid
}
trap cleanup EXIT INT TERM

for _ in {1..60}; do
  if curl -fsS "$APP_URL/api/v1/health" >/dev/null 2>&1; then
    echo "Hi-agent 已启动：$APP_URL"
    open "$APP_URL" 2>/dev/null || true
    wait "$PID"
    exit $?
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "启动失败，最近日志："
    tail -n 40 logs/hi-agent.log || true
    exit 1
  fi
  sleep 0.5
done

echo "启动超时，最近日志："
tail -n 40 logs/hi-agent.log || true
exit 1
