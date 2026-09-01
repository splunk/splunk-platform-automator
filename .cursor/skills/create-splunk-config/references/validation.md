# Validation before deploy

Run from **repository root** after writing `config/splunk_config.yml`.

## Primary script

```bash
./bin/validate_splunk_config.sh [path/to/splunk_config.yml]
```

Default path: `config/splunk_config.yml`.

### What it runs

1. **Pydantic schema** — `ansible/plugins/inventory/schema.py` `validate_config_file`
2. **Inventory plugin** — `ansible-inventory --list` with config as inventory source
3. **Playbook syntax** — `ansible-playbook --syntax-check` on provision and deploy playbooks

### Optional AWS validation

When credentials are available:

```bash
./bin/validate_splunk_config.sh --splunk-config-aws config/splunk_config.yml
```

Parses `terraform.aws` from the YAML and runs `bin/splunk_config_aws.py --validate`.

Or directly:

```bash
python3 bin/splunk_config_aws.py --region eu-central-1 --validate \
  --ami-id ami-xxx --key-name aws_key --security-groups Splunk_Basic \
  --instance-type t3.medium --json
```

## Schema tests (no AWS required)

```bash
./tests/run_schema_tests.sh -q
```

## Quality gate

Do not hand off to user provision until:

- [ ] `validate_splunk_config.sh` exits 0
- [ ] No schema errors from inventory plugin
- [ ] Playbook syntax-check passes

## User deploy (skill does not run these)

```bash
ap ansible/provision_terraform_aws.yml -e auto_approve=true
ap ansible/deploy_site.yml
```

Destroy:

```bash
ap ansible/destroy_terraform_aws.yml -e auto_approve=true
```

## Common failures

| Error | Fix |
|-------|-----|
| `license_manager` without `splunk_license_file` | Add license file or remove LM role |
| CM without `idxcluster:` | Add `idxcluster` on CM host |
| Deployer without `shcluster:` | Add `shcluster` on deployer host |
| Multisite without `site:` | Add `site` on CM and indexers |
| Missing `ssh_username` | Set in `terraform.aws` per [aws-os-matrix.md](aws-os-matrix.md) |
