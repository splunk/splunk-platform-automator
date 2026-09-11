# Scripts for spa-create-config

Canonical scripts live in the **repository** `bin/` directory. Run from project root.

| Script | Purpose |
|--------|---------|
| `spa aws` | AWS discovery: `--check-auth`, `--latest-ami`, `--survey`, `--validate` |
| `spa licenses` | Scan `../Software` for `.lic` files; propose `splunk_license_file` (ITSI-aware with `--config`) |
| `spa validate` | Schema + inventory + playbook syntax-check; optional `--check-licenses` |

Do not duplicate logic in this skill folder. See [references/aws-baseline.md](../references/aws-baseline.md) and [references/validation.md](../references/validation.md).

## SPA skill naming

Canonical skills live under `skills/spa/` ([Agent Skills spec](https://agentskills.io/specification.md)). Cursor discovers them via `.cursor/skills/` symlinks. Use the **`spa-`** prefix (`spa-create-config`, `spa-add-test-scenario`) for `/` command names in Cursor.

## Dependencies

- `boto3` for `spa aws` (`pip install boto3`)
- `PyYAML` for `spa licenses` with `--config` (`pip install PyYAML`)
- AWS credentials for API discovery/validate
- Ansible + project venv for `spa validate` (uses `tests/run_venv.sh` pattern)
