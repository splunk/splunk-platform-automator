# spa roadmap

Future work for reproducible Splunk Enterprise labs — a shared framework prefix, agent-ready `spa` CLI, Terraform AWS and [Splunk Operator for Kubernetes](https://github.com/splunk/splunk-operator), without a full repo checkout per lab.

Shipped work stays checked. Git clone remains the contributor path. Splunk installers, licenses, and Professional Services baseconfig apps stay out of band (`Software/` path in config). vagrant-aws is legacy (replaced by Terraform AWS) and is not listed here.

## Distribution

Install the **shared** framework once (playbooks, Terraform, skills, `spa` binary). `spa init` writes **config only** for that environment. Controllers should feel the same on macOS and Linux: install the prefix, then `spa init` / `spa deploy` — no per-env git clone.

**Contract:** `SPA_HOME` is the framework (`ansible/`, Terraform modules, `skills/`, `bin/`). `SPA_ENV_DIR` is the Splunk environment (`splunk_config.yml`, optional `.spa.yml`, `inventory/hosts`, Terraform state, `saved_base_config_apps/`). Unset both → the git clone; today's `ansible-playbook` workflow is unchanged. When they differ, do not write env state into the prefix (an upgrade of `~/.local/spa` or `/opt/spa` would lose it).

Ship M1–M3 on one integration branch, then **3.0** when M3 is in. Do not cut a minor per milestone. Pickup: the issue for that milestone (not a Cursor plan). After a milestone is done: check it here, close the issue, merge into the parent branch for further testing. Do not start the next until the prior is merged there.

**Branching:** parent `distribution` (off `main`). Each milestone is `dist/mN` branched from `distribution` and merged back. When M3 is in, PR `distribution` → `main` and tag **3.0**. Clone + `ansible-playbook` stay supported on `main` until then.

- [x] **M1** Path contract + env scaffold — [#46](https://github.com/splunk/splunk-platform-automator/issues/46)
- [x] **M2** `spa` CLI over the clone prefix — [#47](https://github.com/splunk/splunk-platform-automator/issues/47)
- [ ] **M3** `install.sh` + framework tarball — [#48](https://github.com/splunk/splunk-platform-automator/issues/48)

### Outcomes

- [x] Semver GitHub Releases from [CHANGELOG.md](CHANGELOG.md) ([RELEASE.md](RELEASE.md))
- [x] `SPA_HOME` / `SPA_ENV_DIR` path contract; clone defaults keep today's layout (**M1**)
- [x] `spa init` scaffolds an env dir (example config, `.spa.yml`; no copy of `ansible/`) and migrates an existing clone env (config, inventory, Terraform state) (**M1** / **M2**)
- [x] Separate env dirs against one clone `SPA_HOME` (**M1**)
- [x] `bin/spa_venv.sh` shared venv (framework, envs, tests) + env `.envrc` for direnv; no Homebrew Ansible/Pydantic requirement (**M1**)
- [x] `spa` commands use the shared prefix (`init`, `validate`, `provision`, `deploy`, `suspend`, `resume`, `destroy`, `hosts`, `shell`, `run`, `aws`, `licenses`) (**M2**)
- [x] `spa run --list` / `NAME --help` from `# spa-run:` metadata; 3.0 operator stems (2.x names still resolve with a hint) (**M2**)
- [x] `--hosts` on `deploy`, `run`, `suspend`, `resume`, and `hosts list` (inventory names or roles) (**M2**)
- [x] Mutating ops confirm in `LocalSpaSession` (named human prompt; agents/GUI pass `--yes` and never `input()`) (**M2**)
- [x] `spa suspend` / `spa resume` for AWS compute (keep Terraform state and EBS; resume refreshes inventory addresses) (**M2**)
- [ ] Release tarball of the framework (exclude `tests/`, `.git`, lab `config/`) (**M3**)
- [ ] `install.sh` (cup-style `curl | sh` or `gh release download`): default prefix `~/.local/spa`, or `--prefix` / `SPA_PREFIX`; creates the venv; puts `spa` on `PATH` (**M3**)
- [ ] Documented extract-anywhere: unpack the tarball, set `SPA_HOME`, run `spa` from that tree (**M3**)
- [ ] Optional later: native Linux packages (`.deb` / `.rpm`) from the same tarball, unpack to `/opt/spa`; `install.sh` prefers the distro package when it matches
- [ ] Optional later: Homebrew tap of the same tarball (no brew Ansible/Pydantic; `spa_venv` stays the Python path)
- [ ] Optional later: Ansible collection extract of roles/plugins — not the primary install

## Agent platform and CLI

Modeled on [cup](https://github.com/splunk/cup) agent mode (detect agent env, JSON envelope, `agent schema`, `-y`).

- [x] Portable skills under [skills/spa/](skills/spa/) + Cursor `/spa-create-config` ([docs/Agent_Skills.md](docs/Agent_Skills.md))
- [x] Agent-mode `spa`: auto-detect agent env, JSON envelope with `schema_version`, `spa agent schema`, `--agent` / `--no-agent`, `-y` for destructive ops, parse-error JSON
- [x] `spa.api` backend session (`open_session` / `LocalSpaSession`) for the CLI and a future GUI; optional remote daemon later; skills stay on `spa`. See the [controller, GUI, and remote-client architecture contract](docs/Controller_Architecture.md).
- [x] Fold SSH/SCP into `spa hosts` (`list` / `ssh` / `copy`); `spa shell` / `spa sh` remain SSH aliases (no `spa shell -l`)
- [x] Map top-level [ansible/](ansible/) playbooks to `spa run` (and named `provision` / `deploy` / `destroy`) — every playbook is a main entry point; do not require raw `ansible-playbook` for day-to-day use. Discover with `spa run --list`; inspect with `spa run NAME --help`.
- [ ] Main `spa` skill (cup-style `/spa` entry) — [#54](https://github.com/splunk/splunk-platform-automator/issues/54)
- [ ] `spa skills install` / `spa skills remove` (Claude / Cursor / Codex) from `$SPA_HOME/skills/spa/` — [#55](https://github.com/splunk/splunk-platform-automator/issues/55)
- [ ] Skills, agents, and runbooks pack (full operator loop; calls `spa` only) — [#67](https://github.com/splunk/splunk-platform-automator/issues/67). Blocked by [#54](https://github.com/splunk/splunk-platform-automator/issues/54) and [#55](https://github.com/splunk/splunk-platform-automator/issues/55)
- [ ] Splunkbase search / snippet / download / write `splunk_config.yml` (CLI + app-management skill; never display Splunkbase passwords — [secrets-handling.md](skills/spa/spa-create-config/references/secrets-handling.md)) — [#59](https://github.com/splunk/splunk-platform-automator/issues/59)
- [ ] Optional [cup](https://github.com/splunk/cup) integration (plugin; spa works without cup; cup uses `spa hosts copy` / `ssh` for file transfer) — [#62](https://github.com/splunk/splunk-platform-automator/issues/62)
- [ ] Single-app deploy/remove, list, optional app groups (from config only) — [#68](https://github.com/splunk/splunk-platform-automator/issues/68). Blocked by [#59](https://github.com/splunk/splunk-platform-automator/issues/59)

## Config and validation

- [x] Pydantic schema + `spa validate` (idxc / role pairing; supersedes a Vagrantfile-only idxc check)
- [x] Host ranges (`iter.numbers: "1..N"`)
- [x] Index definitions including `datatype: metric` (`splunk_indexes`)
- [x] First-login splash disabled ([ansible/roles/splunk_software/tasks/ui_config.yml](ansible/roles/splunk_software/tasks/ui_config.yml))
- [ ] Per-host / multi-group `splunk_outputs` in the inventory plugin (today hardcoded `all`; DS can already stage multiple output apps)
- [ ] Optional CM deployment-client toggle (`org_all_deploymentclient` vs `master_deployment_client`)
- [ ] Deploy dry-run / plan (stale-fact preflight already in Unreleased)
- [ ] Documented `splunk_user` (and local VirtualBox SSH user) in `splunk_defaults`
- [ ] Disable remaining UI tours and info wizards after login
- [ ] Feature catalog + provider-independent topology examples; separate provider examples; spa merges on select — [#53](https://github.com/splunk/splunk-platform-automator/issues/53)
- [ ] Certificate add/rotate + SPA vault for certs/keys (closes [#30](https://github.com/splunk/splunk-platform-automator/issues/30)) — [#69](https://github.com/splunk/splunk-platform-automator/issues/69). Blocked by [#52](https://github.com/splunk/splunk-platform-automator/issues/52)
- [ ] Credentials / `spa auth` (profiles, Splunkbase, vault password; macOS Keychain; backwards compatible) — [#52](https://github.com/splunk/splunk-platform-automator/issues/52)

## Docs

- [ ] Slim README + structured user guide + rewrite [AGENTS.md](AGENTS.md) — [#61](https://github.com/splunk/splunk-platform-automator/issues/61)

## Provisioning

- [x] Terraform AWS + `spa aws` ([docs/Ansible_Terraform_AWS_Integration.md](docs/Ansible_Terraform_AWS_Integration.md))
- [ ] VirtualBox spa provider (`spa provision` / `destroy` / suspend-resume via Vagrant); remove unmaintained vagrant-aws — [#56](https://github.com/splunk/splunk-platform-automator/issues/56)
- [ ] Shared network access groups (provider-agnostic CLI; AWS first; SPA_HOME state; env destroy does not delete) — [#58](https://github.com/splunk/splunk-platform-automator/issues/58)
- [ ] External / BYO SSH hosts (register only; mixed with managed; never terminate the real machine) — [#57](https://github.com/splunk/splunk-platform-automator/issues/57)
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
- [ ] `premium_app: es` (Enterprise Security + CIM / TA layout) — [#60](https://github.com/splunk/splunk-platform-automator/issues/60)
- [ ] More curated app playbooks (TA-nix exists under `ansible/apps_playbooks/`)

## Lifecycle

- [x] Manual upgrade playbooks, including rolling IDXC and SHC (`ansible/upgrade_splunk*.yml`)
- [ ] Include Windows UF in the upgrade host set
- [ ] Config-driven version bump (`splunk_version` change → rolling upgrade) — same runbook-vs-playbook choice as the upgrade skill
- [ ] Remove a host: `spa destroy --hosts NAME` runs decommission (IDXC peer / SHC member, DS serverclass), then tears down only those instances and drops them from config/state. `spa destroy --all` is whole-env teardown. Omitting both `--hosts` and `--all` is an error (do not treat “no hosts” as destroy-everything). No separate `decommission` command. Until this exists, `spa destroy --yes` remains whole-env.
- [ ] `spa provision` must abort if the Terraform plan would **destroy or replace** an instance (host removed from `splunk_config.yml`, or AMI / instance-type replacement). Tell the operator to restore the host or use `spa destroy --hosts`. Creates and in-place updates still apply. Today, deleting a host from config and running provision **terminates that VM** with no Splunk decommission.
- [ ] Cluster topology changes on a live site (RF/SF, add a site, move a host between clusters) — not just re-run bootstrap
- [ ] Git for env configs and local apps; pluggable SCM/CI (GitHub first); promote along user-named stages — [#63](https://github.com/splunk/splunk-platform-automator/issues/63)
- [ ] Baseconfig: render/generate locally or standalone (no env) + placement markdown/JSON; ship via app deployment when using SPA (replaces optional public baseconfig-substitute download) — [#64](https://github.com/splunk/splunk-platform-automator/issues/64)
- [ ] Splunk binary/version management (download to Software or register remote; AWS stub/touch) — [#65](https://github.com/splunk/splunk-platform-automator/issues/65)
- [ ] `spa licenses add` + canonical NFR symlink in Software — [#66](https://github.com/splunk/splunk-platform-automator/issues/66)

## Testing

- [x] Local pytest + GitHub Actions CI ([tests/README.md](tests/README.md))
- [ ] Broader schema / example sweep
- [ ] Optional nightly AWS job — not required on every PR
