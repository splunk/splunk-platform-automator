# AWS API unavailable — skill behavior

Use when `splunk_config_aws.py` cannot call AWS (no credentials, no boto3, or network blocked). The guided workflow **still works**; only live discovery and API validation are skipped.

## Detect early (Step 0)

```bash
python3 bin/splunk_config_aws.py --check-auth --json
```

| Result | Meaning | Skill path |
|--------|---------|------------|
| `ok: true` + `account` | Credentials work | Phase 4 **with creds** (`--survey`, `--latest-ami`, optional `--splunk-config-aws`) |
| `ok: false`, error mentions credentials | No AWS creds / expired session | Phase 4 **without creds** (this doc) |
| Exit 2, `boto3 is required` | boto3 not installed | `pip install boto3`; until then, **without creds** path |
| `ok: false`, other API error | Profile/region/permission issue | Fix AWS setup or fall back **without creds** and note in header |

Record in config header comment when API was not used:

```yaml
# AWS API: not available during config build — AMIs from examples; verify before provision
```

## What still works (no AWS API)

| Step | Works without AWS? |
|------|-------------------|
| Phases 0a–3, 5–7 (topology, OS matrix, RF/SF, write YAML) | Yes |
| `bin/splunk_config_licenses.py` | Yes (local `../Software` scan) |
| `./bin/validate_splunk_config.sh` (default) | Yes — schema, inventory, license pairing, playbook syntax |
| `./tests/run_schema_tests.sh` | Yes |
| `splunk_config_aws.py` | **No** (needs boto3 + credentials for all operations except none) |

## What fails or is skipped

| Command | Without credentials |
|---------|---------------------|
| `--check-auth` | `ok: false`, error (e.g. Unable to locate credentials) |
| `--list-regions`, `--survey`, `--latest-ami`, `--validate` | `ok: false` in JSON or non-zero exit |
| `validate_splunk_config.sh --splunk-config-aws` | **Fails** if validate runs and AWS rejects the call — **do not use** without creds |

Provision/deploy (`ap ansible/provision_terraform_aws.yml`) **requires** working AWS credentials at run time — building config offline is fine, but user must configure creds before provision.

## Without-creds Phase 4 workflow

1. **Region** — user states org default (e.g. `eu-central-1`); do not call `--list-regions`.
2. **OS + SSH** — [aws-os-matrix.md](aws-os-matrix.md) templates (`ec2-user` / `ubuntu` / `admin`).
3. **AMI** — copy from closest `examples/*.yml` or [examples/aws_lab_baseline.yml](../../../examples/aws_lab_baseline.yml); add comment `# verify AMI in console or re-run splunk_config_aws.py when creds available`.
4. **Instance type** — lab default `t3.medium` ([aws-baseline.md](aws-baseline.md)).
5. **Key pair / security groups** — user supplies names that exist in their account (cannot list via API).
6. **Local paths** — `ssh_private_key_file`, tags, volume size from baseline.

Do **not** block config completion on missing AWS API. Warn that AMI IDs **expire** and key/SG names are **not verified**.

## Phase 8 without AWS

Required:

```bash
./bin/validate_splunk_config.sh config/splunk_config.yml
```

Optional (no AWS):

```bash
./bin/validate_splunk_config.sh --check-licenses config/splunk_config.yml
```

**Skip** `--splunk-config-aws` until credentials work.

Handoff note: user should run `--check-auth` and `--splunk-config-aws` (or `--validate`) before first provision.

## After credentials become available

```bash
python3 bin/splunk_config_aws.py --check-auth --json
python3 bin/splunk_config_aws.py --survey --region <region> --json
python3 bin/splunk_config_aws.py --region <region> --validate \
  --ami-id <ami> --key-name <key> --security-groups <sg> --instance-type t3.medium --json
```

Update `ami_id`, `ssh_username` (from `--describe-ami` if needed), and re-validate.
