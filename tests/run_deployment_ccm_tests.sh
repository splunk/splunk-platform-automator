#!/bin/bash
# ==============================================================================
# Run the CCM live deployment suite (ES topologies)
# ==============================================================================
# Composes tests/deployment topologies with providers/ccm.yml, then:
#   spa validate / spa deploy --yes / spa run verification/... / spa destroy --yes
#
# This script does not create CCM resources by itself; pytest live steps do.
# Slice 7 is the live-run owner. Default -n 1 so stages run one at a time.
#
# Usage:
#   ./run_deployment_ccm_tests.sh                      # -n 1 --dist=loadgroup
#   ./run_deployment_ccm_tests.sh -k single_node_es    # one topology
#   ./run_deployment_ccm_tests.sh -n 1                 # explicit worker count
#   ./run_deployment_ccm_tests.sh -s                   # show spa stdout
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - CCM deployment suite ===${NC}"

if [[ -z "${CCM_TOKEN:-}" ]]; then
    echo -e "${YELLOW}WARNING: CCM_TOKEN is not set.${NC}"
    echo "Set CCM_TOKEN before running CCM live tests."
fi

# Pass -- so pytest -k args are not inherited as pip package specs.
source "$SCRIPT_DIR/run_venv.sh" --

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
    PYTEST_ARGS+=("-n" "1")
    HAS_PARALLEL=true
    echo -e "${YELLOW}Default parallel: -n 1 (CCM stages run one at a time)${NC}"
fi
if [[ "$HAS_PARALLEL" == true && "$HAS_DIST" == false ]]; then
    PYTEST_ARGS+=("--dist=loadgroup")
    echo -e "${YELLOW}Parallel mode: each topology stays on one worker (loadgroup)${NC}"
fi

echo -e "${GREEN}Running CCM suite...${NC}"
pytest -m aws tests/test_deployment.py --deployment-suite ccm "${PYTEST_ARGS[@]}"

echo -e "${GREEN}=== CCM deployment suite complete ===${NC}"
