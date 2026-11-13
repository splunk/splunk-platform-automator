<!-- markdownlint-disable MD024 -->
# Splunk Platform Automator changes by release

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/).

## [Unreleased]

Work on this branch is **3.0**. Linux packages and Homebrew are later, not part of 3.0. Operators coming from 2.x start at [docs/migrate.md](docs/migrate.md).

### Added

- **Install and path contract** ([#46](https://github.com/splunk/splunk-platform-automator/issues/46), [#48](https://github.com/splunk/splunk-platform-automator/issues/48), [#72](https://github.com/splunk/splunk-platform-automator/issues/72), [#73](https://github.com/splunk/splunk-platform-automator/issues/73), [#91](https://github.com/splunk/splunk-platform-automator/issues/91)): `SPA_HOME` is the framework; `SPA_ENV_DIR` is one environment. `install.sh` installs a prefix from the framework tarball (GitHub `releases/latest/download/install.sh`); `--uninstall` removes that prefix and launcher only. User-level Software / baseconfig / apps pointers live in `paths.yml` (`spa init --software-dir`, `spa environment set --software-dir`). `spa init` scaffolds an env (example or architecture file, `.spa.yml`, inventory, Terraform state dir) and never copies `ansible/`. `--from` / `--force` migrate a 2.x clone env; `--force` strips leftover framework files from the packaging manifest. Init requires `--provider` unless a default is saved with `spa environment set --provider NAME`.

- **`spa` CLI and agent mode** ([#47](https://github.com/splunk/splunk-platform-automator/issues/47), [#99](https://github.com/splunk/splunk-platform-automator/issues/99), [#105](https://github.com/splunk/splunk-platform-automator/issues/105), [#108](https://github.com/splunk/splunk-platform-automator/issues/108), [#133](https://github.com/splunk/splunk-platform-automator/issues/133)): one operator entry `bin/spa`. Catalogs are `COMMAND list` (a missing action exits 2 and names the legal command). Mutating commands require `--yes` (non-TTY never prompts). `--agent` prints one JSON envelope with `schema_version`; `spa agent schema` is the catalog. Humans see `Next:` from `data.next`. Live SSH/SCP stay text (`spa hosts ssh`, `spa hosts copy`).

- **`spa venv` and environment registry** ([#54](https://github.com/splunk/splunk-platform-automator/issues/54)): `spa venv path|create|reinstall|upgrade|rebuild` manage the shared or `--environment` venv (`--yes`). `spa environment list|init|set|cleanup|remove` (alias `env`; `spa init` aliases `environment init`). `cleanup` drops registry entries whose directory is missing. Commands resolve `--env`, cwd, or the registered default.

- **Transactional config editor** ([#76](https://github.com/splunk/splunk-platform-automator/issues/76), [#86](https://github.com/splunk/splunk-platform-automator/issues/86), [#117](https://github.com/splunk/splunk-platform-automator/issues/117), [#127](https://github.com/splunk/splunk-platform-automator/issues/127)): `spa config` `get` / `set` / `add` / `unset` / `merge` / `move` / `topology` / `provider` / `migrate` / `header`, plus `search` / `explain` / `schema` / `templates list` / `audit`. Writes are schema-aware, planned, and atomic (`--show-diff` for humans; agent JSON includes `data.diff`). Unresolved writes return `ok: false` and write nothing. `splunk_config.yml` stamps SPA-owned `schema_version` (current is 1); `spa deploy` refuses a missing stamp until `spa config migrate --yes`. Generated [docs/config.md](docs/config.md) comes from `spa config schema --markdown`.

- **Topology examples and remote-provider fragment** ([#53](https://github.com/splunk/splunk-platform-automator/issues/53), [#143](https://github.com/splunk/splunk-platform-automator/issues/143)): `spa init --example TOPOLOGY --provider aws|virtualbox|ccm|external` composes topology + provider YAML. For a remote provider, init already merges [examples/templates/remote-provider.yml](examples/templates/remote-provider.yml) (inventory hostname, host-side Splunk download, Splunkbase `target_download`, TLS) and prints `merged: remote-provider`. VirtualBox skips that merge. Existing envs use `spa config merge remote-provider --yes`. `--from` / `--migrate` copies stay as-is.

- **Architecture files** ([#144](https://github.com/splunk/splunk-platform-automator/issues/144)): `spa init --architecture FILE` (exclusive with `--example`), `spa architecture plan|apply|check` for confirmed `kind: splunk.architecture` schema 1. Plan is read-only; apply overlays counts, RF/SF, `org_prefix`, and extra roles and reports ingested/skipped/remaining. Init and apply ignore `apps.by_role`; PS baseconfigs come from `splunk_baseconfig_dir`.

- **Apps** ([#59](https://github.com/splunk/splunk-platform-automator/issues/59), [#109](https://github.com/splunk/splunk-platform-automator/issues/109), [#125](https://github.com/splunk/splunk-platform-automator/issues/125), [#138](https://github.com/splunk/splunk-platform-automator/issues/138)): `spa apps search` / `snippet` / `download` / `add` / `remove` / `content-packs list`. ITSI is app 1841; Content Library is 5391 (`content-packs list` inspects the archive). `spa apps add APP_ID --new --roles ROLE[,ROLE]` appends a second `apps[]` row. Search of `unix` / `nix` / `Splunk_TA_nix` pins app 833. After `apps add 1841`, `data.next` sets Java 21 on a search-head selector (`java-21-openjdk` or `openjdk-21-jdk`), never global `os.packages`. Unix TA roles follow the vendor [Install](https://splunk.github.io/splunk-add-on-for-unix-and-linux/Install/) docs.

- **Providers**: `spa provider aws` named actions (`check-auth`, `latest-ami`, `describe-ami`, `validate`, `survey`, `KIND list`) ([#133](https://github.com/splunk/splunk-platform-automator/issues/133)). Without `--region`, `spa provider aws` uses `terraform.aws.region`, then `AWS_REGION` / `AWS_DEFAULT_REGION` / `~/.aws/config`. VirtualBox via Vagrant (`spa deploy` / `destroy` / `suspend` / `resume`; env dirs have no Vagrantfile) ([#56](https://github.com/splunk/splunk-platform-automator/issues/56)). External / BYO hosts: `spa hosts register` / `unregister`; SPA does not create or terminate those machines ([#57](https://github.com/splunk/splunk-platform-automator/issues/57)). CCM (Corporate Cloud Manager EC2 over HTTPS): `spa provider ccm` discovery; `spa deploy` / `destroy` / `suspend` / `resume` for a `ccm:` env; `CCM_TOKEN` is reported as set / not set ([#146](https://github.com/splunk/splunk-platform-automator/issues/146); [docs/ccm.md](docs/ccm.md)).

- **Lifecycle, hosts, logs** ([#71](https://github.com/splunk/splunk-platform-automator/issues/71), [#93](https://github.com/splunk/splunk-platform-automator/issues/93), [#138](https://github.com/splunk/splunk-platform-automator/issues/138)): `spa deploy --yes` creates missing managed hosts, waits for SSH, then installs Splunk. Host-only create is `spa hosts provision --yes`. Mutating commands write JSONL under `$SPA_ENV_DIR/logs/`; `spa logs list` / `--last` / `--follow --wait` (wait skips the previous run). Compact progress is one live line per named group. `--ansible-output` replays stored Ansible lines.

- **Validate, doctor, licenses, completion** ([#74](https://github.com/splunk/splunk-platform-automator/issues/74), [#107](https://github.com/splunk/splunk-platform-automator/issues/107), [#153](https://github.com/splunk/splunk-platform-automator/issues/153)): `spa validate` and deploy preflight require the Software installer for each role, version, and `splunk_architecture` in config (default `amd64`). `spa doctor` inventories Software as warnings (Enterprise and UF tarballs, PS baseconfig markers, top-level `*.lic`) without failing; `spa validate` / `spa deploy` stay fail-closed. `spa licenses list` is the catalog (bare `spa licenses` exits 2). `spa completion bash|zsh` prints the script; spa does not edit the shell startup file.

- **Skills and docs** ([#55](https://github.com/splunk/splunk-platform-automator/issues/55), [#61](https://github.com/splunk/splunk-platform-automator/issues/61), [#67](https://github.com/splunk/splunk-platform-automator/issues/67), [#101](https://github.com/splunk/splunk-platform-automator/issues/101), [#125](https://github.com/splunk/splunk-platform-automator/issues/125)): `spa skills install` copies packages from `$SPA_HOME/skills/spa/` into the IDE skill directory. Operator skills are `/spa` (including [upgrade.md](skills/spa/spa/references/upgrade.md) and [health.md](skills/spa/spa/references/health.md)), `/spa-create-config`, and `/spa-apps`. First-run path is [docs/quick-start.md](docs/quick-start.md). Generated catalogs are [docs/commands.md](docs/commands.md) and [docs/config.md](docs/config.md). Contributor map: [docs/architecture.md](docs/architecture.md).

### Changed

- **Python and Ansible**: Python **3.9–3.14** and Ansible **2.21**. `spa venv` picks the newest usable 3.9–3.14 when `python3` is newer.

- **Admin password required**: shipped examples set `splunk_defaults.splunk_admin_password` to `{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}`. Schema rejects an omitted or blank value. Ansible defaults no longer supply admin, indexer-cluster, or search-head-cluster passwords.

- **`SPADirName`** is `spa_env_dir | basename`.

- **License pairing** ([#138](https://github.com/splunk/splunk-platform-automator/issues/138)): a `license_manager` host and ITSI app 1841 without `.lic` files are warnings (`spa validate` stays `ok: true`). 2.5 required both. ES without an ES-capable license still fails.

- **App source and Content Library**: an omitted app `source` means Splunkbase (older configs that relied on omitted source as local must set `source: local`). The Content Library entry is Splunkbase `app_id: 5391` or `source: local` named `DA-ITSI-ContentLibrary`, with `itsi_content_pack: true` and exactly one of `content_pack_apps` or `install_all_apps: true`.

- **AWS and Software checks**: `terraform.aws` unknown keys fail validation. One management role per environment (second deployer, `deployment_server`, or `license_manager` is rejected). Software check requires `*/org_s2_indexer_indexes` and `*/org_cluster_manager_base`.

- **Ansible facts and vars**: fact cache is `$SPA_ENV_DIR/.ansible_facts`. Env inventory no longer symlinks `group_vars` into the repo; framework vars load through the `spa_group_vars` plugin.

- **Host link page**: `$SPA_ENV_DIR/config/index.html` is the architecture snapshot (2.x already had `create_linkpage.yml`). After a successful `spa deploy`, humans see `Next:` with that path.

- **`spa validate --splunk-config aws`** ([#125](https://github.com/splunk/splunk-platform-automator/issues/125)): replaces `validate_splunk_config.sh --splunk-config-aws`. Checks that named `security_group_names` exist; it does not read port rules.

- **Installer one-liner** is `curl … | sh` (POSIX `install.sh`).

- **CI** ([#151](https://github.com/splunk/splunk-platform-automator/issues/151)): PR CI runs a `Syntax` job plus three pytest jobs (`CLI tests`, `Ansible tests`, `Unit tests`).

### Deprecated

- **2.x playbook stems** still resolve with a hint (`use spa run NEW`). Current names are in [docs/migrate.md](docs/migrate.md).

### Removed

- **2.x `bin/` wrappers** (`init_spa_dir.sh`, `spa_env.sh`, `spa_doctor.sh`, `validate_splunk_config.sh`, `spash`, `splunk_config_aws.py`, `splunk_config_licenses.py`). Operators use `spa`. `bin/spa_venv.sh` remains (`spa venv`).

- **`vagrant-aws` / leftover `aws:`** ([#106](https://github.com/splunk/splunk-platform-automator/issues/106)): cloud is `terraform.aws`. A top-level `aws:` key or `splunk_hosts[].aws` fails validation.

- **Repo `.cursor/skills`**, `setup_ansible_remote.txt`, and `examples/configuration_description.yml`. Skill packages install with `spa skills install`. Descriptions live on the Pydantic fields and in generated [docs/config.md](docs/config.md).

- **Old `spa init --example` filenames** such as `cm_2idxc_sh_uf_aws.yml`. A topology id works with either provider: `spa init --example TOPOLOGY --provider aws|virtualbox|ccm|external NAME`.

- **Clone-equal layout as an operator env**: operator `spa` does not treat equal `SPA_HOME` / `SPA_ENV_DIR` as an environment. Clone remains the contributor path. See [docs/migrate.md](docs/migrate.md).

### Fixed

- **`upgrade_distributed`** targets `role_cluster_manager` and runs the version check first (`upgrade_software` on both plays so `splunk_current_version` and `splunk_target_version` exist before the upgrade message). Search heads stay `serial: 1`.

- **Reload deploy-server** waits for a large serverclass: `splunk reload deploy-server -timeout` defaults to 300 seconds, with 2 retries and a 20 second delay, delegated to the deployment server.

## [2.5.2](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.5.2) - 2026-09-10

### Fixed

- **CI `json_query` on GitHub Actions** – `debug_app_scope.yml` now filters DS apps with builtin Jinja (`selectattr`/`rejectattr`) instead of `json_query`, which ansible-core does not ship. Test runners also install `requirements.yml` collections into `tests/.collections` for other playbooks.

## [2.5.1](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.5.1) - 2026-09-10

### Fixed

- **CI app-scope tests without `../Software`** – Inventory parse for `debug_app_scope.yml` honors `SPA_BASECONFIG_DIR` and `SPA_SOFTWARE_DIR`. Local tests create installer/license stubs under `tests/fixtures/baseconfig/` so GitHub Actions does not need a real Software directory.

- **Release only after tag CI** – `scripts/release.sh --push` no longer runs `gh release create`. [`.github/workflows/release.yml`](.github/workflows/release.yml) publishes the GitHub Release only after local tests pass on the tag. Bump/`--push` do not re-run `./tests/run_local_tests.sh`; use `--check` for that.

## [2.5.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.5.0) - 2026-09-10

### Added

- **Deploy preflight checks for stale Ansible fact cache** – `ansible/preflight_deploy.yml` runs at the start of `deploy_site.yml` and `aws_wait_hosts.yml`:
  - Probes each host for `python3` with `raw` (bypasses cached interpreter).
  - Flushes jsonfile fact cache entries when the cached `discovered_interpreter_python` differs from the live host (common after OS/AMI changes with the same hostnames).
  - Verifies Ansible `ping` with the probed interpreter before the main deploy.
  - `aws_provision.yml` flushes cache for provisioned hosts when Terraform inventory is regenerated (`spa_flush_fact_cache_on_provision`, default `true` in `ansible/group_vars/all/ansible.yml`).
  - `spa_preflight_deploy` (default `true`) controls whether preflight runs at deploy start.

- **Bidirectional license / license_manager schema validation** – `splunk_license_file` now requires a `license_manager` host (and vice versa), including overrides on hosts and `splunk_environments`. Enforced in Pydantic (`schema.py`) and in `validate_splunk_config.sh` (default step 3/4). Optional `--check-licenses` also verifies files in `../Software` and ITSI license presence. `splunk_config_licenses.py` reports the same gaps in `warnings`. Unit tests in `tests/test_schema.py`.

- **Guided `splunk_config.yml` setup (Cursor skill)** – Interactive workflow for designing AWS Linux deployments without hand-editing every field:
  - **Skill**: `skills/spa/spa-create-config/` ([Agent Skills spec](https://agentskills.io/specification.md); Cursor: `.cursor/skills/` symlink, `/spa-create-config`) — phased flow (deployment intent, SVA topology, sizing, OS/SSH, role placement, apps, licenses, write, validate, handoff). SPA project skills use the `spa-*` prefix for `/` command discovery.
  - **References**: architecture requirements, SVA questionnaire/map, AWS baseline, OS matrix (Amazon Linux 2023, RHEL 10, Ubuntu 24.04), role placement, apps questionnaire, license questionnaire, **RF/SF sizing** ([rf-sf-sizing.md](skills/spa/spa-create-config/references/rf-sf-sizing.md) — Splunk doc formulas for replication/search factors, peer minimums, multisite `total` calculation, ingest/storage hints), **AWS without credentials** ([aws-without-credentials.md](skills/spa/spa-create-config/references/aws-without-credentials.md) — Step 0 `spa provider aws check-auth` probe, static AMI fallback, skip `--splunk-config-aws` when API unavailable), validation checklist.
  - **Docs**: guided setup is now consolidated in [user-guide.md](docs/user-guide.md) and [aws.md](docs/aws.md).

- **`bin/splunk_config_aws.py`** – AWS discovery and validation for `terraform.aws`:
  - List regions, key pairs, security groups, instance types.
  - **Dynamic AMI resolution** for Amazon Linux 2023, RHEL 10, and Ubuntu 24.04 (SSM public parameters and `describe-images` where needed).
  - `spa provider aws check-auth` — STS credential probe (no `--region` required); use in skill Step 0 before discovery.
  - `spa provider aws latest-ami`, `survey` (recommended AMIs + defaults), `describe-ami`, `validate` with `--json` / `--agent` output.

- **`bin/splunk_config_licenses.py`** – Scan `../Software` (`splunk_software_dir`) for license files and propose `splunk_defaults.splunk_license_file`:
  - ITSI-aware proposals when `splunk_app_deployment` includes ITSI (`premium_app: itsi`, `app_id: 1841`, or content packs).
  - `--config` to read current config; text fallback when PyYAML is not installed; `yaml_snippet` for paste into config.

- **`bin/validate_splunk_config.sh`** – Pre-provision quality gate:
  - Pydantic schema validation, inventory plugin load, license/role pairing, provision/deploy playbook syntax-check.
  - Optional `--check-licenses` (Software dir file presence + ITSI license file) and `--splunk-config-aws` (live AWS API checks).

- **Example**: `examples/aws_lab_baseline.yml` — the then-current minimal lab starting point with recommended OS packages (including polkit).

- **CI and release tooling** – GitHub Actions [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs `bash -n` and [`tests/run_local_tests.sh`](tests/run_local_tests.sh) on pull requests and `master`. Tag workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) publishes a GitHub Release from `CHANGELOG.md` if one is missing. Maintainer commands: [`RELEASE.md`](RELEASE.md), [`scripts/release.sh`](scripts/release.sh).

- **Local unit tests** – Schema sweep for shipped examples and app-scope fixtures; SHC-direct and `run_playbook_after_restart` rules; `bin/splunk_config_licenses.py` and `bin/splunk_config_aws.py` helpers; secret-resolver env/vault normalization.

- **`spa-create-config` RF/SF guidance** – [sva-topology-map.md](skills/spa/spa-create-config/references/sva-topology-map.md) SVA code → lab RF/SF defaults and peer checklist; [rf-sf-sizing.md](skills/spa/spa-create-config/references/rf-sf-sizing.md) documents Splunk Enterprise rules (failure tolerance, multisite `total` minimum, `idxc_rf` for two-peer sites) and links to SVA M2/M12 and Deployment Capacity Manual performance/storage tables.

### Changed

- **Cursor skill naming** — Project skills renamed to `spa-*` for `/` command discovery: `spa-create-config` (was `create-splunk-config`), `spa-add-test-scenario` (was `add-test-scenario`).

- **`spa-create-config` AWS credential handling** — Step 0 runs `spa provider aws check-auth` and records API availability; Phase 4 branches to static examples when creds or boto3 are missing; Phase 8 uses default `validate_splunk_config.sh` only (no `--splunk-config-aws`) until credentials work.

- **`spa-create-config` plan mode** — Step 0 `plan` vs `write`; Phases 0a–6b unchanged; Phase 6c outputs architecture plan from [architecture-plan-template.md](skills/spa/spa-create-config/assets/architecture-plan-template.md); Phase 7–9 only after user approves plan.

- **`spa-create-config` secrets handling** — [secrets-handling.md](skills/spa/spa-create-config/references/secrets-handling.md): never display Splunkbase or AWS credential env values in chat or terminal; report set/not-set only; prefer `spa provider aws check-auth` for AWS; forbid `echo`/`printenv` on secrets and `aws configure list`.

- **Agent skills layout** — Canonical packages under `skills/spa/` ([Agent Skills](https://agentskills.io/specification.md) format); Cursor discovery via `.cursor/skills/` symlinks; [AGENTS.md](AGENTS.md) and [docs/contributing.md](docs/contributing.md#agent-skills) for cross-tool setup.

- **Default AWS tag `SPADirName`** — Lab examples include `SPADirName: "{{ playbook_dir | dirname | basename }}"` under `terraform.aws.tags` (SPA repo folder name on the controller).

- `examples/splunk_config_terraform_aws.yml` — default AMI guidance aligned with RHEL 10 / latest-OS discovery.
- [examples/single_node_itsi.yml](examples/single_node_itsi.yml) — ITSI search tier uses Java 21 (`java-21-openjdk` / `openjdk-21-jdk`).
- [tests/configs/2site-idxc_shc_mc_ds_sh_hf_uf_itsi_apps.yml](tests/configs/2site-idxc_shc_mc_ds_sh_hf_uf_itsi_apps.yml) — ITSI search hosts use `java-21-openjdk` on RHEL 10 (ITSI max Java 21).
- [README.md](README.md) — example `splunk_version` 10.4.0; badge formatting cleanup.
- OS guidance: **polkit** required on Amazon Linux and RHEL (`polkit`); **policykit-1** on Ubuntu (SPA policykit check fails on UF without it).

## [2.4.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.4.0) - 2026-08-25

### Added

- **Single-app ITSI content packs** – Deploy a one-pack archive (Splunkbase or local) without `content_pack_apps`. Set top-level **`name`** to the on-disk pack folder (e.g. `DA-ITSI-CP-CUST-ATLAS-AWS-EBS` for Splunkbase app_id 7294); optional top-level **`content_pack_api`** and **`customizations`** drive ITSI API registration and post-restart playbooks. Deploy and verify like a standard folder-backed app. See [Apps](docs/apps.md#itsi-and-content-packs).

- **App Deployment** – New automated deployment of Splunk apps from Splunkbase or local filesystem, with per-host routing.
  - **General**:
    - **Config**: `splunk_app_deployment` in `splunk_config.yml` (credentials, `apps` list with `name`, `source` (splunkbase/local), `app_id` or `path`, `version`, `target_roles`, optional `state`, `deployment_target`, `serverclass`, etc.).
    - **Playbooks**: `ansible/splunk_apps_deploy.yml` (deploy/update apps), `ansible/splunk_apps_remove.yml` (remove apps with `state: absent`).
    - **Routing**: Apps are deployed to the correct location per host—Deployment Server (`etc/deployment-apps`), Cluster Manager (`etc/manager-apps`), Search Head Cluster Deployer (`etc/shcluster/apps`), or directly to the host (`etc/apps`). Routing respects cluster membership and optional `deployment_target: direct`.
    - **Roles**: `apps_deployment_server`, `apps_cluster_manager`, `apps_deployer`, `apps_direct` (shared logic in `apps_common`). Handlers: Restart Splunk, Reload deploy-server, Push shcluster bundle, Apply indexer cluster bundle.
    - **Sources**: Splunkbase (with env-based credentials) or local path; idempotent install/update with optional backup.
    - **Download options**: `target_download` (default false)—when true, each target downloads Splunkbase apps itself (avoids slow upload from Ansible host for large apps); `cache_downloads` (default true)—when false, remove downloaded `.tgz` after extraction.
    - **`update_mode`** (default `"merge"`): Controls how existing apps are replaced during updates. `merge` overlays new files onto the existing directory, preserving files not in the source (e.g. `local/` customizations); `clean` removes the old app directory before installing (full replace). Configurable globally under `splunk_app_deployment.update_mode` and per-app via `app_item.update_mode` (per-app overrides global). Applies to all deployment methods (Deployment Server, Cluster Manager, Deployer, Direct), ITSI premium apps (search head, indexer, license manager installs), and ITSI content packs (file extraction only; the content pack API install and its `resolution` parameter are unaffected).
    - **`deploymentclient_check`** (default `true`): When true, app deployment runs `splunk btool deploymentclient` on hosts to detect actual deployment clients and filter Deployment Server serverclass whitelists. When false, skips btool and uses an inventory-based heuristic (assumes non–deployment-server, non–SHC/IDXC-member hosts are deployment clients). Set to `false` for faster runs when btool is unavailable or unnecessary.
    - **Verification**: `ansible/verification/verify_app_deployment.yml` and role-specific verification tasks to confirm deployed apps match config.
    - **Docs**: consolidated in [Apps](docs/apps.md).
  - **Target filters** – Per-app filters to restrict which hosts receive an app:
    - **hosts_whitelist** / **hosts_blacklist**: Include or exclude specific search heads (standalone and SHC members in deployer context).
    - **shc_whitelist** / **shc_blacklist**: Include or exclude by search head cluster name (must match `splunk_shclusters`).
    - **idxc_whitelist** / **idxc_blacklist**: Include or exclude by indexer cluster name (must match `splunk_idxclusters`).
    - **sc_whitelist** / **sc_blacklist**: (Deployment Server / Agent Management) Control serverclass whitelist/blacklist for which clients get the app.
    - Filters are applied in a fixed order to compute the final target set; empty result means the app is not deployed (no error). Premium apps may use only **hosts_whitelist** OR **shc_whitelist** (not both) and may not use blacklists.
    - **Documentation**: [Apps — filter targets](docs/apps.md#filter-targets).
  - **Customizations** – Per-app, per-role options to modify deployed apps after install:
    - **`remove`**: Delete files or directories from the app (paths relative to app root).
    - **`local_configs`**: Create or update Splunk `.conf` files in the app’s `local/` folder (same structure as `splunk_conf` in `splunk_config.yml`).
    - **`run_playbook`** / **`run_role`**: Run a custom Ansible task file or role for that app (path from project root; `app_path`, `app_name`, and optional `extra_vars` provided by the framework).
    - **`run_playbook_after_restart`**: Register a task file to run **after** the deployment handler (e.g. Restart splunk) has run on the host. Use when the playbook must run once Splunk is back up (e.g. wait for port, then call REST or configure lookups). Supported for **direct deployment** only; requires `deployment_target: direct` (enforced by schema). The playbook runs in a follow-up play in `splunk_apps_deploy.yml` with `app_path`, `app_name`, and `extra_vars` passed in. Example: `ansible/apps_playbooks/Splunk_SIM_addon-configure.yml` for the Splunk Infrastructure Monitoring add-on.
    - Same app can appear multiple times in `splunk_app_deployment.apps` with different `target_roles` and different `customizations`.
    - Customizations run in order: deploy app → remove → local_configs → update_indexes → run_playbook/run_role. Setting `update_needed: true` in a custom task file triggers the correct deployment handler.
    - **`update_indexes`**: When `true`, copies `default/indexes.conf` to `local/` and rewrites `homePath`/`coldPath` to use configured volumes (`splunk_volume_defaults`). Useful for apps that ship index definitions with hardcoded paths. Normal (non-premium) apps only.
    - **Force flags** – By default `local_configs`, `run_playbook`, and `run_playbook_after_restart` only execute when the app is installed or updated during the current run. Force flags override this and run the customization every time:
      - **`force_local_configs`** (default `false`): write local config files even if the app was already installed at the expected version.
      - **`force_run_playbook`** (default `false`): run the `run_playbook` task file even if no install/update occurred.
      - **`force_run_playbook_after_restart`** (default `false`): run the `run_playbook_after_restart` task file even if the app was already installed. Also applies to ITSI content pack apps.
    - **Example playbook** `ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml`: Enables Splunk_TA_nix script inputs (performance metrics); optional `extra_vars.ta_nix_script_index`. Equivalent behavior via `local_configs` is documented for universal_forwarder.
    - **Documentation**: [Apps — customize an app](docs/apps.md#customize-an-app).
  - **Premium apps (ITSI)** – Splunk IT Service Intelligence as a premium app (single archive, multiple apps, role-specific extraction):
    - **Config**: `premium_app: itsi` on the app entry; optional `version` (same as normal apps), `hosts_whitelist` / `shc_whitelist` (and other target filters), `itsi_notification_disable`. Source Splunkbase (app_id 1841) or local path.
    - **Roles**: Cluster Manager (selected apps to `manager-apps`), License Manager (license/access apps to `etc/apps`), Deployer (full bundle to `shcluster/apps`), Search Head (full bundle to `etc/apps`). Respects `target_download` for controller vs per-target download and cache.
    - **Version check**: Reads `[launcher]` version from each app’s `app.conf` in the archive and on the target; only deploys when at least one app is missing or version differs. App list and expected versions come from the archive (app-conf cache or listing); no hardcoded fallback—playbook fails if the list cannot be obtained.
    - **`shc_rolling_restart`** (default `false`): When `true` on the ITSI app entry, the deployer uses a rolling restart instead of a standard bundle push after installing ITSI. Workaround for environments where ITSI requires all SHC members to restart sequentially.
    - **Removal**: Per-role removal (CM, LM, deployer, search head) with app list built from the archive; same target filters (`hosts_whitelist`, `shc_whitelist`, etc.) apply for search heads. Fails if archive is not available or not listable.
    - **Task structure**: Splunkbase download and app-conf cache split into controller vs `target_download` task files to avoid skipped tasks; removal split into role-specific task files (e.g. `itsi_remove_deployer.yml`, `itsi_remove_search_head.yml`).
    - **Docs**: [Apps](docs/apps.md#itsi-and-content-packs).
  - **ITSI content pack install** – Deploy and remove ITSI content packs (Splunkbase or local) via the same app deployment flow as ITSI:
    - **Single-app packs**: `itsi_content_pack: true` with no `content_pack_apps` (and not `install_all_apps`); top-level `name` is the pack folder; optional top-level `content_pack_api` / `customizations`.
    - **Multi-app packs**: Top-level `name` is the library folder (e.g. `DA-ITSI-ContentLibrary`); `content_pack_apps` lists additional pack folders only, with per-pack `content_pack_install`, optional `customizations.run_playbook_after_restart`.
    - **Full bundle**: Optional `install_all_apps: true` extracts the entire archive at deploy/removal.
    - Target filters (`hosts_whitelist`, `shc_whitelist`, etc.) are inherited from the ITSI app so content pack and ITSI use the same scope.
    - **Install**: Content pack role (`apps_itsi_content_pack`) installs the pack and nested apps to search heads (standalone and SHC); deployer pushes to `shcluster/apps`, direct deployment to `etc/apps`. Post-restart playbooks run after the Restart splunk handler when configured.
    - **Removal**: Content packs are removed before ITSI (sorted order). On standalone search heads, when a content pack is in `direct_apps` but ITSI was not (e.g. eligibility excluded ITSI for that host), ITSI is added to `direct_apps` so both “Remove ITSI apps from etc/apps” and content pack removal run on the single SH.
    - **Docs**: [Apps](docs/apps.md).

- **Vault support for config values** – Encrypted values in config and playbooks:
  - **Inventory decryption**: Vault-encrypted values in `splunk_config.yml` are decrypted in place by the inventory plugin’s `secret_resolver.py` when the config is loaded (e.g. for Splunk admin password and other variables used by roles).
  - **Environment variable lookups**: `{{ lookup('env', 'VAR_NAME') }}` expressions in `splunk_config.yml` are resolved at config load time by the inventory plugin (e.g. for Splunkbase credentials).
  - **Lookup plugin**: Custom lookup plugin `spa_vault_decrypt` for playbooks that load config via `include_vars` (e.g. Terraform AWS credentials in `aws_provision.yml` and `aws_destroy.yml`); lookup plugin path set in `ansible.cfg` via `lookup_plugins = ./ansible/plugins/lookup`.
  - **Docs**: [Secrets](docs/secrets.md).

- **SSH public keys** – Install additional SSH public keys on managed hosts:
  - New `os.ssh_keys` config option: list of local public key file paths to install into the Ansible login user's `authorized_keys`.
  - Can be set globally in the `os:` section or per host in `splunk_hosts[].os.ssh_keys`.
  - Standalone playbook `ansible/ssh_keys.yml` to deploy keys without a full site deployment.
  - Documented in [README.md](README.md).

- **Terraform AWS** – Optional `subnet_id` for VPC subnet placement:
  - New `terraform.aws.subnet_id` option in `splunk_config.yml` (global and per-host)
  - Instances are placed in the specified subnet when set; otherwise AWS uses the default subnet
  - Documented in [AWS](docs/aws.md) and [terraform/aws/README.md](terraform/aws/README.md)

### Fixed

- Fixed `os.packages` not being merged between global and per-host levels — host-level packages now combine with global packages instead of replacing them
- Fixed missing outputs.conf configuration for Splunk 9.2+ on Deployment Servers not acting as indexers

## [2.3.2](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.3.2) - 2026-02-08

### Added

- Added pytest-based test framework for automated deployment and verification testing:
  - Sequential deployment tests with dependency tracking (`is_provisioned`, `is_splunk_installed`, `is_splunk_configured`)
  - Integrated verification tests (data flow, IDXC health, SHC health)
  - Parallel execution support for multiple configurations using pytest-xdist
  - `--local` mode to run verification tests against existing local deployments
  - Automatic workspace isolation with per-config venvs and temp directories
  - Infrastructure auto-teardown after test completion
- Added Pydantic-based schema validation for `splunk_config.yml`:
  - Validates configuration structure before Ansible processing
  - Enforces required fields, valid roles, and business rules
  - Provides clear error messages for invalid configurations
  - New `schema.py` module and `test_schema.py` unit tests
  - Run with `./tests/run_schema_tests.sh`

### Changed

- Optimized Ansible performance:
  - Grouped tasks with standard `when` conditions into blocks to reduce conditional checks
  - Increased Ansible forks to 20 for better parallelism
  - Enabled smart fact gathering and JSON fact caching in `ansible.cfg`

## [2.3.1](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.3.1) - 2026-01-25

### Added

- Added `bin/spash` wrapper script to easily connect to valid Ansible hosts via SSH
  - Lists available hosts and their roles with `./bin/spash -l`
    - Added option `-v` to check the status of the hosts (ansible ping/aws status)
  - Connects to hosts using Ansible inventory details
  - Added scp support to copy files to/from hosts with `-c` option
- Added check for Ansible version compatibility (greater than 2.10)
- Added requirements for community collections

### Changed

- Updated all Ansible tasks to use Fully Qualified Collection Names (FQCNs)
- Added names to anonymous tasks

### Fixed

- Fixed premature terraform provisioning
- Fixed terraform variable precedence order
- Fixed Splunk version detection logic for Splunk 10+
- Fixed Ansible linting issues:
  - Added names to anonymous tasks
  - Corrected boolean syntax
  - Fixed loop usage and filters
  - Fixed handler notifications
  - Standardized octal file modes to quoted strings (e.g., `'0644'`)
- Fixed deprecation warnings:
  - Replaced legacy fact variables (e.g., `ansible_os_family`) with `ansible_facts` syntax
- Fixed conditional type errors in several tasks

## [2.3.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.3.0) - 2026-01-18

### Added

- Added Terraform AWS integration as modern replacement for the outdated vagrant-aws plugin
  - Ansible-driven Terraform workflow with single source of truth in `splunk_config.yml`
  - Automatic Ansible inventory generation from Terraform outputs
  - AWS instance status check verification before deployment
  - Support for per-host instance types, volumes, and configurations
  - Comprehensive documentation is consolidated in [AWS](docs/aws.md)

## [2.2.6](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.6) - 2025-09-24

### Fixed

- Fixed some issues for ansible 2.19.x

## [2.2.5](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.5) - 2025-01-15

### Fixed

- Fixed file permissions for splunk systemd service file

## [2.2.4](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.4) - 2024-12-27

### Fixed

- Disable COM1 when using Virtualbox on WSL with vagrant

### Added

- Added splunk_architecture to support different OS architectures like amd64, x86_64, arm64, etc.
- Added splunk_fips to support FIPS mode in splunk

## [2.2.3](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.3) - 2024-12-01

### Fixed

- Forced splunk restart handler to the inventory_hostname to prevent mistaken delegations

### Added

- Added org_indexer_volume_indexes and org_all_indexes to heavy forwarders for app wizards index selection
- Added requirements.txt to the project for easy module installation
- Added commented out profiling for easy timestamp activation in the ansible output
- Added support for vagrant-gecko-aws plugin

## [2.2.2](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.2) - 2024-03-05

### Fixed

- Fix the usage of the manager-apps dir on the cm from 9.0.0 on

## [2.2.1](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.1) - 2024-02-11

### Fixed

- Fixed the sharing of variables with role dependencies ([Ansible Issue 80944](https://github.com/ansible/ansible/issues/80944)) -> Support Ansible 2.15 and above.

## [2.2.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.2.0) - 2023-09-25

### Changed

- Changed code to reflect new name as splunk-platform-automator
- Removed biased language and use new manager/peer terms from 9.0.0 on
- Transfered the project to the Splunk Organization
- Renamed the project from splunkenizer to splunk-platform-automator

### Added

- Added config setting to connect to an existing license server

### Fixed

- Fixed usage of AWS key/secret in splunk_config.yml
- Fixed 'Unsupported parameters' for command in newer ansible versions

## [2.1.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.1.0) - 2022-03-05

### Changed

- Changed default image for virtualbox to almalinux/8
- Index path settings are defined in the [default] per default. Can be disabled.
- Index definitions at splunk_defaults.splunk_indexes must be in dictionary format
- Changed start_ip for virtualbox, because of new restriction in Vbox 6.1.28

### Added

- Added check for acl package availability in linux
- Added setting `splunk_use_policykit` to disable policykit usage
- Added logic to setup sudo rules, if policykit is not installed
- Added playbook to run search head cluster rolling upgrade
- Added new splunk_hosts types: list and iter (shorter config for lots of equal nodes)
- Added possibility to set addidional index options
- Added test_metrics index per default
- Added setting `splunk_kv_store_engine_wiredtiger` to disable config (enabled by default)
- Added playbook to run indexer cluster rolling upgrade
- Added playbook to cleanup splunk_backup (etc) archives
- Added playbook to update inputs ssl certificates
- Added playbook to call splunk rest endpoints

### Fixed

- Fixed update /etc/hosts if ip_addr not available
- Fail on install if no splunk.secret file is found and more than one host is deployed
- Create auth dir if needed
- Fixed missing bundle push after shc setup
- Fixed boolean comparison for older python versions
- Fixed removed collections.Mapping usage with python 3.10
- Added splunkd full service check during SHC member add. Did run into timeout when having lots of apps.
- Updated URL for downloads of splunk install archives
- Follow symlinks during Splunk archive extraction
- Fixed SPLUNK_HOME ownership, when having it linked to another directory

## [2.0.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v2.0.0) - 2021-07-27

### Changed

- Never disable SELinux on Universal Forwarders
- start_ip is now part of `virtualbox` section (was in general before)

### Added

- Added ability to add custom ansible variables globally and on host level
- Set storageEngine=wiredTiger on new installs for 8.1+
- Created Ansible inventory plugin (no more `vagrant status` needed to recalculate inventory)
- Create all AWS EC2 instances at the same time. Huge time saver!
- Better error checking in `splunk_config.yml` file
- Added playbook (`create_linkpage.yml`) to update index.html file
- Added disable_apparmor setting to disable AppArmor, if found
- Added pipelining = true to ansible.cfg

### Fixed

- Usage of own certificates for single indexers

### Removed

- Ansible cannot be called from vagrant directly
- Removed dependency to vagrant (Although vagrant does still work!)
- Removed usage of `vagrant-hostmanager` plugin. This plugin can be removed.

## [1.3.0](https://github.com/splunk/splunk-platform-automator/releases/tag/v1.3.0) - 2021-04-11

### Changed

- New default: Do not run ansible from vagrant
- New default: disable_selinux: true (disables only, if state is 'enforcing')

### Deprecated

- Call ansible from vagrant

### Added

- Added support for SmartStore (S2)
- Install Policy Kit Rules by enable boot-start for 8.1.1+
- Added setting summary_replication = true
- Added Bucket tunings for indexers
- Do not update comment macro permissions for Splunk 8.1+
- Added playbook to update splunk web certs
- Support upgrades to Splunk 8.x
- Allow to set custom config file settings (splunk_conf)
- Option the 'os' section to disable SELinux (needs Ansible 2.7)
- Option to allow maxVolumeDataSizeMB for volumes to be calculated from the available filesystem free space

### Fixed

- Fixed ansible temp_dir warning during splunk download
- Fixed SHC setup for Splunk 8.1.x
- Fixed changed status to be ok for non changing shell and command tasks
- Fixed splunk command calls to run as user splunk instead of root
- Do not deploy org_search_volume_indexes on single node instance
- Fixed search head cluster setup when using own certificates
- Enable systemd-managed by default with Splunk 7.3.x
- Fixes broken universal forwarder install with 7.3.x
- Fixed search head cluster setup for 7.3.x
- Fixed hard coded ansible user home location
- Fixed issue: Special characters in Splunk password #6
- Added workaround for bug in vagrant-aws with vagrant 2.2.7

## [1.2](https://github.com/splunk/splunk-platform-automator/releases/tag/v1.2) - 2019-06-02

### Added

- Added option to run ansible independent from vagrant.
  - Create VM first without Ansible and run playbooks in parallel on the nodes. See [README.md](README.md#optional-but-recommended-create-vm-first-without-ansible-and-run-playbooks-in-parallel-on-the-nodes)
  - More modularization in the code and playbooks
  - Added playbook to remove the Splunk installation from nodes
  - Added playbooks to stop/start/restart splunk
  - Added playbook to uninstall the splunk software along with THP and ulimit settings
  - Added playbook to run splunk commands
  - Added playbook to upgrade the Splunk software (not cluster aware)
- Support native systemd support introduced with Splunk Version 7.2.2
  - Added ulimit settings to native systemd service file
  - Create policy kit rule if systemd version 226 is available
  - Support polkit version 0.105 policy file.
  - Create suoders file as workaround to allow splunk user restart splunk service, if systemd version is too low.
- Added support for Ansible versions 2.7.x and removed Ansible version check
- Added support for Ansible versions 2.8.x
- Update permissions of comment macro to be global
- Moved python install on ubuntu to splunk_config file
- Added option 'idxc_discovery_password' to setup indexer discovery
- Support for multiple license files
- Add option general.url_locale (ex. en-US) to be added in index.html
- Added options to turn off login page info (ex. in AWS)
- Added options to force inventory name set as serverName and/or host (ex. in AWS)
- Added option to set os hostname (ex. in AWS)
- Support for windows virtual machine setup in Virtualbox
  - Installation and configuration of windows universal forwarder (deployment server needed for now)

### Fixed

- Fixed 'vbguest' error, when using AWS only
- Fixed some base_config installations on single node configs with additional roles
- Disable time sync cron for AWS by default

## [1.1.1](https://github.com/splunk/splunk-platform-automator/releases/tag/v1.1.1) - 2018-10-18

### Changed

- Optimized network config file upates for AWS instances

### Fixed

- Fixed SHC setup for Splunk 7.2
- Fixed updating the index.html, after restart AWS instances

## [1.1](https://github.com/splunk/splunk-platform-automator/releases/tag/v1.1) - 2018-10-08

### Added

- Added support for Ansible versions 2.5.x and 2.6.x
- Added support for creating virtual machines in the Amazon Cloud (AWS)
- Replaced internal hosts file maintenance with the vagrant hostmanager plugin
- Improved standalone Ansible playbook usage
- Added option to download splunk binaries from splunk.com during install
- Added hf_host field to heavy_forwarder
- Added feature to save a copy of the base_config apps on the Ansible host

### Fixed

- Removed locale (en_GB) in the links of node link page (index.html)
- Fixed wrong systemd service name for universal forwarder
- Removed Deployment Server from serverclasses whitelists
- Do not install splk_all_forwarder_outputs on a single box, when adding LM, MC roles

## [1.0](https://github.com/splunk/splunk-platform-automator/releases/tag/tag/v1.0) - 2018-05-21

### Added

- Support hashed config values for cluster and ssl cert passwords
- Support for using the same splunk.secret file
- Support new password policy of Splunk 7.1 during install
- Reworked shcluster setup. Better support for adding shc nodes.
- Allow Splunk Version 'latest' to use the latest found splunk version in the directory
- Support for single node system
- Using systemd for splunk services, where available
- Timezone taken from vagrant host per default
- Support Ubuntu
- Support index volume definitions
- Support to use Ansible playbooks without vagrant
- Support ssl for splunk web (including custom certs)
- Support ssl for forwarder->indexer communicaion (including custom certs)

### Fixed

- Remove deployment server from the host lists generated for serverclasses
- Allow fgdn hosts
- Added missing org_search_volume_indexes to DS
- Added org_all_search_base to all roles with web enabled

## [0.9](https://github.com/splunk/splunk-platform-automator/releases/tag/v0.9) - 2018-02-09

### Added

- Added time sync workaround for the clock skew without virtualbox additions
- Configuration variables can now also be set on splunk_hosts level
  - Ansible vars are configurable in the config file (ex. skip_tags)
  - Allow to install additional os packages
- Make 'org_' for apps changeable, does set to splunk_env_name
- Make destname for apps changeable (ex. org_site_n_indexer_base)
- Added single indexer playbook, forwarding config to it not yet implemented
- Added ansible.cfg to turn off deprecation warnings on ansible 2.4+
- Add note about hostname, roles, user/pw on login page
- Support multiple indexer clusters in org_all_forwarder_outputs (use idxc name in stanza)
- Allow mixed splunk versions. Can be set per splunk_env or host level
- Support single indexers
- Support single search heads
- Create HTML link page for all roles

### Removed

- Removed [splunk_env_name:vars] from the ansible inventory

### Changed

- Simplifyed the configuration file. Established default values for most of the settings
- Reworked outputs and search_peer configuration

### Fixed

- not all apps on single search head are deployed from deployment server
- add tags to the dserver and serverclass tasks
- volume and indexes should be deployed to single search head (create serverclass)
- org_all_forwarder_outputs should output to all indexers. does only use first cluster in multicluster config

## [0.8](https://github.com/splunk/splunk-platform-automator/releases/tag/v0.8) - 2017-11-12

- Check for site affinity in search head clusters
- Install path /opt changeable
- Disable indexing on CM, DS(?), Deployer (check in the cli file) -> done by the forwarder app
- set indexes from all config file
- org_search_volume_indexes on SH
- Check correct usage of ansible vars in when statements
- Set search head cluster label
- org_cluster_search_base needs probably app_path during config on deployer, wrong path used
- sh need splunk restart after cluster init
- Find solution for reboot before bootstrap (if command throws error, reboot and bootstrap)
- tries to add dservers twice on smc, dserver list must be created in a better way, indexer cluster not there
- create hosts file out of inventory of Vagrant file (done from config file)
- make Vagrant file dynamical
- Set role with Vagrant var
- make common main playbook and decide on Vagrant var (done on the config role)
- after shcluster build, bundle push must be performed: `splunk apply shcluster-bundle -target https://sh3:8089`
- uf is not connecting after install, needs reboot, how to check for it?
- do not add own host to dservers and make the list unique
- Multi site indexer cluster
- single site multiside cluster
- renamed playbooks -> ansible
- probably need to wait until the shcluster has restarted, otherwise bundle deploy can fail
- org_full_license_server should not be installed if role license master (check on cm)
- org_cluster_search_base should not be installed if role is cluster master
- ulimit settings <https://docs.splunk.com/Documentation/Splunk/latest/Installation/Systemrequirements#Considerations_regarding_system-wide_resource_limits_on_.2Anix_systems>
- THP settings <http://docs.splunk.com/Documentation/Splunk/latest/ReleaseNotes/SplunkandTHP>
- org_cluster_search_base misses multisite = true if multiside idx cluster
- one more restart for UF
- caclculate idxc_available_sites dynamically and add it to the cluster
- calculate shc_captain dynamically
- Change config to be able to have more than one cluster
- do not provide base_config apps, user must download
- Support multiple cluster masters in org_cluster_search_base (use idxc name in stanza)
- hashed password check must be changed to check inside the cm stanza in org_cluster_search_base on cm
- Add cm as search peer in SMC
- Support single search heads
- don't install relevant baseconfig, if clustermaster, deployment server, monitoring console is not there
- check if full_lic app is created, if license master is not already installed, works :-)
- check if deployment client app is installed, if deployment server is not yet installed, works :-)
- add forward app, if deployment server is missing
- add license client app, if deployment server is missing
- allow relative pathes for software an baseconfigs
- added org_all_search_base
- fix dserver list creation fail, if group was missing
- Output error if license file not there
- Added fix for clock skew on Linux in Virtualbox: <https://oitibs.com/fix-virtualbox-guest-time-skew> (not working, either)
- dserver list does not exclude UF
- Install forward output, if deployer is ds
- Install forward output, if cm is ds
- Create list of license clients in serverclass dynamically
- added new role for heavy forwarder
- cleanup ansible tags
- Calculate /etc/hosts from inventory if possible otherwise from splunk_config
- Single SH does not get license client app -> need to be added automatically in server class
- reload deploy server, if serverclass changes
- fix serverclass whitelisting
- dynamic ip addresses
- use a start_ip for dynamic ips
- update serverclass everytime a server is created
- Check host to be available before adding dserver
- set site0 to cluster masters in the example configs (no site affinity)
- Allow to turn on virtualbox addon installation inside config (disable clock skew fix)
- disable first login page
