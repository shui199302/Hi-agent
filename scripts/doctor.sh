#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILURES=0
WARNINGS=0
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.tools/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT_DIR/.tools/python}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT_DIR/.tools/playwright}"
export PATH="$ROOT_DIR/.tools/bin:$ROOT_DIR/.tools/node/bin:$PATH"

ok() { printf '✓ %s\n' "$*"; }
warn() { printf '! %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '✗ %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "$ROOT_DIR/.tools/bin/uv" ]]; then
  UV_BIN="$ROOT_DIR/.tools/bin/uv"
else
  UV_BIN=""
fi
if [[ -n "$UV_BIN" ]]; then
  ok "uv: $($UV_BIN --version 2>/dev/null)"
  if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]] \
    && [[ "$("$ROOT_DIR/backend/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" == "3.12" ]]; then
    PY312="$ROOT_DIR/backend/.venv/bin/python"
    ok "Python 3.12: $PY312"
  elif PY312="$($UV_BIN python find 3.12 2>/dev/null)"; then
    ok "Python 3.12: $PY312"
  else
    fail "uv 尚未安装 Python 3.12（运行 scripts/bootstrap.sh）"
  fi
else
  fail "未找到 uv"
fi

if command -v node >/dev/null 2>&1; then
  NODE_VERSION="$(node --version 2>/dev/null || true)"
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || printf '0')"
  if (( NODE_MAJOR >= 22 )); then
    ok "Node.js: $NODE_VERSION"
  else
    warn "Node.js $NODE_VERSION 低于项目基线 22；bootstrap 会安装项目内 Node 22"
  fi
else
  fail "未找到 Node.js"
fi

if command -v pnpm >/dev/null 2>&1; then
  ok "pnpm: $(pnpm --version 2>/dev/null)"
else
  fail "未找到 pnpm"
fi
command -v curl >/dev/null 2>&1 && ok "curl 可用" || fail "未找到 curl"

for required in \
  backend/pyproject.toml \
  backend/src/hi_agent/main.py \
  web/package.json \
  skills/knowledge-base-qa/SKILL.md \
  deploy/vllm-compose.yml; do
  [[ -f "$ROOT_DIR/$required" ]] || fail "缺少项目文件: $required"
done

[[ -f "$ROOT_DIR/.env" ]] && ok ".env 已配置" || warn "尚未创建 .env，将使用安全默认值"
[[ -d "$ROOT_DIR/backend/.venv" ]] && ok "后端虚拟环境已安装" || warn "后端依赖尚未安装"
[[ -f "$ROOT_DIR/web/dist/index.html" ]] && ok "Web 已构建" || warn "Web 尚未构建"
[[ -d "$PLAYWRIGHT_BROWSERS_PATH" ]] && ok "Playwright Chromium 已安装" || warn "Playwright 浏览器尚未安装"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "Docker Compose 可用（仅 Linux/NVIDIA 主机运行 vLLM）"
else
  warn "Docker Compose 不可用；这不影响 Mac 作为 vLLM 客户端"
fi

if [[ -f "$ROOT_DIR/.hi-agent.pid" ]]; then
  PID="$(cat "$ROOT_DIR/.hi-agent.pid" 2>/dev/null || true)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    ok "Hi-agent 正在运行（PID $PID）"
  else
    warn "发现失效的 .hi-agent.pid"
  fi
fi

printf '\n诊断完成：%d 个错误，%d 个提醒。\n' "$FAILURES" "$WARNINGS"
(( FAILURES == 0 ))
