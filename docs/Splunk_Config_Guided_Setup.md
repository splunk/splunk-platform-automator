# Splunk Config Guided Setup

Human-readable guide for building `config/splunk_config.yml` on **AWS Linux** with Splunk Platform Automator (SPA).

For interactive agent assistance in Cursor, use the project skill: `.cursor/skills/create-splunk-config/`.

## Quick path

1. Copy [examples/aws_lab_baseline.yml](examples/aws_lab_baseline.yml) or start from [examples/splunk_config_terraform_aws.yml](examples/splunk_config_terraform_aws.yml).
2. Add topology from an SVA-aligned example (e.g. [examples/4idxc2site_sh.yml](examples/4idxc2site_sh.yml) for multisite IDXC + SH).
3. Set **`terraform.aws.ssh_username`** to match your AMI (`ec2-user` for RHEL; `ubuntu` for Ubuntu).
4. Set global **`os:`** block per OS — see [OS and SSH matrix](#os-and-ssh-matrix) below.
5. Validate before provision:

```bash
./bin/validate_splunk_config.sh config/splunk_config.yml
```

6. Provision and deploy:

```bash
ap ansible/provision_terraform_aws.yml -e auto_approve=true
ap ansible/deploy_site.yml
```

## Architecture design references

- [About Splunk Validated Architectures](https://help.splunk.com/en/splunk-cloud-platform/splunk-validated-architectures/introduction-to-splunk-validated-architectures/about-splunk-validated-architectures)
- [Topology selection guidance](https://help.splunk.com/en/splunk-enterprise/get-started/splunk-validated-architectures/splunk-platform-indexing-and-search)
- [Designing a scalable architecture](https://lantern.splunk.com/Splunk_Success_Framework/Mitigate_Risk/Guarding_against_impact_to_revenue/Designing_a_scalable_architecture) (Lantern)
- [configuration_description.yml](examples/configuration_description.yml) — all config keys

## Deployment intent

| Intent | Typical sizing | Notes |
|--------|----------------|-------|
| Config / infra test | `t3.medium`, 50 GB | Minimal hosts; lab role co-location OK |
| Feature / app lab | Larger SH if needed | ITSI: Java 21 max on search tier |
| Production-like | Document overrides | SVA-aligned separation; multisite |

## OS and SSH matrix

Always set `terraform.aws.ssh_username` explicitly.

| OS | `ssh_username` | Global `os:` |
|----|----------------|--------------|
| RHEL 8/9/10 | `ec2-user` | `set_hostname: true`; `packages: [acl]`; `disable_selinux: true` |
| Ubuntu | `ubuntu` | `set_hostname: true`; `disable_apparmor: true`; `packages: [acl]` |

**ITSI:** use `java-21-openjdk` (RHEL) or `openjdk-21-jdk` (Ubuntu) on search hosts — not Java 22+.

Discover AMI and SSH hints with AWS credentials:

```bash
python3 bin/splunk_config_aws.py --region eu-central-1 --list-amis --name-filter "RHEL*10*" --json
python3 bin/splunk_config_aws.py --region eu-central-1 --describe-ami --ami-id ami-xxx --json
```

## Role placement

SVAs favor separated management tiers. Lab configs often co-locate roles on fewer hosts.

| Pattern | Example | SVA note |
|---------|---------|----------|
| CM only | `config/splunk_config.yml` | OK for IDXC config tests |
| CM + MC + DS + deployer | `tests/configs/2site-idxc_shc_mc_ds_sh_hf_uf.yml` | Closer to production |
| All-in-one | `examples/single_node.yml` | S1 only |

Hard rules: `cluster_manager` needs `idxcluster:`; `deployer` needs `shcluster:`; `license_manager` needs `splunk_license_file`.

## Basic apps

See [App Deployment](App_Deployment.md). Use env vars `SPLUNKBASE_USERNAME` and `SPLUNKBASE_PASSWORD`.

ITSI example: [examples/single_node_itsi.yml](examples/single_node_itsi.yml).

## Validation

| Check | Command |
|-------|---------|
| Schema + inventory + playbooks | `./bin/validate_splunk_config.sh config/splunk_config.yml` |
| + AWS API (optional) | `./bin/validate_splunk_config.sh --splunk-config-aws config/splunk_config.yml` |
| Schema unit tests | `./tests/run_schema_tests.sh -q` |

**Playbook syntax-check** requires Ansible collections (`requirements.yml` and `ansible.windows`). Install with:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection install ansible.windows
```

## Related docs

- [Ansible-Terraform AWS Integration](Ansible_Terraform_AWS_Integration.md)
- [App Deployment Guide](App_Deployment_Guide.md)
- Cursor skill: `.cursor/skills/create-splunk-config/SKILL.md`

## Destroy

```bash
ap ansible/destroy_terraform_aws.yml -e auto_approve=true
```
