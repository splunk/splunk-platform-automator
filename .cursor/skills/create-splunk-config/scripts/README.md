# Scripts for create-splunk-config

Canonical scripts live in the **repository** `bin/` directory. Run from project root.

| Script | Purpose |
|--------|---------|
| `bin/splunk_config_aws.py` | AWS discovery (regions, AMIs, instance types, keys, SGs) and validation |
| `bin/validate_splunk_config.sh` | Schema + inventory + playbook syntax-check |

Do not duplicate logic in this skill folder. See [references/aws-baseline.md](../references/aws-baseline.md) and [references/validation.md](../references/validation.md).

## Dependencies

- `boto3` for `splunk_config_aws.py` (`pip install boto3`)
- AWS credentials for API discovery/validate
- Ansible + project venv for `validate_splunk_config.sh` (uses `tests/run_venv.sh` pattern)
