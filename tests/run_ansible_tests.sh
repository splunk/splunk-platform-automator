#!/bin/bash
# Local tests that shell out to ansible-playbook.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/run_venv.sh" \
  'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml'

export PYTHONPATH="$(cd "$SCRIPT_DIR/.." && pwd)/lib${PYTHONPATH:+:$PYTHONPATH}"

DIST_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "-n" ]] || [[ "$arg" =~ ^-n[0-9]+ ]]; then
        # loadgroup honors xdist_group so one app-scope scenario stays on one worker
        DIST_ARGS=(--dist=loadgroup)
        break
    fi
done

pytest -m "local and ansible" tests/ "$@" "${DIST_ARGS[@]}"
