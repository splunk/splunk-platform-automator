#!/bin/bash
# ==============================================================================
# Run App Scope Scenario Tests
# ==============================================================================
# Runs scenario-based tests for app scope (debug_app_scope.yml).
#
# For each scenario under tests/configs/app_scope/<name>/splunk_config.yml,
# runs debug_app_scope.yml with run_scope_locally=true and asserts on the
# produced scope_debug.json. No SSH or real Splunk hosts required.
#
# Requires ansible-playbook, jmespath, lxml in the venv (installed via run_venv.sh).
# Uses tests/.venv (created if missing).
#
# Usage:
#   ./run_app_scope_scenarios_tests.sh [pytest args...]
#
# Examples:
#   ./run_app_scope_scenarios_tests.sh              # Run all scope scenario tests
#   ./run_app_scope_scenarios_tests.sh -v           # Verbose
#   ./run_app_scope_scenarios_tests.sh -k "minimal" # Only minimal_direct scenario
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - App Scope Scenario Tests ===${NC}"

# ansible-core + jmespath/lxml required for inventory plugin when running debug_app_scope.yml
source "$SCRIPT_DIR/run_venv.sh" 'pydantic>=2.0' 'ansible-core' 'jmespath' 'lxml'

pytest tests/test_app_scope_scenarios.py "$@"

echo -e "${GREEN}=== App scope scenario tests complete ===${NC}"
