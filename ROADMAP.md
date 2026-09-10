# spa roadmap

Future work for reproducible Splunk Enterprise labs — shared Homebrew install, agent-ready `spa` CLI, Terraform AWS and [Splunk Operator for Kubernetes](https://github.com/splunk/splunk-operator), without a full repo checkout per lab.

Shipped work stays checked. Git clone remains the contributor path. Splunk installers, licenses, and Professional Services baseconfig apps stay out of band (`Software/` path in config). vagrant-aws is legacy (replaced by Terraform AWS) and is not listed here.

## Distribution

Homebrew installs the **shared** framework once (playbooks, Terraform, skills, `spa` binary). `spa init` writes **config only** for that lab. Linux should feel the same: install the prefix, then `spa init` / `spa deploy` — no per-lab git clone.

**Contract:** `SPA_HOME` is the framework (`ansible/`, Terraform modules, `skills/`, `bin/`). `SPA_LAB_DIR` is the lab (`splunk_config.yml`, optional `.spa.yml`, `inventory/hosts`, Terraform state). Unset both → the git clone; today's `ansible-playbook` workflow is unchanged. When they differ, do not write lab state into the prefix (Homebrew / `/opt/spa` would lose it on upgrade).

Ship as **four minors**, in order. Pickup: the issue for that milestone (not a Cursor plan). After a milestone ships: check it here, close the issue, CHANGELOG, cut the minor. Do not start the next until the prior is in a released tag.

- [ ] **M1** Path contract + lab scaffold — [#46](https://github.com/splunk/splunk-platform-automator/issues/46)
- [ ] **M2** `spa` CLI over the clone prefix — [#47](https://github.com/splunk/splunk-platform-automator/issues/47)
- [ ] **M3** Homebrew tap + framework tarball — [#48](https://github.com/splunk/splunk-platform-automator/issues/48)
- [ ] **M4** Native Linux packages + `curl | sh` — [#49](https://github.com/splunk/splunk-platform-automator/issues/49)

### Outcomes

- [x] Semver GitHub Releases from [CHANGELOG.md](CHANGELOG.md) ([RELEASE.md](RELEASE.md))
- [ ] `SPA_HOME` / `SPA_LAB_DIR` path contract; clone defaults keep today's layout (**M1**)
- [ ] `bin/init_lab_dir.sh` scaffolds a lab dir (example config, `.spa.yml`; no copy of `ansible/`) (**M1**); `spa init` wraps it (**M2**)
- [ ] Separate lab dirs against one clone `SPA_HOME` (**M1**)
- [ ] `spa` commands use the shared prefix (`init`, `validate`, `provision`, `deploy`, `destroy`, `shell`, and the rest of the playbook surface) (**M2**)
- [ ] Homebrew tap (`splunk/tap`) on **macOS and Linux**: shared prefix + `spa` binary (depends on ansible, terraform, python, pydantic). Same formula; [Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux) is the primary Linux path (**M3**)
- [ ] Native Linux packages from the same release tarball as the brew formula: `.deb` (apt), `.rpm` (dnf/yum), and a tarball into `/opt/spa` with `spa` on `PATH` (**M4**)
- [ ] Optional `curl | sh` installer that uses the brew formula when Homebrew is present, otherwise the Linux tarball (**M4**)
- [ ] Optional later: Ansible collection extract of roles/plugins — not the primary install

## Agent platform and CLI

Modeled on [cup](https://github.com/splunk/cup) agent mode (detect agent env, JSON envelope, `agent schema`, `-y`).

- [x] Portable skills under [skills/spa/](skills/spa/) + Cursor `/spa-create-config` ([docs/Agent_Skills.md](docs/Agent_Skills.md))
- [ ] Agent-mode `spa`: auto-detect agent env, JSON envelope, `spa agent schema`, `--agent` / `--no-agent`, `-y` for destructive ops, parse-error hints
- [ ] Fold [bin/spash](bin/spash) into `spa shell` (SSH, `-l` host list, `-c` copy) — keep `spash` as a thin alias at most
- [ ] Map top-level [ansible/](ansible/) playbooks to `spa` subcommands (deploy, apps, upgrade, restart, license, certs, …) — every playbook is a main entry point; do not require raw `ansible-playbook` for day-to-day use
- [ ] `spa skills install` (Claude / Cursor / Codex) from the shared prefix
- [ ] `spa apps search` / `spa apps snippet`: search Splunkbase and print a copy-paste `splunk_app_deployment` app entry (`name`, `app_id`, `version`, `source`)
- [ ] Skill for Splunkbase search → YAML snippet (calls the same CLI; never display Splunkbase passwords — [secrets-handling.md](skills/spa/spa-create-config/references/secrets-handling.md))
- [ ] Skills for destroy, add-app, and post-deploy health
- [ ] Upgrade via a runbook **or** keep the existing hardcoded playbooks (`upgrade_splunk*.yml`) behind `spa upgrade` — decide when implementing, not both unless a runbook only orchestrates those playbooks
- [ ] Optional [cup](https://github.com/splunk/cup) profile after deploy for search / ITSI checks

## Config and validation

- [x] Pydantic schema + [bin/validate_splunk_config.sh](bin/validate_splunk_config.sh) (idxc / role pairing; supersedes a Vagrantfile-only idxc check)
- [x] Host ranges (`iter.numbers: "1..N"`)
- [x] Index definitions including `datatype: metric` (`splunk_indexes`)
- [x] First-login splash disabled ([ansible/roles/splunk_software/tasks/ui_config.yml](ansible/roles/splunk_software/tasks/ui_config.yml))
- [ ] Per-host / multi-group `splunk_outputs` in the inventory plugin (today hardcoded `all`; DS can already stage multiple output apps)
- [ ] Optional CM deployment-client toggle (`org_all_deploymentclient` vs `master_deployment_client`)
- [ ] Deploy dry-run / plan (stale-fact preflight already in Unreleased)
- [ ] Documented `splunk_user` (and local VirtualBox SSH user) in `splunk_defaults`
- [ ] Disable remaining UI tours and info wizards after login

## Provisioning

- [x] Terraform AWS + [bin/splunk_config_aws.py](bin/splunk_config_aws.py) ([docs/Ansible_Terraform_AWS_Integration.md](docs/Ansible_Terraform_AWS_Integration.md))
- [ ] Splunk Operator for Kubernetes: `splunk_config.yml` → Operator CRs (IndexerCluster, SearchHeadCluster, ClusterManager, LicenseManager, MonitoringConsole, Standalone) plus namespace, storage, and image settings
- [ ] Windows Universal Forwarder on AWS (AMI + WinRM); VirtualBox UF role exists but needs an undocumented box ([docs/Setup_Windows_Box.md](docs/Setup_Windows_Box.md))

## Splunk topology

- [x] Cluster manager, indexer cluster, deployer, search head cluster, deployment server, heavy / universal forwarder, license manager, monitoring console
- [x] SmartStore / S2 index path
- [ ] Load balancer in front of SHC (UI / API) and HEC on indexers — AWS NLB/ALB via Terraform; Kubernetes Service `LoadBalancer` / Ingress with the Operator
- [ ] Cluster manager redundancy (manager redundancy / CMHA) in config, Terraform, and Operator
- [ ] UF → heavy forwarder or single-indexer outputs as first-class config
- [ ] Per-tier DS `outputs.conf` / serverclasses (HF vs cluster vs standalone indexer)
- [ ] DNS role or Bind on one node; point lab hosts at it
- [ ] Finish `ldap_server` (add to schema) and wire Splunk `authentication.conf`

## Apps and premium apps

- [x] Generic Splunkbase / local / URL apps + customizations ([docs/App_Deployment.md](docs/App_Deployment.md))
- [x] ITSI premium app + content packs (`premium_app: itsi`)
- [ ] `premium_app: es` (Enterprise Security + CIM / TA layout)
- [ ] More curated app playbooks (TA-nix exists under `ansible/apps_playbooks/`)
- [ ] Optional download of public baseconfig substitutes (Professional Services “Configurations - Base” cannot be shipped)

## Lifecycle

- [x] Manual upgrade playbooks, including rolling IDXC and SHC (`ansible/upgrade_splunk*.yml`)
- [ ] Include Windows UF in the upgrade host set
- [ ] Config-driven version bump (`splunk_version` change → rolling upgrade) — same runbook-vs-playbook choice as the upgrade skill
- [ ] Remove a host from config: decommission IDXC peer / SHC member, drop DS serverclass entries, then destroy the instance (apps already have `state: absent`; hosts do not)
- [ ] Cluster topology changes on a live site (RF/SF, add a site, move a host between clusters) — not just re-run bootstrap

## Testing

- [x] Local pytest + GitHub Actions CI ([tests/README.md](tests/README.md))
- [ ] Broader schema / example sweep
- [ ] Optional nightly AWS job — not required on every PR
