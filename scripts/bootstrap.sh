#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
BIN_DIR="$TOOLS_DIR/bin"
NODE_VERSION="22.17.0"
PNPM_VERSION="11.7.0"
mkdir -p "$BIN_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$TOOLS_DIR/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$TOOLS_DIR/python}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$TOOLS_DIR/playwright}"
export PATH="$BIN_DIR:$TOOLS_DIR/node/bin:$PATH"

note() { printf '==> %s\n' "$*"; }
die() { printf '错误: %s\n' "$*" >&2; exit 1; }

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
  elif [[ -x "$BIN_DIR/uv" ]]; then
    printf '%s\n' "$BIN_DIR/uv"
  fi
}

install_uv() {
  command -v curl >/dev/null 2>&1 || die "安装 uv 需要 curl"
  local installer
  installer="$(mktemp "${TMPDIR:-/tmp}/hi-agent-uv.XXXXXX")"
  note "从 astral.sh 下载 uv 安装器"
  curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh -o "$installer"
  UV_INSTALL_DIR="$BIN_DIR" UV_NO_MODIFY_PATH=1 sh "$installer"
  rm -f "$installer"
}

platform_archive() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"
  case "$os/$arch" in
    Darwin/arm64) printf 'node-v%s-darwin-arm64.tar.gz\n' "$NODE_VERSION" ;;
    Darwin/x86_64) printf 'node-v%s-darwin-x64.tar.gz\n' "$NODE_VERSION" ;;
    Linux/aarch64|Linux/arm64) printf 'node-v%s-linux-arm64.tar.gz\n' "$NODE_VERSION" ;;
    Linux/x86_64) printf 'node-v%s-linux-x64.tar.gz\n' "$NODE_VERSION" ;;
    *) return 1 ;;
  esac
}

install_node() {
  command -v curl >/dev/null 2>&1 || die "安装 Node.js 需要 curl"
  command -v tar >/dev/null 2>&1 || die "安装 Node.js 需要 tar"
  local archive url work expected actual extracted
  archive="$(platform_archive)" || die "不支持的平台: $(uname -s)/$(uname -m)"
  url="https://nodejs.org/dist/v${NODE_VERSION}"
  work="$(mktemp -d "${TMPDIR:-/tmp}/hi-agent-node.XXXXXX")"
  note "下载 Node.js $NODE_VERSION 到项目 .tools 目录"
  curl --proto '=https' --tlsv1.2 -fsSL "$url/$archive" -o "$work/$archive"
  curl --proto '=https' --tlsv1.2 -fsSL "$url/SHASUMS256.txt" -o "$work/SHASUMS256.txt"
  expected="$(awk -v name="$archive" '$2 == name {print $1}' "$work/SHASUMS256.txt")"
  [[ -n "$expected" ]] || die "Node.js 校验清单中没有 $archive"
  if command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$work/$archive" | awk '{print $1}')"
  else
    actual="$(sha256sum "$work/$archive" | awk '{print $1}')"
  fi
  [[ "$actual" == "$expected" ]] || die "Node.js 下载校验失败"
  tar -xzf "$work/$archive" -C "$TOOLS_DIR"
  extracted="${archive%.tar.gz}"
  ln -sfn "$extracted" "$TOOLS_DIR/node"
  rm -rf "$work"
}

UV_BIN="$(find_uv || true)"
if [[ -z "$UV_BIN" ]]; then
  install_uv
  UV_BIN="$(find_uv || true)"
fi
[[ -x "$UV_BIN" ]] || die "uv 安装失败"

NODE_MAJOR=0
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || printf '0')"
fi
if (( NODE_MAJOR < 22 )); then
  install_node
  export PATH="$TOOLS_DIR/node/bin:$PATH"
fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) process.exit(1)' \
  || die "需要 Node.js 22 或更高的兼容版本"

if ! command -v pnpm >/dev/null 2>&1 || [[ "$(pnpm --version 2>/dev/null || true)" != "$PNPM_VERSION" ]]; then
  command -v corepack >/dev/null 2>&1 || die "未找到 pnpm 或 corepack"
  corepack enable --install-directory "$BIN_DIR"
  corepack prepare "pnpm@${PNPM_VERSION}" --activate
  export PATH="$BIN_DIR:$PATH"
fi
command -v pnpm >/dev/null 2>&1 || die "未找到 pnpm；Node.js 的 corepack 未能启用它"

note "安装 Python 3.12 和后端依赖"
"$UV_BIN" python install 3.12
"$UV_BIN" sync --project "$ROOT_DIR/backend" --frozen --all-extras --dev
note "安装只读 MCP 示例服务器"
"$UV_BIN" sync --project "$ROOT_DIR/mcp_servers" --frozen --dev

note "安装并构建 Web 控制台"
pnpm --dir "$ROOT_DIR/web" install --frozen-lockfile
pnpm --dir "$ROOT_DIR/web" build
if [[ "${HI_AGENT_SKIP_BROWSER_DOWNLOAD:-false}" != "true" ]]; then
  note "安装 Playwright Chromium 端到端测试浏览器"
  pnpm --dir "$ROOT_DIR/web" exec playwright install chromium
fi

if [[ "${HI_AGENT_SKIP_MODEL_DOWNLOAD:-false}" != "true" ]]; then
  note "预下载中文嵌入模型（不会下载大语言模型）"
  "$UV_BIN" run --project "$ROOT_DIR/backend" python "$ROOT_DIR/scripts/preload_embedding.py"
fi

note "运行环境诊断"
PATH="$BIN_DIR:$TOOLS_DIR/node/bin:$PATH" "$ROOT_DIR/scripts/doctor.sh"
note "安装完成。复制 .env.example 为 .env 后运行 ./start.command"
