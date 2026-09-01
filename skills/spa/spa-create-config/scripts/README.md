# Scripts for spa-create-config

Canonical scripts live in the **repository** `bin/` directory. Run from project root.

| Script | Purpose |
|--------|---------|
| `bin/splunk_config_aws.py` | AWS discovery: `--check-auth`, `--latest-ami`, `--survey`, `--validate` |
| `bin/splunk_config_licenses.py` | Scan `../Software` for `.lic` files; propose `splunk_license_file` (ITSI-aware with `--config`) |
| `bin/validate_splunk_config.sh` | Schema + inventory + playbook syntax-check; optional `--check-licenses` |

Do not duplicate logic in this skill folder. See [references/aws-baseline.md](../references/aws-baseline.md) and [references/validation.md](../references/validation.md).

## SPA skill naming

Canonical skills live under `skills/spa/` ([Agent Skills spec](https://agentskills.io/specification.md)). Cursor discovers them via `.cursor/skills/` symlinks. Use the **`spa-`** prefix (`spa-create-config`, `spa-add-test-scenario`) for `/` command names in Cursor.

## Dependencies

- `boto3` for `splunk_config_aws.py` (`pip install boto3`)
- `PyYAML` for `splunk_config_licenses.py` with `--config` (`pip install PyYAML`)
- AWS credentials for API discovery/validate
- Ansible + project venv for `validate_splunk_config.sh` (uses `tests/run_venv.sh` pattern)
