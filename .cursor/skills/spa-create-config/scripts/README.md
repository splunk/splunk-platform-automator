# Scripts for spa-create-config

Canonical scripts live in the **repository** `bin/` directory. Run from project root.

| Script | Purpose |
|--------|---------|
| `bin/splunk_config_aws.py` | AWS discovery: `--latest-ami --os rhel|ubuntu|amazon_linux|debian|all` (dynamic lookup), `--survey`, `--validate` |
| `bin/splunk_config_licenses.py` | Scan `../Software` for `.lic` files; propose `splunk_license_file` (ITSI-aware with `--config`) |
| `bin/validate_splunk_config.sh` | Schema + inventory + playbook syntax-check; optional `--check-licenses` |

Do not duplicate logic in this skill folder. See [references/aws-baseline.md](../references/aws-baseline.md) and [references/validation.md](../references/validation.md).

## SPA skill naming

Project Cursor skills use the **`spa-`** prefix (folder name = `name` in SKILL.md frontmatter) so they are easy to invoke with `/spa-create-config`, `/spa-add-test-scenario`, etc.

## Dependencies

- `boto3` for `splunk_config_aws.py` (`pip install boto3`)
- `PyYAML` for `splunk_config_licenses.py` with `--config` (`pip install PyYAML`)
- AWS credentials for API discovery/validate
- Ansible + project venv for `validate_splunk_config.sh` (uses `tests/run_venv.sh` pattern)
