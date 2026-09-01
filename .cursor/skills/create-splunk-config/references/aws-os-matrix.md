# Linux OS and SSH matrix for AWS

**Linux only** for this skill. Always set `terraform.aws.ssh_username` explicitly.

## Supported lab OS choices

| OS | `ssh_username` | Example AMI comment (eu-central-1) | Global `os:` block |
|----|----------------|-------------------------------------|-------------------|
| RHEL 10 | `ec2-user` | `ami-0f5fb818aeff8f5fb` (`examples/single_node_itsi.yml`) | `set_hostname: true`; `packages: [acl]`; `disable_selinux: true` |
| RHEL 9 | `ec2-user` | `ami-03cbad7144aeda3eb` (`defaults/aws.yml`) | Same as RHEL 10 |
| RHEL 8 | `ec2-user` | `ami-0badcc5b522737046` (`examples/splunk_config_terraform_aws.yml`) | Same pattern |
| Ubuntu | `ubuntu` | User-supplied AMI for region | `disable_apparmor: true`; `packages: [acl]` or `remote_command` for apt acl |

Defaults in `defaults/os.yml`: `disable_selinux: true`, `disable_apparmor: true`.

## RHEL example

```yaml
os:
  set_hostname: true
  packages:
    - acl
  disable_selinux: true
```

## Ubuntu example

```yaml
os:
  set_hostname: true
  disable_apparmor: true
  packages:
    - acl
```

Or use `remote_command: 'sudo apt-get install -y acl'` if package name differs.

## ITSI / Java 21 (search tier hosts only)

**ITSI supports Java 21 maximum.** Do not use Java 22+.

| OS | Package |
|----|---------|
| RHEL 8/9/10 | `java-21-openjdk` |
| Ubuntu | `openjdk-21-jdk` |

Set on host-level `os.packages` under search tier hosts:

```yaml
splunk_hosts:
  - name: sh1
    roles: [search_head]
    os:
      packages:
        - java-21-openjdk
```

## AMI → ssh_username heuristic

`splunk_config_aws.py --describe-ami` suggests username from AMI name:

- Contains `ubuntu` → `ubuntu`
- RHEL, Red Hat, Amazon Linux → `ec2-user`
- Default → `ec2-user` (user confirms)

## Skill rules

- Prefer API discovery for AMI when credentials available
- Do not copy RHEL `acl` onto Ubuntu without checking package availability
- Warn when AMI IDs in examples may be stale
