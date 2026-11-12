#!/bin/bash
# Local tests that are neither CLI contracts nor ansible-playbook spawns.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/run_venv.sh" \
  'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml'

export PYTHONPATH="$(cd "$SCRIPT_DIR/.." && pwd)/lib${PYTHONPATH:+:$PYTHONPATH}"

pytest -m "local and not cli and not ansible" tests/ "$@"
