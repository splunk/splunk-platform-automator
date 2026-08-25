#!/bin/bash
# ==============================================================================
# Run All Local Tests
# ==============================================================================
# Runs every test marked @pytest.mark.local (no AWS or live Splunk deployment).
#
# Equivalent to: pytest -m local tests/
#
# NOT included (@pytest.mark.aws):
#   run_deployment_tests.sh          AWS provisioning + full deployment pipeline
#   run_verification_tests.sh        Existing deployment (optional: --local)
#
# Individual suites can still be run via their run_*.sh scripts or with markers:
#   pytest -m local tests/test_schema.py
#   pytest -m "local and itsi" tests/
#
# Usage:
#   ./run_local_tests.sh [pytest args...]
#
# Examples:
#   ./run_local_tests.sh             # Run all local tests (single pytest invocation)
#   ./run_local_tests.sh -v          # Verbose test names
#   ./run_local_tests.sh -s          # Show stdout/stderr (no capture)
#   ./run_local_tests.sh -sv         # Verbose + show output
#   ./run_local_tests.sh --tb=long   # Full tracebacks
#   ./run_local_tests.sh -k "minimal_direct" -v
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - All Local Tests ===${NC}"

source "$SCRIPT_DIR/run_venv.sh" 'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml'

mkdir -p "${SCRIPT_DIR}/.ansible_tmp"
export ANSIBLE_LOCAL_TMP="${SCRIPT_DIR}/.ansible_tmp"

echo -e "${GREEN}Running pytest -m local ...${NC}"
pytest -m local tests/ "$@"

echo -e "${GREEN}=== All local tests complete ===${NC}"
