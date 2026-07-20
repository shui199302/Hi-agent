#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.tools/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT_DIR/.tools/python}"
export PATH="$ROOT_DIR/.tools/bin:$ROOT_DIR/.tools/node/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "$ROOT_DIR/.tools/bin/uv" ]]; then
  UV_BIN="$ROOT_DIR/.tools/bin/uv"
else
  echo "未找到 uv，请先运行 scripts/bootstrap.sh" >&2
  exit 1
fi
PNPM_BIN="$(command -v pnpm 2>/dev/null || true)"
[[ -n "$PNPM_BIN" ]] || { echo "未找到 pnpm，请先运行 scripts/bootstrap.sh" >&2; exit 1; }

BACKEND_PID=""
WEB_PID=""
cleanup() {
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/logs"
APP_URL="$("$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" --print-url)"
"$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" --reload &
BACKEND_PID=$!
HI_AGENT_API_ORIGIN="$APP_URL" "$PNPM_BIN" --dir "$ROOT_DIR/web" dev &
WEB_PID=$!
printf 'API: %s\nWeb: http://127.0.0.1:5173\n' "$APP_URL"

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done
exit 1
