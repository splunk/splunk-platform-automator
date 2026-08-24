#!/bin/bash
# ==============================================================================
# Run ITSI Content Pack Tests
# ==============================================================================
# Runs unit and scenario tests for ITSI content pack deployment:
#   - test_itsi_content_pack.py       role task wiring and defaults
#   - test_schema.py (-k itsi_content_pack)  config validation
#   - test_app_scope_scenarios.py     scope/routing for CP scenarios
#
# No SSH or real Splunk hosts required. Scope tests run debug_app_scope.yml
# locally (ansible-playbook, jmespath, lxml installed via run_venv.sh).
#
# Usage:
#   ./run_itsi_content_pack_tests.sh [pytest args...]
#
# Examples:
#   ./run_itsi_content_pack_tests.sh              # Run all ITSI CP tests
#   ./run_itsi_content_pack_tests.sh -v           # Verbose
#   ./run_itsi_content_pack_tests.sh --tb=long    # Full tracebacks
#
# Note: Pass -v/--tb/etc. only; avoid -k here (each suite uses its own filter).
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - ITSI Content Pack Tests ===${NC}"

source "$SCRIPT_DIR/run_venv.sh" 'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml'

PYTEST_EXTRA=("$@")

echo -e "${GREEN}Running ITSI content pack role wiring tests...${NC}"
pytest tests/test_itsi_content_pack.py "${PYTEST_EXTRA[@]}"

echo -e "${GREEN}Running ITSI content pack schema validation tests...${NC}"
pytest tests/test_schema.py -k "itsi_content_pack" "${PYTEST_EXTRA[@]}"

echo -e "${GREEN}Running ITSI content pack scope scenario tests...${NC}"
pytest tests/test_app_scope_scenarios.py -k "itsi_content_pack or itsi_standalone_sh or itsi_multi_shc" "${PYTEST_EXTRA[@]}"

echo -e "${GREEN}=== ITSI content pack tests complete ===${NC}"
