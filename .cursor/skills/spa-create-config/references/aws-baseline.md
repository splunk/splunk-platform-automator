# AWS baseline for SPA lab configs

Global `terraform.aws` block applies to all hosts unless overridden per host in `splunk_hosts[].terraform.aws`.

## Lab defaults (config / infra test)

| Setting | Default | Notes |
|---------|---------|-------|
| `instance_type` | `t3.medium` | Config tests; not capacity proof |
| `root_volume_size` | 50 | GB, `gp3` |
| `region` | User/org choice | Discover via `splunk_config_aws.py` |
| `security_group_names` | `Splunk_Basic` | If present in account |
| `key_name` | User key in region | Must exist |
| `ssh_private_key_file` | Controller path | e.g. `~/.ssh/aws_key.pem` |
| `tags.SPADirName` | `{{ playbook_dir | dirname | basename }}` | SPA repo folder name on controller (cost/ownership tagging) |

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
      SPADirName: "{{ playbook_dir | dirname | basename }}"
      splunkit_data_classification: "public"
      splunkit_environment_type: "non-prd"
```

## `splunk_config_aws.py` usage

From repo root (requires `boto3` and AWS credentials):

```bash
python3 bin/splunk_config_aws.py --list-regions --json
python3 bin/splunk_config_aws.py --region eu-central-1 --latest-ami --os all --json
python3 bin/splunk_config_aws.py --region eu-central-1 --list-instance-types --family t3 --json
python3 bin/splunk_config_aws.py --region eu-central-1 --list-key-pairs --json
python3 bin/splunk_config_aws.py --region eu-central-1 --list-security-groups --json
python3 bin/splunk_config_aws.py --region eu-central-1 --describe-ami --ami-id ami-xxx --json
python3 bin/splunk_config_aws.py --region eu-central-1 --validate \
  --ami-id ami-xxx --key-name aws_key --security-groups Splunk_Basic --instance-type t3.medium --json
python3 bin/splunk_config_aws.py --survey --region eu-central-1 --json
```

## Prerequisites checklist

- AWS credentials (env or profile)
- Key pair exists in target region
- Security group allows SSH (and Splunk ports as needed)
- SSH private key on Ansible controller
- AMI valid in target region (AMIs expire — prefer API discovery)

## Static fallback

If credentials unavailable, use [aws-os-matrix.md](aws-os-matrix.md) and example AMIs in `defaults/aws.yml` / `examples/single_node_itsi.yml` with **verify in AWS console** warning.
