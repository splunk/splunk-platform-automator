#!/bin/bash
# Fast release-contract suite for spa help, parsing, routing, and backend calls.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CLI modules need the same Python packages as a normal SPA installation, but
# these tests mock Ansible/provider execution and never contact AWS or hosts.
source "$SCRIPT_DIR/run_venv.sh" \
  'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml' 'boto3'

export PYTHONPATH="$(cd "$SCRIPT_DIR/.." && pwd)/lib${PYTHONPATH:+:$PYTHONPATH}"
export ANSIBLE_LOCAL_TMP="${SCRIPT_DIR}/.ansible_tmp"

pytest -m cli tests/ "$@"
