#!/bin/bash
# ==============================================================================
# Run the AWS live deployment suite
# ==============================================================================
# Composes tests/deployment topologies with providers/aws.yml, then:
#   spa validate / spa deploy --yes / spa run verification/... / spa destroy --yes
#
# Usage:
#   ./run_deployment_aws_tests.sh                 # -n 4 --dist=loadgroup
#   ./run_deployment_aws_tests.sh -k single_node  # one topology
#   ./run_deployment_aws_tests.sh -n 2            # override worker count
#   ./run_deployment_aws_tests.sh -s              # show spa stdout
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - AWS deployment suite ===${NC}"

if [[ -z "$AWS_ACCESS_KEY_ID" ]] || [[ -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo -e "${YELLOW}WARNING: AWS credentials not found in environment.${NC}"
    echo "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY before running tests."
fi

source "$SCRIPT_DIR/run_venv.sh"

PYTEST_ARGS=()
HAS_PARALLEL=false
HAS_DIST=false
for arg in "$@"; do
    PYTEST_ARGS+=("$arg")
    if [[ "$arg" == "-n" ]] || [[ "$arg" =~ ^-n[0-9]+ ]]; then
        HAS_PARALLEL=true
    fi
    if [[ "$arg" == "--dist" ]] || [[ "$arg" == --dist=* ]]; then
        HAS_DIST=true
    fi
done

if [[ "$HAS_PARALLEL" == false ]]; then
    PYTEST_ARGS+=("-n" "4")
    HAS_PARALLEL=true
    echo -e "${YELLOW}Default parallel: -n 4 (one worker per AWS topology)${NC}"
fi
if [[ "$HAS_PARALLEL" == true && "$HAS_DIST" == false ]]; then
    PYTEST_ARGS+=("--dist=loadgroup")
    echo -e "${YELLOW}Parallel mode: each topology stays on one worker (loadgroup)${NC}"
fi

echo -e "${GREEN}Running AWS suite...${NC}"
pytest -m aws tests/test_deployment.py --deployment-suite aws "${PYTEST_ARGS[@]}"

echo -e "${GREEN}=== AWS deployment suite complete ===${NC}"
