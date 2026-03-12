#!/bin/bash
# ==============================================================================
# Run Secret Resolver (Vault) Unit Tests
# ==============================================================================
# Runs unit tests for secret_resolver.py (in-place vault decryption in config).
# No infrastructure or vault password required for current tests.
#
# Usage:
#   ./run_secret_resolver_tests.sh [pytest args...]
#
# Examples:
#   ./run_secret_resolver_tests.sh                 # Run all secret resolver tests
#   ./run_secret_resolver_tests.sh -v              # Verbose
#   ./run_secret_resolver_tests.sh -k "LoadConfig"  # Only LoadConfig tests
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Splunk Platform Automator - Secret Resolver Tests ===${NC}"

source "$SCRIPT_DIR/run_venv.sh" ansible-core

# Use a test-only Ansible config so the project's ansible.cfg (and config directory
# inventory) are not loaded. Avoids side effects from config/splunk_config.yml etc.
# local_tmp under tests/ is writable in sandboxed/CI.
mkdir -p "${SCRIPT_DIR}/.ansible_tmp"
export ANSIBLE_CONFIG="${SCRIPT_DIR}/ansible_test.cfg"

echo -e "${GREEN}Running secret resolver and vault decrypt lookup tests...${NC}"
pytest tests/test_secret_resolver.py tests/test_spa_vault_decrypt.py "$@"

echo -e "${GREEN}=== Secret resolver tests complete ===${NC}"
