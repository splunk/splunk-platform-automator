# Scripts for spa-create-config

Canonical scripts live in the **repository** `bin/` directory. Run from project root.

| Script | Purpose |
|--------|---------|
| `spa provider aws` | AWS discovery: `check-auth`, `latest-ami`, `survey`, `validate`, `KIND list` (`regions list` and `check-auth` need no region; pass `--region` on the others) |
| `spa licenses list` | Scan Software for `.lic` files; propose `splunk_license_file` (ITSI-aware from the env config) |
| `spa validate` | Schema + inventory + playbook syntax-check; optional `--check-licenses` |
| `spa architecture plan FILE` | Read a confirmed 0.4.0 architecture JSON file (read-only). See [references/architecture-input.md](../references/architecture-input.md). |
| `spa init --architecture FILE --provider` | Scaffold from `sva.code` then overlay counts, RF/SF, and extra roles. Exclusive with `--example`. |
| `spa architecture apply FILE --yes` | Overlay the same deltas onto an existing env. |
| `spa architecture check FILE` | Subset-match the file against the current env (required on path B before validate). |
| `spa config move role` / `move host` | Relocate one role, or rename/prefix/postfix hosts. |

Do not duplicate logic in this skill folder. See [references/aws-baseline.md](../references/aws-baseline.md) and [references/validation.md](../references/validation.md).

## SPA skill naming

Canonical skills live under `skills/spa/` ([Agent Skills spec](https://agentskills.io/specification.md)). Install them with `spa skills install`. Use the **`spa-`** prefix (`spa-create-config`, `spa-apps`) for `/` command names.

## Dependencies

- `boto3` for `spa provider aws` (`pip install boto3`)
- `PyYAML` for `spa licenses list` (`pip install PyYAML`)
- AWS credentials for API discovery/validate
- Ansible + project venv for `spa validate` (uses `tests/run_venv.sh` pattern)
