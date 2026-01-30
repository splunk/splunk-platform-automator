#!/bin/bash
# ==============================================================================
# Run Verification Tests
# ==============================================================================
# This script runs verification tests against deployed Splunk environments.
#
# Usage:
#   ./run_verification_tests.sh [pytest args...]
#
# Examples:
#   ./run_verification_tests.sh                            # Run all verification tests
#   ./run_verification_tests.sh -k "single_node"           # Run only single_node config
#   ./run_verification_tests.sh -n 2                       # Run with 2 parallel workers
#   ./run_verification_tests.sh --local                    # Run against existing local deployment
#   ./run_verification_tests.sh --local -s                 # Local mode with output visible
#
# The --local flag runs tests against your existing local deployment:
#   - Uses config/splunk_config.yml from the project root
#   - Does NOT create a temp workspace or venv
#   - Does NOT destroy infrastructure after tests
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

echo -e "${GREEN}=== Splunk Platform Automator - Verification Tests ===${NC}"

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
if [[ "$HAS_PARALLEL" == true ]]; then
    PYTEST_ARGS+=("--dist=loadgroup")
    echo -e "${YELLOW}Parallel mode: Each config runs on a separate worker${NC}"
fi

# Run verification tests
echo -e "${GREEN}Running verification tests...${NC}"
cd "$PROJECT_ROOT"

pytest tests/test_verification.py "${PYTEST_ARGS[@]}"

echo -e "${GREEN}=== Verification tests complete ===${NC}"

