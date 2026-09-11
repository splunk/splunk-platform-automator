---
description: Deploy Splunk infrastructure to AWS using Terraform
---

# Deploy Splunk Infrastructure to AWS with Terraform

This workflow provisions AWS infrastructure using Terraform and deploys Splunk. Use **only `spa`** from an environment directory (`SPA_ENV_DIR`). Do not call `ansible-playbook` or `python3 bin/…` here.

## Prerequisites

1. **direnv / PATH:** `cd` the env dir so `spa` is on `PATH` (`$SPA_HOME/bin`), or run `$SPA_HOME/bin/spa`.
2. **Host tools:** `spa doctor` (Terraform for AWS). Ansible collections come from `spa_venv` — do not run `ansible-galaxy` in this workflow.
3. **AWS credentials:** `spa aws --check-auth --json`. Report set/not-set only; never print secret values.
4. **Config:** `config/splunk_config.yml` with `terraform.aws` (security group, key pair, AMI in the target region).

## Step 1: Configure Infrastructure

Edit `config/splunk_config.yml` and add/update the `terraform.aws` section (see examples). Discover AMIs and resources with `spa aws --survey --region <region> --json` when credentials work.

## Step 2: Preview Infrastructure Changes

```bash
spa provision -- --tags plan
```

This generates `terraform/aws/terraform.tfvars`, runs `terraform init` / `plan`, and does **not** apply.

## Step 3: Provision Infrastructure

```bash
spa provision
```

Non-interactive (agents / CI): `spa provision --yes && spa deploy`. `--yes` after `provision` auto-approves Terraform apply (`-y` is the short form; `spa -y provision` also works).

This will:

1. Generate Terraform configuration
2. Initialize Terraform
3. Show the plan
4. Prompt for confirmation unless `--yes`
5. Create EC2 instances and `inventory/hosts`
6. Wait for SSH by default

Skip SSH wait: `spa provision -- -e wait_for_ssh=false`.

## Step 4: Verify Host Readiness (optional)

```bash
spa run wait_for_terraform_aws_hosts
```

SSH, Python, uptime, cloud-init. Success text in the playbook may mention deploy; continue with `spa deploy`.

## Step 5: Deploy Splunk

```bash
spa deploy
```

## Step 6: Verify Deployment

Open `$SPA_ENV_DIR/config/index.html`, or:

```bash
spa run create_linkpage
```

SSH: `spa shell <host>` when the host is in inventory.

## Troubleshooting

- `spa doctor` and `spa aws --check-auth --json` first.
- Verbose wait: `spa run wait_for_terraform_aws_hosts -- -v`
- Longer SSH timeout: `spa run wait_for_terraform_aws_hosts -- -e ssh_timeout=600`

## Cleanup

```bash
spa destroy
```

In agent mode, destroy requires `-y` / `--yes`. This permanently deletes EC2 instances.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `spa doctor` | Host prerequisites |
| `spa aws --check-auth --json` | Credential probe (no secret values) |
| `spa provision -- --tags plan` | Preview changes |
| `spa provision --yes && spa deploy` | Provision then deploy (stop if provision fails) |
| `spa provision` / `spa provision --yes` | Provision infrastructure only |
| `spa run wait_for_terraform_aws_hosts` | Verify host readiness |
| `spa deploy` | Deploy Splunk (hosts already provisioned) |
| `spa run create_linkpage` | Host link page |
| `spa destroy` | Destroy infrastructure |
| `spa shell <host>` | SSH via inventory |
| `spa run --list` | Playbook catalog |
