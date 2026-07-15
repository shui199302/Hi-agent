#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COREPACK_HOME="${COREPACK_HOME:-$ROOT_DIR/.tools/corepack}"
exec "$ROOT_DIR/.tools/node/bin/node" \
  "$ROOT_DIR/.tools/node/lib/node_modules/corepack/dist/pnpm.js" "$@"
