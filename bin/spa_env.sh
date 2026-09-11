#!/usr/bin/env bash
# ==============================================================================
# Export SPA_HOME / SPA_LAB_DIR / ANSIBLE_* for a clone or a separate lab.
# Source this file:  source bin/spa_env.sh
# Or print exports:  bin/spa_env.sh [--start-dir DIR]
# ==============================================================================

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SPA_HOME="$(cd "$BIN_DIR/.." && pwd)"
RESOLVER="${SPA_HOME:-$DEFAULT_SPA_HOME}/ansible/plugins/inventory/spa_paths.py"

if [[ ! -f "$RESOLVER" ]]; then
    echo "spa_paths resolver not found: ${RESOLVER}" >&2
    return 1 2>/dev/null || exit 1
fi

# When sourced, apply exports in the current shell. When executed, print them.
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    eval "$(python3 "$RESOLVER" --export "$@")"
else
    set -euo pipefail
    python3 "$RESOLVER" --export "$@"
fi
