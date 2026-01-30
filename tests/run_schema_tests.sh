#!/bin/bash
# ==============================================================================
# Run Schema Validation Tests
# ==============================================================================
# This script runs unit tests for YAML configuration schema validation.
# These tests do NOT require infrastructure - they validate config structure only.
#
# Usage:
#   ./run_schema_tests.sh [pytest args...]
#
# Examples:
#   ./run_schema_tests.sh                    # Run all schema tests
#   ./run_schema_tests.sh -v                 # Run with verbose output
#   ./run_schema_tests.sh -k "invalid"       # Run only invalid config tests
#   ./run_schema_tests.sh --tb=long          # Show full tracebacks
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Splunk Platform Automator - Schema Validation Tests ===${NC}"

# Create or activate test runner venv
VENV_DIR="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo -e "${GREEN}Creating test runner virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
    # Ensure pydantic is installed
    pip install 'pydantic>=2.0'
else
    source "$VENV_DIR/bin/activate"
    # Ensure pydantic is installed
    pip install -q 'pydantic>=2.0'
fi

# Run schema validation tests
echo -e "${GREEN}Running schema validation tests...${NC}"
cd "$PROJECT_ROOT"

pytest tests/test_schema.py "$@"

echo -e "${GREEN}=== Schema validation tests complete ===${NC}"
