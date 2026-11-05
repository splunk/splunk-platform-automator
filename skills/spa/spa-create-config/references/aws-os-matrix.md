# Linux OS and SSH matrix for AWS

**Linux only** for this skill. Always set `terraform.aws.ssh_username` explicitly.

## Recommended OS choices (pick one)

Use the **latest** AMI in your region (AMIs expire). Discover with `spa aws` or AWS console — do not rely on example AMI IDs without verification.

**SPA preference order:** RHEL → Ubuntu LTS → Amazon Linux → Debian (Debian is least tested).

| Priority | OS | `ssh_username` | Notes |
|----------|-----|----------------|-------|
| 1 | **RHEL** | `ec2-user` | Best tested; recommended default |
| 2 | **Ubuntu LTS** | `ubuntu` | Well supported |
| 3 | **Amazon Linux** | `ec2-user` | Good for AWS-native labs |
| 4 | **Debian** | `admin` | Supported; less tested with SPA playbooks |

Discover latest AMI (no hardcoded versions):

```bash
spa --agent aws latest-ami --region eu-central-1 --os rhel
spa --agent aws latest-ami --region eu-central-1 --os ubuntu
spa --agent aws latest-ami --region eu-central-1 --os amazon_linux
spa --agent aws latest-ami --region eu-central-1 --os debian
spa --agent aws latest-ami --region eu-central-1 --os all
spa --agent aws survey --region eu-central-1
```

| OS | Resolution method |
|----|-------------------|
| RHEL | Highest major version from official Red Hat owner (`309956199498`), latest `CreationDate` image |
| Ubuntu LTS | Highest `*.04` SSM pointer under `/aws/service/canonical/ubuntu/server/` (`stable/current`, amd64, gp3 preferred) |
| Amazon Linux | Highest `al{YYYY}` SSM pointer (`kernel-default-x86_64`) under `/aws/service/ami-amazon-linux-latest/` |
| Debian | Highest major version from Debian Cloud Team owner (`136693071363`), latest `debian-{N}-amd64-*` image |

Defaults in `defaults/os.yml`: `disable_selinux: true`, `disable_apparmor: true`.

## Policykit (polkit) — required for SPA playbooks

Splunk playbooks check for `/usr/bin/pkaction` when `splunk_use_policykit` is true (default). **Ubuntu minimal AMIs often omit policykit** — install it in `os.packages` or set `splunk_defaults.splunk_use_policykit: false`.

| OS family | Package name in `os.packages` |
|-----------|-------------------------------|
| Amazon Linux / RHEL | `polkit` |
| Ubuntu | `policykit-1` |
| Debian | `policykit-1` |

## Amazon Linux 2023 example

```yaml
os:
  set_hostname: true
  packages:
    - acl
    - polkit

terraform:
  aws:
    ssh_username: "ec2-user"
    ami_id: "ami-xxxxxxxx"  # AL2023 (region) — verify via API
```

## RHEL 10 example

```yaml
os:
  set_hostname: true
  packages:
    - acl
    - polkit

terraform:
  aws:
    ssh_username: "ec2-user"
    ami_id: "ami-xxxxxxxx"  # RHEL 10 (region)
```

## Ubuntu 24.04 example

```yaml
os:
  set_hostname: true
  packages:
    - acl
    - policykit-1

terraform:
  aws:
    ssh_username: "ubuntu"
    ami_id: "ami-xxxxxxxx"  # Ubuntu 24.04 LTS (region)
```

## Debian example

```yaml
os:
  set_hostname: true
  packages:
    - acl
    - policykit-1

terraform:
  aws:
    ssh_username: "admin"
    ami_id: "ami-xxxxxxxx"  # Debian (region) — verify via API
```

## ITSI / Java 21 (search tier hosts only)

**ITSI supports Java 21 maximum.** Do not use Java 22+. Set the package on `splunk_hosts[].os.packages` for search/ITSI hosts. Do not add it to the global `os:` block (that would install Java on every host).

| OS | Package |
|----|---------|
| Amazon Linux / RHEL | `java-21-openjdk` |
| Ubuntu / Debian | `openjdk-21-jdk` |

## AMI → ssh_username heuristic

`spa --agent aws describe-ami --region REGION --ami-id AMI_ID` suggests username from AMI name:

- Contains `ubuntu` → `ubuntu`
- Contains `debian` → `admin`
- Amazon Linux, RHEL, Red Hat → `ec2-user`
- Default → `ec2-user` (user confirms)

Custom AMI search (optional): `spa aws amis list --region REGION --name-filter "your-pattern*"`

## Skill rules

- Prefer API discovery when credentials are available
- Include **polkit** (or Ubuntu `policykit-1`) in global `os.packages` for all roles including forwarders
- Author only non-default keys: `os.packages` and `os.set_hostname` if chosen. Do not set `disable_selinux`, `update_hosts_file`, `splunk_user_create`, `splunk_group_create`, or `enable_time_sync_cron` unless the operator asked to change the default. Never `config set os '{whole map}'`; set leaf paths.
- Warn when example AMI IDs may be stale
