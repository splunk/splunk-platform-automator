# AWS

SPA provisions EC2 infrastructure with Terraform while keeping `config/splunk_config.yml` as the source of truth. Operators use `spa`; do not edit generated tfvars, apply Terraform directly, or maintain a second inventory.

## Discover and configure

AWS credentials come from the normal AWS credential chain or vault/env references in config. Never commit or print access keys. Check authentication and inspect live regional values with:

```bash
spa aws --check-auth --json
spa aws --survey --region REGION --json
spa features show provider.aws --keys
```

Configure `terraform.aws` with a region, AMI, EC2 key pair, SSH user/key, security groups, and defaults such as instance type and root volume. Per-host `terraform.aws` overrides global defaults. `iter` can generate numbered hosts. Terraform modules remain in `SPA_HOME`; generated variables and state remain in `SPA_ENV_DIR`.

AMI IDs, instance offerings, and subnets are regional and change over time, so this guide does not hardcode a catalog. Typical SSH users are `ec2-user` for Amazon Linux/RHEL-family images and `ubuntu` for Ubuntu; verify the publisher's AMI documentation.

The selected image needs Python and OS packages required by Ansible/Splunk. Ubuntu environments commonly need `acl` and `policykit-1`; premium applications can add requirements such as the supported Java version. Use `os.remote_command` only for deterministic pre-deploy bootstrapping: a failure stops provisioning.

## Network prerequisites

Security groups and EC2 key pairs must already exist in the selected region. SPA does not create security groups yet; that is [ROADMAP #58](../ROADMAP.md) (shared network access groups). Until then, create a group such as `Splunk_Basic` and name it in `terraform.aws.security_group_names`.

### Example Basic AWS Security Group `Splunk_Basic`

Inbound:

| Type | Protocol | Port range | Source | Description |
| --- | --- | --- | --- | --- |
| All TCP | TCP | 0–65535 | 172.31.0.0/16 | Internal traffic in the default VPC CIDR |
| Custom TCP | TCP | 8000 | 0.0.0.0/0 | Splunk Web |
| SSH | TCP | 22 | 0.0.0.0/0 | SSH |

Outbound:

| Type | Protocol | Port range | Destination | Description |
| --- | --- | --- | --- | --- |
| All traffic | All | All | 0.0.0.0/0 | Allow all traffic |

The `0.0.0.0/0` sources are a lab-style starting point. Tighten SSH and Splunk Web to trusted networks before production. Internal Splunk management, forwarding, replication, search, and deployment traffic is covered by the all-TCP VPC rule; follow Splunk's network-port reference if you split groups later.

## Provision and deploy

```bash
spa validate
spa provision --yes
spa deploy --yes
```

Provision generates vars, initializes Terraform, shows the plan, applies it, waits for AWS status checks, and writes inventory. For plan-only inspection:

```bash
spa provision --yes -- --tags plan
```

Maintainer stages exposed by the wrapped playbook include `generate`, `init`, `plan`, and `outputs`; inspect current support with `spa provision --help`. Optional readiness checks:

```bash
spa run aws_wait_hosts --help
```

`aws_wait_hosts` adds connectivity, Python, uptime, and cloud-init checks after AWS status checks. Provision can also perform a quick SSH verification via its documented extra vars.

## Operate the environment

| Job | Command |
| --- | --- |
| Inspect AWS-backed host status | `spa hosts list --status` |
| Stop instances, retain state/disks | `spa suspend --yes` |
| Start and refresh inventory addresses | `spa resume --yes` |
| Reconcile Splunk after resume/change | `spa deploy --yes` |
| Remove Terraform-managed resources | `spa destroy --yes` |

Do not remove a live host from `splunk_config.yml` and provision: Terraform may interpret that as permission to terminate it. Review the plan and use the dedicated destroy workflow.

## From vagrant-aws

vagrant-aws is removed in 3.0. A top-level `aws:` block is only legacy inventory data, not a provider. Move cloud settings to `terraform.aws`, migrate the environment with `spa init`, validate, and review a Terraform plan before managing existing resources. See [Migrate](migrate.md).

## Maintainers

The module implementation is under [`terraform/aws/`](../terraform/aws/). Its README describes module files and outputs; operator behavior belongs here and in `spa provision --help`.
