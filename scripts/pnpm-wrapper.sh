#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  SOURCE_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
  LINK_TARGET="$(readlink "$SOURCE")"
  if [[ "$LINK_TARGET" = /* ]]; then
    SOURCE="$LINK_TARGET"
  else
    SOURCE="$SOURCE_DIR/$LINK_TARGET"
  fi
done
ROOT_DIR="$(cd "$(dirname "$SOURCE")/.." && pwd)"
export COREPACK_HOME="${COREPACK_HOME:-$ROOT_DIR/.tools/corepack}"
exec "$ROOT_DIR/.tools/node/bin/node" \
  "$ROOT_DIR/.tools/node/lib/node_modules/corepack/dist/pnpm.js" "$@"
