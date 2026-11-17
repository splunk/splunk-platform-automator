#!/bin/bash
# Local tests that run playbooks through spa run (plus the JSONL callback fixture).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/run_venv.sh" \
  'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml'

export PYTHONPATH="$(cd "$SCRIPT_DIR/.." && pwd)/lib${PYTHONPATH:+:$PYTHONPATH}"

DIST_ARGS=()
for arg in -n auto "$@"; do
    if [[ "$arg" == "-n" ]] || [[ "$arg" =~ ^-n[0-9]+ ]]; then
        # loadgroup honors xdist_group so one app-scope scenario stays on one worker
        DIST_ARGS=(--dist=loadgroup)
        break
    fi
done

pytest -m "local and ansible" tests/ -n auto "$@" "${DIST_ARGS[@]}"
