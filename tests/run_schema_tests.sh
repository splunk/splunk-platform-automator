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
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - Schema Validation Tests ===${NC}"

source "$SCRIPT_DIR/run_venv.sh" 'pydantic>=2.0'

echo -e "${GREEN}Running schema validation tests...${NC}"
pytest tests/test_schema.py "$@"

echo -e "${GREEN}=== Schema validation tests complete ===${NC}"
