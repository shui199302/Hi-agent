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

web_needs_build=false
if [[ ! -f web/dist/index.html ]]; then
  web_needs_build=true
elif find web/src web/index.html web/package.json web/pnpm-lock.yaml \
  -type f -newer web/dist/index.html -print -quit 2>/dev/null | grep -q .; then
  web_needs_build=true
fi

if [[ "$web_needs_build" == "true" ]]; then
  PNPM_BIN="$(command -v pnpm 2>/dev/null || true)"
  if [[ -z "$PNPM_BIN" ]]; then
    echo "Web 需要重新构建但未找到 pnpm。请先运行 scripts/bootstrap.sh"
    exit 1
  fi
  echo "检测到 Web 源码更新，正在重新构建…"
  "$PNPM_BIN" --dir web build
fi

mkdir -p logs data
APP_URL="$("$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" --print-url)"

if [[ -f .hi-agent.pid ]]; then
  EXISTING_PID="$(cat .hi-agent.pid)"
  EXISTING_COMMAND="$(ps -p "$EXISTING_PID" -o command= 2>/dev/null || true)"
  if kill -0 "$EXISTING_PID" 2>/dev/null && [[ "$EXISTING_COMMAND" == *"scripts/serve.py"* ]]; then
    backend_needs_restart=false
    if find backend/src scripts/serve.py backend/pyproject.toml backend/uv.lock \
      -type f -newer .hi-agent.pid -print -quit 2>/dev/null | grep -q .; then
      backend_needs_restart=true
    elif [[ -f .env && .env -nt .hi-agent.pid ]]; then
      backend_needs_restart=true
    fi
    if [[ "$backend_needs_restart" == "false" ]]; then
      echo "Hi-agent 已在运行：$APP_URL"
      open "$APP_URL" 2>/dev/null || true
      exit 0
    fi
    echo "检测到后端源码或配置更新，正在重启 Hi-agent…"
    kill "$EXISTING_PID"
    for _ in {1..20}; do
      kill -0 "$EXISTING_PID" 2>/dev/null || break
      sleep 0.25
    done
  fi
  rm -f .hi-agent.pid
fi

echo "正在启动 Hi-agent…"
nohup "$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" \
  >logs/hi-agent.log 2>&1 </dev/null &
PID=$!
echo "$PID" > .hi-agent.pid

for _ in {1..60}; do
  if curl -fsS "$APP_URL/api/v1/health" >/dev/null 2>&1; then
    echo "Hi-agent 已启动：$APP_URL"
    open "$APP_URL" 2>/dev/null || true
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "启动失败，最近日志："
    tail -n 40 logs/hi-agent.log || true
    rm -f .hi-agent.pid
    exit 1
  fi
  sleep 0.5
done

echo "启动超时，最近日志："
tail -n 40 logs/hi-agent.log || true
kill "$PID" 2>/dev/null || true
rm -f .hi-agent.pid
exit 1
