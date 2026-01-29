#!/bin/bash
# ==============================================================================
# Run Deployment Tests
# ==============================================================================
# This script sets up the test runner environment and executes deployment tests.
#
# Usage:
#   ./run_deployment_tests.sh [pytest args...]
#
# Examples:
#   ./run_deployment_tests.sh                              # Run all deployment tests
#   ./run_deployment_tests.sh -k "single_node"             # Run only single_node config
#   ./run_deployment_tests.sh -n 2                         # Run with 2 parallel workers
#   ./run_deployment_tests.sh -s                           # Show stdout in real-time
#
# Note: When using -n for parallel execution, tests are grouped by config file
#       to maintain sequential dependencies within each test suite.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Splunk Platform Automator - Deployment Tests ===${NC}"

# Check for AWS credentials
if [[ -z "$AWS_ACCESS_KEY_ID" ]] || [[ -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo -e "${YELLOW}WARNING: AWS credentials not found in environment.${NC}"
    echo "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY before running tests."
fi

# Create or activate test runner venv
VENV_DIR="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo -e "${GREEN}Creating test runner virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
else
    source "$VENV_DIR/bin/activate"
fi

# Build pytest arguments
# If -n is specified, add --dist=loadscope to keep tests grouped by config
PYTEST_ARGS=()
HAS_PARALLEL=false

for arg in "$@"; do
    PYTEST_ARGS+=("$arg")
    if [[ "$arg" == "-n" ]] || [[ "$arg" =~ ^-n[0-9]+ ]]; then
        HAS_PARALLEL=true
    fi
done

# Add distribution strategy for parallel runs
# loadgroup uses @pytest.mark.xdist_group markers (assigned based on config_file)
# This ensures tests for each config run on the same worker, but different
# configs run in parallel on different workers
if [[ "$HAS_PARALLEL" == true ]]; then
    PYTEST_ARGS+=("--dist=loadgroup")
    echo -e "${YELLOW}Parallel mode: Each config runs on a separate worker${NC}"
fi

# Run deployment tests
echo -e "${GREEN}Running deployment tests...${NC}"
cd "$PROJECT_ROOT"

pytest tests/test_deployment.py "${PYTEST_ARGS[@]}"

echo -e "${GREEN}=== Deployment tests complete ===${NC}"
