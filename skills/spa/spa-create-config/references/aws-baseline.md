# AWS baseline for SPA lab configs

Global `terraform.aws` block applies to all hosts unless overridden per host in `splunk_hosts[].terraform.aws`.

## Lab defaults (config / infra test)

| Setting | Default | Notes |
|---------|---------|-------|
| `instance_type` | `t3.medium` | Config tests; not capacity proof |
| `root_volume_size` | 50 | GB, `gp3` |
| `region` | User/org choice | Discover via `spa aws` |
| `security_group_names` | `Splunk_Basic` | If present in account |
| `key_name` | User key in region | Must exist |
| `ssh_private_key_file` | Controller path | e.g. `~/.ssh/aws_key.pem` |
| `tags.SPADirName` | `{{ spa_env_dir | basename }}` | Env dir folder name |

## Feature / app lab

- Larger SH instance type may be needed (ITSI, ES)
- ITSI: Java 21 on search tier — see [aws-os-matrix.md](aws-os-matrix.md)
- License files in `splunk_defaults.splunk_license_file`

## Production-like lab

- Per-tier overrides only when justified; document cost in header
- Do not auto-size from ingest — PS / capacity planning

## Example global block

Recommended OS: **Amazon Linux 2023**, **RHEL 10**, or **Ubuntu 24.04** (latest AMI in region). Pair with matching `os:` block in [aws-os-matrix.md](aws-os-matrix.md) — include `polkit` / `policykit-1`.

```yaml
terraform:
  aws:
    region: "eu-central-1"
    ami_id: "ami-xxxxxxxx"  # AL2023 | RHEL 10 | Ubuntu 24.04 — verify in console or API
    ssh_username: "ec2-user"  # "ubuntu" for Ubuntu AMIs
    key_name: "aws_key"
    ssh_private_key_file: "~/.ssh/aws_key.pem"
    security_group_names: ["Splunk_Basic"]
    instance_type: "t3.medium"
    root_volume_size: 50
    root_volume_type: "gp3"
    tags:
      Env: "Splunk Lab"
      SPADirName: "{{ spa_env_dir | basename }}"
      splunkit_data_classification: "public"
      splunkit_environment_type: "non-prd"
```

## `spa aws` usage

From repo root (requires `boto3` and AWS credentials):

```bash
spa aws --check-auth --json
spa aws --json regions list
spa aws --region eu-central-1 --latest-ami --os all --json
spa aws --json instance-types list --region eu-central-1 --family t3
spa aws --json key-pairs list --region eu-central-1
spa aws --json security-groups list --region eu-central-1
spa aws --region eu-central-1 --describe-ami --ami-id ami-xxx --json
spa aws --region eu-central-1 --validate \
  --ami-id ami-xxx --key-name aws_key --security-groups Splunk_Basic --instance-type t3.medium --json
spa aws --survey --region eu-central-1 --json
```

`--region` wins. When it is omitted, `spa aws` uses `AWS_REGION`, then `AWS_DEFAULT_REGION`, then `region` in `~/.aws/config` for the active profile. Text output names that source, and `spa aws regions list` marks the region with `selected`. `--json` and `--agent` print only JSON, including `region_source`. `regions list --json` also returns `aws_config_region` and `aws_config_profile` from `~/.aws/config`, even when an environment config sets the region first. Provision and the other lifecycle commands still read `terraform.aws.region` from the environment config.

## Prerequisites checklist

- AWS credentials (env or profile)
- Key pair exists in target region
- Security group allows SSH (and Splunk ports as needed)
- SSH private key on Ansible controller
- AMI valid in target region (AMIs expire — prefer API discovery)

## Static fallback (no AWS API)

If `--check-auth` fails or boto3 is missing, follow [aws-without-credentials.md](aws-without-credentials.md). Inspect `spa --agent config explain provider.aws`, then select it with `spa --agent config provider aws`; use [aws-os-matrix.md](aws-os-matrix.md) for `ssh_username` and `os.packages`. **Verify AMI IDs in the AWS console** before provision, or re-run discovery when credentials are available.
