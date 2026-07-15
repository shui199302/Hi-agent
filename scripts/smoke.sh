#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.tools/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT_DIR/.tools/python}"
CUSTOM_URL="${HI_AGENT_SMOKE_URL:-}"
TMP_DIR=""
SERVER_PID=""
EXPECT_APPROVAL="false"

if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "$ROOT_DIR/.tools/bin/uv" ]]; then
  UV_BIN="$ROOT_DIR/.tools/bin/uv"
else
  echo "未找到 uv，请先运行 scripts/bootstrap.sh" >&2
  exit 1
fi
BASE_URL="${CUSTOM_URL:-$("$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" --print-url)}"

cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  [[ -n "$SERVER_PID" ]] && wait "$SERVER_PID" 2>/dev/null || true
  [[ -n "$TMP_DIR" ]] && rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

if ! curl -fsS "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
  if [[ -n "$CUSTOM_URL" ]]; then
    echo "无法连接自定义 HI_AGENT_SMOKE_URL: $BASE_URL" >&2
    exit 1
  fi
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hi-agent-smoke.XXXXXX")"
  HI_AGENT_DATA_DIR="$TMP_DIR/data" \
  HI_AGENT_EMBEDDING_BACKEND=deterministic \
  HI_AGENT_ALLOW_SKILL_SCRIPTS=true \
    "$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync python "$ROOT_DIR/scripts/serve.py" \
      >"$TMP_DIR/server.log" 2>&1 &
  SERVER_PID=$!
  EXPECT_APPROVAL="true"
  for _ in {1..60}; do
    curl -fsS "$BASE_URL/api/v1/health" >/dev/null 2>&1 && break
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      cat "$TMP_DIR/server.log" >&2
      exit 1
    fi
    sleep 0.25
  done
fi

SMOKE_ARGS=(--base-url "$BASE_URL")
if [[ "$EXPECT_APPROVAL" == "true" ]]; then
  SMOKE_ARGS+=(--expect-approval)
fi
"$UV_BIN" run --project "$ROOT_DIR/backend" --no-sync \
  python "$ROOT_DIR/scripts/api_smoke.py" "${SMOKE_ARGS[@]}"
