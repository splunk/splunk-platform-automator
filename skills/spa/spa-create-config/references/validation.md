# Validation before deploy

Run from **repository root** after writing `config/splunk_config.yml`.

## Primary script

```bash
spa validate [path/to/splunk_config.yml]
```

Default path: `config/splunk_config.yml`.

### What it runs

1. **Pydantic schema** — `ansible/plugins/inventory/schema.py` `validate_config_file`
2. **Inventory plugin** — `ansible-inventory --list` with config as inventory source
3. **License / role pairing** — `splunk_license_file` requires `license_manager` role (and vice versa); ITSI requires LM
4. **Playbook syntax** — included in `spa validate` (`--syntax-check` on provision and deploy)

### Optional license content and entitlement check

Parses configured licenses from `../Software` and fails when a file is missing,
invalid XML, expired, or lacks an Enterprise / ITSI / ES capability required by
the selected apps. It warns when expiration is within 30 days or cannot be
determined:

```bash
spa validate --check-licenses config/splunk_config.yml
```

Or directly:

```bash
spa licenses --config config/splunk_config.yml --json
```

### Optional AWS validation

When credentials are available:

```bash
spa validate --splunk-config-aws config/splunk_config.yml
```

Parses `terraform.aws` from the YAML and runs `spa aws --validate`.

Or directly:

```bash
spa aws --region eu-central-1 --validate \
  --ami-id ami-xxx --key-name aws_key --security-groups Splunk_Basic \
  --instance-type t3.medium --json
```

## Schema tests (no AWS required)

```bash
./tests/run_schema_tests.sh -q
```

## Quality gate

Do not hand off to user provision until:

- [ ] `spa validate` exits 0
- [ ] `spa validate --check-licenses` exits 0 when licenses are configured
- [ ] No schema errors from inventory plugin
- [ ] Playbook syntax-check passes

## User deploy (skill does not run these)

```bash
spa provision --yes && spa deploy --yes
```

Destroy:

```bash
spa destroy --yes
```

## Common failures

| Error | Fix |
|-------|-----|
| `license_manager` without `splunk_license_file` | Add license file or remove LM role |
| `splunk_license_file` without `license_manager` | Add `license_manager` to a host (e.g. on `cm`) or remove license file for trial labs |
| License invalid, expired, or wrong entitlement | Use `spa licenses --config config/splunk_config.yml --json`; choose the proposed non-expired files that satisfy all required capabilities |
| CM without `idxcluster:` | Add `idxcluster` on CM host |
| Deployer without `shcluster:` | Add `shcluster` on deployer host |
| Multisite without `site:` | Add `site` on CM and indexers |
| Missing `ssh_username` | Set in `terraform.aws` per [aws-os-matrix.md](aws-os-matrix.md) |
| AWS validate fails / no creds | Use default `spa validate` only; see [aws-without-credentials.md](aws-without-credentials.md) |
| Policykit not installed (Ubuntu UF) | Add `policykit-1` to global `os.packages` or set `splunk_use_policykit: false` |
