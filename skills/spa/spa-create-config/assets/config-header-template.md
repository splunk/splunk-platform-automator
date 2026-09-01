# Config header template

Copy into the top of `config/splunk_config.yml` (YAML comments).

```yaml
---
# splunk_config.yml — Splunk Platform Automator
# Intent: config-test | app-lab | production-like
# Requirements: ingest=<band>; users=<band>; use_case=<...>; DR=<none|multisite|...>
# SVA target: <code> (lab compromises: <list gaps>)
# Role placement: <SVA-aligned | lab-minimal | hybrid> — <host summary>
# OS: <RHEL 10 | RHEL 9 | RHEL 8 | Ubuntu>; ssh_username=<ec2-user|ubuntu>
# Deploy: ap ansible/provision_terraform_aws.yml -e auto_approve=true; ap ansible/deploy_site.yml
plugin: splunk-platform-automator
```

Adjust lines to match user choices. Remove unused comment lines rather than leaving placeholders.
