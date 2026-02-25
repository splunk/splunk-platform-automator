#!/bin/bash
# ==============================================================================
# Run App Deployment Tests
# ==============================================================================
# Runs automated tests for Splunk app deployment (deploy_splunk_apps.yml).
#
# - test_app_deployment.py: pre-deployment checks (duplicate app, credentials,
#   valid config) via ansible-playbook with static localhost inventory.
# - test_schema.py: TestAppDeploymentConfig (splunk_app_deployment schema).
#
# No real Splunk hosts or AWS required. Requires ansible-playbook on PATH for
# playbook tests; schema tests need only pytest and pydantic.
#
# Usage:
#   ./run_app_deployment_tests.sh [pytest args...]
#
# Examples:
#   ./run_app_deployment_tests.sh                    # Run all app deployment tests
#   ./run_app_deployment_tests.sh -v                  # Verbose
#   ./run_app_deployment_tests.sh -k "duplicate"      # Only duplicate-app test
#   ./run_app_deployment_tests.sh -k "Schema"         # Only schema tests
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - App Deployment Tests ===${NC}"

VENV_DIR="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo -e "${GREEN}Creating test runner virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
    pip install -q 'pydantic>=2.0'
else
    source "$VENV_DIR/bin/activate"
    pip install -q 'pydantic>=2.0'
fi

cd "$PROJECT_ROOT"

# Run app deployment playbook tests, schema validation tests, and app deployment schema tests
pytest tests/test_app_deployment.py tests/test_schema.py -k "TestAppDeploymentPreDeploymentChecks or TestAppDeploymentSchemaValidation or TestAppDeploymentConfig" "$@"

echo -e "${GREEN}=== App deployment tests complete ===${NC}"
