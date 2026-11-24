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

# Default is the full ansible track. CI sets SPA_ANSIBLE_MARKEXPR to run one chunk.
ANSIBLE_MARKEXPR="${SPA_ANSIBLE_MARKEXPR:-local and ansible}"
pytest -m "$ANSIBLE_MARKEXPR" tests/ -n auto "$@" "${DIST_ARGS[@]}"
