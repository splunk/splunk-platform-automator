# Splunk Config Guided Setup

Human-readable guide for building `config/splunk_config.yml` on **AWS Linux** with Splunk Platform Automator (SPA).

For interactive agent assistance in Cursor, use the project skill at [skills/spa/spa-create-config](../skills/spa/spa-create-config/) (Cursor discovers it via `.cursor/skills/` symlink; invoke with `/spa-create-config`). See [Agent Skills](Agent_Skills.md) for other tools.

## Quick path

**Separate environment directory (recommended):** from the clone, `spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env`, then `cd ~/envs/my-env` (direnv or `eval "$(spa env --export)"`). Then `spa validate && spa provision --yes && spa deploy`. See [README — Start here](../README.md#start-here).

**Clone-equal:**

1. Copy [examples/aws_lab_baseline.yml](../examples/aws_lab_baseline.yml) or start from [examples/splunk_config_terraform_aws.yml](../examples/splunk_config_terraform_aws.yml) to `config/splunk_config.yml`.
2. Add topology from an SVA-aligned example (e.g. [examples/4idxc2site_sh.yml](../examples/4idxc2site_sh.yml) for multisite IDXC + SH).
3. Set **`terraform.aws.ssh_username`** to match your AMI (`ec2-user` for Amazon Linux / RHEL; `ubuntu` for Ubuntu).
4. Set global **`os:`** block per OS — include **polkit** (`policykit-1` on Ubuntu). See [OS and SSH matrix](#os-and-ssh-matrix) below.
5. Validate before provision:

```bash
spa validate config/splunk_config.yml
```

6. Provision and deploy:

```bash
spa provision --yes && spa deploy
```

`deploy_site.yml` runs `preflight_deploy.yml` first. It probes each host for `python3`, flushes stale Ansible fact cache when the cached interpreter no longer matches (for example after switching OS/AMI while reusing hostnames like `cm` and `idx1`), and verifies Ansible connectivity before the main deploy. Terraform provisioning also flushes cache for affected hosts when inventory is regenerated.

To skip preflight: `ap ansible/deploy_site.yml --skip-tags preflight`. To disable cache flush on provision: `-e spa_flush_fact_cache_on_provision=false`.

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

**Recommended (latest in region):** Amazon Linux 2023, RHEL 10, or Ubuntu 24.04 LTS. Discover AMIs with `spa aws` — example IDs expire.

| OS | `ssh_username` | Global `os.packages` (required) |
|----|----------------|-------------------------------|
| Amazon Linux 2023 | `ec2-user` | `acl`, `polkit`; `disable_selinux: true` |
| RHEL 10 | `ec2-user` | `acl`, `polkit`; `disable_selinux: true` |
| Ubuntu 24.04 | `ubuntu` | `acl`, **`policykit-1`**; `disable_apparmor: true` |

SPA checks for policykit (`pkaction`) by default. **Ubuntu images often lack it** — without `policykit-1`, deploy fails on forwarders and other hosts with:

`Policykit (polkit) is not installed. Install the policykit package or set splunk_use_policykit to false.`

**ITSI:** `java-21-openjdk` (AL/RHEL) or `openjdk-21-jdk` (Ubuntu) on search hosts — not Java 22+.

Discover AMI and SSH hints:

```bash
spa aws --region eu-central-1 --latest-ami --os all --json
spa aws --region eu-central-1 --describe-ami --ami-id ami-xxx --json
```

## Role placement

SVAs favor separated management tiers. Lab configs often co-locate roles on fewer hosts.

| Pattern | Example | SVA note |
|---------|---------|----------|
| CM only | `config/splunk_config.yml` | OK for IDXC config tests |
| CM + MC + DS + deployer | `tests/configs/2site-idxc_shc_mc_ds_sh_hf_uf.yml` | Closer to production |
| All-in-one | `examples/single_node.yml` | S1 only |

Hard rules: `cluster_manager` needs `idxcluster:`; `deployer` needs `shcluster:`; `license_manager` needs `splunk_license_file`.

## License files

Place license files on the Ansible controller in `../Software` (SPA `splunk_software_dir`). Reference **basename only** in config:

```yaml
splunk_defaults:
  splunk_license_file: Splunk_Enterprise.lic
```

For ITSI, use both enterprise and ITSI licenses when available:

```yaml
splunk_defaults:
  splunk_license_file:
    - Splunk_Enterprise.lic
    - Splunk_ITSI.lic
```

Discover and propose licenses from Software:

```bash
spa licenses --json
spa licenses --config config/splunk_config.yml --json
```

Lab configs: add licenses when files exist (avoids trial limits). ITSI in `splunk_app_deployment` requires `license_manager` role and `Splunk_ITSI.lic` when deploying ITSI.

## Basic apps

See [App Deployment](App_Deployment.md). Set `SPLUNKBASE_USERNAME` and `SPLUNKBASE_PASSWORD` on the controller (never paste values into chat or echo them in the terminal).

ITSI example: [examples/single_node_itsi.yml](examples/single_node_itsi.yml).

## Validation

| Check | Command |
|-------|---------|
| Schema + inventory + playbooks | `spa validate config/splunk_config.yml` |
| + Software license scan (optional) | `spa validate --check-licenses config/splunk_config.yml` |
| + AWS API (optional) | `spa validate --splunk-config-aws config/splunk_config.yml` |
| Schema unit tests | `./tests/run_schema_tests.sh -q` |

**Playbook syntax-check** requires Ansible collections (`requirements.yml` and `ansible.windows`). Install with:

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection install ansible.windows
```

## Related docs

- [Ansible-Terraform AWS Integration](Ansible_Terraform_AWS_Integration.md)
- [App Deployment Guide](App_Deployment_Guide.md)
- Agent skill: [skills/spa/spa-create-config/SKILL.md](../skills/spa/spa-create-config/SKILL.md) (Cursor: `/spa-create-config` via `.cursor/skills/` symlink)

## Destroy

```bash
ap ansible/destroy_terraform_aws.yml -e auto_approve=true
```
