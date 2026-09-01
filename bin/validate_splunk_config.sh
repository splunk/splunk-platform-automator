#!/usr/bin/env bash
# ==============================================================================
# Validate splunk_config.yml — schema, inventory plugin, playbook syntax-check
# ==============================================================================
# Usage:
#   ./bin/validate_splunk_config.sh [path/to/splunk_config.yml]
#   ./bin/validate_splunk_config.sh --check-licenses config/splunk_config.yml
#   ./bin/validate_splunk_config.sh --splunk-config-aws config/splunk_config.yml
#
# Default config path: config/splunk_config.yml
# ==============================================================================

set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$BIN_DIR/.." && pwd)"
CONFIG_PATH="${PROJECT_ROOT}/config/splunk_config.yml"
RUN_AWS_VALIDATE=false
RUN_LICENSE_CHECK=false

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
    echo "Usage: $0 [--check-licenses] [--splunk-config-aws] [path/to/splunk_config.yml]"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-licenses)
            RUN_LICENSE_CHECK=true
            shift
            ;;
        --splunk-config-aws)
            RUN_AWS_VALIDATE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            CONFIG_PATH="$1"
            if [[ "$CONFIG_PATH" != /* ]]; then
                CONFIG_PATH="${PROJECT_ROOT}/${CONFIG_PATH}"
            fi
            shift
            ;;
    esac
done

if [[ ! -f "$CONFIG_PATH" ]]; then
    echo -e "${RED}Config file not found: ${CONFIG_PATH}${NC}" >&2
    exit 1
fi

cd "$PROJECT_ROOT"

echo -e "${GREEN}=== Validating ${CONFIG_PATH} ===${NC}"

# Schema validation via Pydantic
echo -e "${GREEN}[1/3] Schema validation (Pydantic)...${NC}"
source "${PROJECT_ROOT}/tests/run_venv.sh" 'pydantic>=2.0' 'PyYAML>=6.0' 'ansible-core>=2.10' 'jmespath' 'lxml'

PYTHONPATH="${PROJECT_ROOT}/ansible/plugins/inventory" python3 - "$CONFIG_PATH" <<'PY'
import sys
from schema import validate_config_file, ConfigValidationError

path = sys.argv[1]
try:
    validate_config_file(path)
    print(f"Schema OK: {path}")
except ConfigValidationError as e:
    print(e, file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Schema validation failed: {e}", file=sys.stderr)
    sys.exit(1)
PY

# Inventory plugin
echo -e "${GREEN}[2/3] Inventory plugin (ansible-inventory)...${NC}"
export ANSIBLE_CONFIG="${PROJECT_ROOT}/ansible.cfg"
export ANSIBLE_INVENTORY="${CONFIG_PATH}"
export ANSIBLE_INVENTORY_PLUGINS="${PROJECT_ROOT}/ansible/plugins/inventory"
ansible-inventory --list >/dev/null
echo "Inventory OK"

# Playbook syntax-check
echo -e "${GREEN}[3/3] Playbook syntax-check...${NC}"
export ANSIBLE_CONFIG="${PROJECT_ROOT}/ansible.cfg"
ansible-playbook ansible/provision_terraform_aws.yml --syntax-check
ansible-playbook ansible/deploy_site.yml --syntax-check
echo "Playbook syntax OK"

# Optional Software directory license check
if [[ "$RUN_LICENSE_CHECK" == true ]]; then
    echo -e "${GREEN}[optional] Software license file check...${NC}"
    LICENSE_JSON="$(python3 "${PROJECT_ROOT}/bin/splunk_config_licenses.py" --config "$CONFIG_PATH" --json)"
    echo "$LICENSE_JSON"
    python3 - "$LICENSE_JSON" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
warnings = data.get("warnings") or []
configured = data.get("configured_splunk_license_file")
proposed = data.get("proposed_splunk_license_file") or []
discovered = {d["basename"] for d in data.get("discovered_files") or []}

if configured:
    missing = [name for name in configured if name not in discovered]
    if missing:
        print(f"Configured license file(s) not found in Software: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

if data.get("itsi_in_config") and not data.get("license_manager_in_config"):
    print("ITSI in config but no license_manager role on any host", file=sys.stderr)
    sys.exit(1)

if data.get("itsi_in_config") and data.get("itsi_license") is None:
    print("ITSI in config but Splunk_ITSI.lic not found in Software", file=sys.stderr)
    sys.exit(1)

if warnings:
    for w in warnings:
        print(f"License note: {w}", file=sys.stderr)

if not configured and proposed:
    print(
        "Tip: licenses available in Software — consider adding splunk_license_file "
        f"(proposed: {', '.join(proposed)})",
        file=sys.stderr,
    )
PY
    echo "License check OK"
fi

# Optional AWS API validation
if [[ "$RUN_AWS_VALIDATE" == true ]]; then
    echo -e "${GREEN}[optional] AWS terraform.aws validation...${NC}"
    PYTHONPATH="${PROJECT_ROOT}/ansible/plugins/inventory" python3 - "$CONFIG_PATH" "$PROJECT_ROOT" <<'PY'
import subprocess
import sys
import yaml

config_path = sys.argv[1]
project_root = sys.argv[2]

with open(config_path) as f:
    data = yaml.safe_load(f) or {}

aws = (data.get("terraform") or {}).get("aws") or {}
region = aws.get("region")
ami_id = aws.get("ami_id")
key_name = aws.get("key_name")
instance_type = aws.get("instance_type")
sg_names = aws.get("security_group_names") or []

if not region:
    print("Skipping AWS validate: no terraform.aws.region in config", file=sys.stderr)
    sys.exit(0)

cmd = [
    "python3",
    f"{project_root}/bin/splunk_config_aws.py",
    "--region",
    region,
    "--validate",
    "--json",
]
if ami_id:
    cmd.extend(["--ami-id", ami_id])
if key_name:
    cmd.extend(["--key-name", key_name])
if instance_type:
    cmd.extend(["--instance-type", instance_type])
if sg_names:
    cmd.extend(["--security-groups", ",".join(sg_names)])

result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
PY
    echo "AWS validation OK"
fi

echo -e "${GREEN}=== Validation complete ===${NC}"
