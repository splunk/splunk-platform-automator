#!/bin/bash
# ==============================================================================
# Umbrella live deployment runner
# ==============================================================================
# Runs suite files under tests/deployment/suites/. AWS always; CCM only when
# CCM_TOKEN is set (so AWS-only local runs do not compose CCM configs).
# AWS-only: ./run_deployment_aws_tests.sh
# CCM-only: ./run_deployment_ccm_tests.sh
#
# Usage:
#   ./run_deployment_tests.sh
#   ./run_deployment_tests.sh -k single_node
#   ./run_deployment_tests.sh -n 2
#   ./run_deployment_tests.sh -s
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - Deployment Tests ===${NC}"

if [[ -z "$AWS_ACCESS_KEY_ID" ]] || [[ -z "$AWS_SECRET_ACCESS_KEY" ]]; then
    echo -e "${YELLOW}WARNING: AWS credentials not found in environment.${NC}"
    echo "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY before running tests."
fi
if [[ -z "${CCM_TOKEN:-}" ]]; then
    echo -e "${YELLOW}WARNING: CCM_TOKEN is not set; skipping the ccm suite.${NC}"
fi

# Pass -- so pytest -k args are not inherited as pip package specs.
source "$SCRIPT_DIR/run_venv.sh" --

shopt -s nullglob
SUITE_FILES=("$SCRIPT_DIR"/deployment/suites/*.yml)
shopt -u nullglob

if [[ ${#SUITE_FILES[@]} -eq 0 ]]; then
    echo "No suite files under tests/deployment/suites/"
    exit 1
fi

USER_ARGS=()
HAS_PARALLEL=false
HAS_DIST=false
for arg in "$@"; do
    USER_ARGS+=("$arg")
    if [[ "$arg" == "-n" ]] || [[ "$arg" =~ ^-n[0-9]+ ]]; then
        HAS_PARALLEL=true
    fi
    if [[ "$arg" == "--dist" ]] || [[ "$arg" == --dist=* ]]; then
        HAS_DIST=true
    fi
done

for suite_file in "${SUITE_FILES[@]}"; do
    suite_id="$(basename "$suite_file" .yml)"
    if [[ "$suite_id" == "ccm" && -z "${CCM_TOKEN:-}" ]]; then
        echo -e "${YELLOW}Skipping ccm suite: CCM_TOKEN is not set${NC}"
        continue
    fi
    echo -e "${GREEN}--- suite: ${suite_id} ---${NC}"
    PYTEST_ARGS=("${USER_ARGS[@]}")
    if [[ "$HAS_PARALLEL" == false ]]; then
        if [[ "$suite_id" == "ccm" ]]; then
            topo_count=1
            echo -e "${YELLOW}Default parallel: -n 1 (CCM stages run one at a time)${NC}"
        else
            topo_count="$(
                python3 -c "
import sys, yaml
from pathlib import Path
data = yaml.safe_load(Path(sys.argv[1]).read_text()) or {}
print(len(data.get('topologies') or []))
" "$suite_file"
            )"
            if [[ -z "$topo_count" || "$topo_count" -lt 1 ]]; then
                topo_count=1
            fi
            echo -e "${YELLOW}Default parallel: -n ${topo_count} (one worker per topology)${NC}"
        fi
        PYTEST_ARGS+=("-n" "$topo_count")
    fi
    if [[ "$HAS_PARALLEL" == false || "$HAS_DIST" == false ]]; then
        if [[ " ${PYTEST_ARGS[*]} " != *" --dist=loadgroup "* ]] && [[ " ${PYTEST_ARGS[*]} " != *" --dist loadgroup "* ]]; then
            PYTEST_ARGS+=("--dist=loadgroup")
            echo -e "${YELLOW}Parallel mode: each topology stays on one worker (loadgroup)${NC}"
        fi
    fi
    pytest -m aws tests/test_deployment.py --deployment-suite "$suite_id" "${PYTEST_ARGS[@]}"
done

echo -e "${GREEN}=== Deployment tests complete ===${NC}"
