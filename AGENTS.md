# Splunk Platform Automator — agent guide

Splunk Platform Automator (SPA) provisions and deploys Splunk Enterprise on **AWS Linux** using Ansible + Terraform. Configuration is driven by `config/splunk_config.yml`.

## Start here

| Task | Path / command |
|------|----------------|
| Main config | `$SPA_ENV_DIR/config/splunk_config.yml` (copy from `examples/` via `spa init --example`) |
| Config keys reference | Types, allowed values, and identifier patterns live in the Pydantic schema (`ansible/plugins/inventory/schema.py`, enforced by `spa validate`). `spa features` / `examples/catalog/features.yml` is when-to-use, snippets, and merge notes (commented dump: `examples/configuration_description.yml`) |
| Guided human + agent workflow | [docs/Splunk_Config_Guided_Setup.md](docs/Splunk_Config_Guided_Setup.md) |
| 2.x → 3.0 operator changes | [docs/Migrate_SPA_2x_to_3x.md](docs/Migrate_SPA_2x_to_3x.md) |
| New environment (one clone, many envs) | `spa init --example cm_2idxc_sh_uf --provider aws ~/envs/my-env` then `cd ~/envs/my-env` (direnv loads venv + `SPA_*`; otherwise `source "$SPA_HOME/bin/spa_venv.sh" --env DIR` and `eval "$(spa env --export)"`). Prefix install: `spa init --software-dir ~/Software --example … ENV`. Existing clone env: `spa init ~/envs/my-env` (migrates config/inventory/tfstate/`.vagrant`). |
| Config settings lookup | `spa features list` / `search QUERY` (concise decision guidance), `show ID`, then `show ID --keys` for schema types/constraints plus catalog notes (JSON: `spa --json features …`). Live AWS region/AMI/instance values come from `spa aws --json`, not schema enums. Skill writes snippets into `splunk_config.yml`; init only composes topology + provider. |
| Python env (Ansible, Pydantic) | `source bin/spa_venv.sh` (shared `SPA_HOME/.venv`; env `.venv` wins when present). Env dirs get an `.envrc` for direnv; `spa init` creates the venv if missing and runs `direnv allow` when direnv is installed. |
| Host tools (terraform, direnv, …) | `spa doctor` (also run at end of `spa init`; `--skip-doctor` to skip). Terraform only for AWS; VirtualBox checks Vagrant, VirtualBox, the driver match, and `vagrant-vbguest` (`virtualbox:` in config). Not brew ansible/pydantic — use `spa_venv`. |
| Validate before provision | `spa validate` (schema, Software/baseconfig/local apps, inventory, licenses pairing, playbook syntax) |
| Provision then deploy | `spa provision --yes && spa deploy --yes` (AWS or VirtualBox from the env dir) |
| Deploy Splunk only (hosts already up) | `spa deploy --yes` (optional `--hosts` names or roles). Fails if Software/baseconfig (or local app sources) are missing; fails if any `splunk_hosts` entry is missing from inventory; `spa provision --yes` first, or `--allow-unprovisioned` only when the operator asked (e.g. one host already up; interim until [#57](https://github.com/splunk/splunk-platform-automator/issues/57)). |
| Run a playbook | `spa run --list`, `spa run NAME --help`, then `spa run NAME --yes` when `requires_confirmation` |
| Pause/resume compute | `spa suspend --yes` / `spa resume --yes` (optional `--hosts`; AWS keeps Terraform state and EBS; VirtualBox is `vagrant halt` / `vagrant up`) |
| List / SSH / copy | `spa hosts list --status`, `spa hosts ssh NAME`, `spa hosts copy SRC DST` (`spa sh` / `spa shell` still SSH) |
| Destroy managed infrastructure | `spa destroy --yes` (env-wide; later `--all` vs `--hosts` decommission) |
| VirtualBox | Same loop as AWS after `spa init --example single_node --provider virtualbox ENV`. Vagrantfile in `SPA_HOME`; `.vagrant` in the env. |
| Install framework (operators) | [docs/Install.md](docs/Install.md); `install.sh` from `releases/latest/download` (default `${XDG_DATA_HOME:-~/.local/share}/spa`) or extract `spa-framework-*.tar.gz` |
| Local tests | `./tests/run_local_tests.sh` |
| Release | [RELEASE.md](RELEASE.md), `./scripts/release.sh --check` |

Infrastructure commands select a provider from `splunk_config.yml`: `terraform.aws` or `virtualbox`.

## Agent skills (portable packages)

Canonical location: `skills/spa/` ([Agent Skills spec](https://agentskills.io/specification.md)).

| Skill | When to load |
|-------|----------------|
| [skills/spa/spa-create-config/SKILL.md](skills/spa/spa-create-config/SKILL.md) | Creating/updating `splunk_config.yml`, architecture planning, SVA topology, AWS `terraform.aws`, licenses, apps |
| [skills/spa/spa-add-test-scenario/SKILL.md](skills/spa/spa-add-test-scenario/SKILL.md) | App-scope routing tests in `tests/configs/app_scope/` |

**Cursor:** skills are symlinked under `.cursor/skills/` — use `/spa-create-config` and `/spa-add-test-scenario`.

**Other tools:** see [docs/Agent_Skills.md](docs/Agent_Skills.md) and [skills/spa/README.md](skills/spa/README.md).

## Secrets (mandatory)

Never display credential values in chat or terminal output.

- Splunkbase: `SPLUNKBASE_USERNAME`, `SPLUNKBASE_PASSWORD` — report **set** / **not set** only; in YAML use `lookup('env', ...)`.
- AWS: prefer `spa aws --check-auth --json`; never echo `AWS_SECRET_ACCESS_KEY` or similar.

Full rules: [skills/spa/spa-create-config/references/secrets-handling.md](skills/spa/spa-create-config/references/secrets-handling.md).

## Do not

- Auto-run provision, deploy, suspend, resume, or destroy without explicit user approval.
- Echo, `printenv`, or `grep` secret environment variables.
- Paste Splunkbase passwords or AWS secret keys into configs or chat.

## Layout

```text
ansible/          Playbooks and roles (SPA_HOME)
bin/              spa, spa_venv.sh
lib/spa/          spa CLI implementation
config/           splunk_config.yml lives in SPA_ENV_DIR (not in the clone for spa)
saved_base_config_apps/  optional pull-back of rendered PS apps (env dir)
examples/         Example configs and configuration_description.yml
skills/spa/       Agent skill packages (canonical)
tests/            Schema, local, and AWS deployment tests
```

**Path contract:** `SPA_HOME` is this checkout (framework). `SPA_ENV_DIR` is an environment dir (`config/`, `.spa.yml`, `inventory/`, Terraform state, `.vagrant/`, optional `saved_base_config_apps/`). Unset both still resolves to the clone for contributor `ansible-playbook`; `spa` operator commands refuse that layout (`spa init` first). When they differ, do not write env state into the prefix. Software/baseconfig/apps live out of band: `spa init --software-dir` saves `${XDG_CONFIG_HOME:-~/.config}/spa/paths.yml` (not secrets) and copies into env `.spa.yml`. Discovery still prefers a sibling of the **env**, then the clone. `.spa.yml` may set `software_dir`, `baseconfig_dir`, `apps_dir`. Config-file overrides: `splunk_dirs.splunk_software_dir`, `splunk_dirs.splunk_baseconfig_dir`, `splunk_app_deployment.local_app_repo_path`. Pulled-back PS apps: `splunk_apps.splunk_save_baseconfig_apps_dir` (default `saved_base_config_apps` under the env). See [Multiple environments, one clone](README.md#multiple-environments-one-clone).

## CLI, backend, GUI, and skills

One backend (`spa.api.LocalSpaSession` via `open_session()`). Two clients:

- **Skills and agents** call only `bin/spa` (`spa validate --json`, `spa agent schema`, `spa provision --yes && spa deploy --yes`). They must not import `spa.api` or talk to a daemon. Mutating commands require `--yes`; agents never answer an interactive prompt.
- **A future GUI** talks to the backend (`open_session()` in-process, or a later daemon wrapping the same session). It does not shell out to `spa` for ordinary operations.

The CLI is also a backend client (parse argv → session → print / JSON envelope). `open_session(url=...)` is reserved for a later remote controller; do not start a daemon unless that work is explicit. Env dirs and Ansible/Terraform stay on the machine that runs `LocalSpaSession`. A later thin laptop `spa` can use `SPA_CONTROLLER` so skills still run `spa` against remote env dirs. The compatibility, transport, confirmation, and security contract is documented in [Controller, GUI, and remote-client architecture](docs/Controller_Architecture.md).

`--hosts` on `deploy`, `run`, `suspend`, `resume`, and `hosts list` takes inventory names or roles (for example `indexer`). `spa validate` and `spa deploy` fail when Software/baseconfig dirs (and PS baseconfig apps) are missing, or when `source: local` apps are configured but `apps_dir` or the named app sources are missing. `spa deploy` also fails if any config host is missing from inventory unless the operator asked for `--allow-unprovisioned`. Discover playbooks with `spa --json run --list` then `spa run NAME --help`. If `requires_confirmation` is true, pass `--yes`. Skills should use full command names (`spa hosts ssh`, `spa validate`), not short aliases (`spa sh`, `spa val`). Do not remove a live host from `splunk_config.yml` and run `spa provision` — Terraform will terminate that instance until the provision destroy-guard exists (see ROADMAP).
