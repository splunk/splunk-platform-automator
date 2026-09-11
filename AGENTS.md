# Splunk Platform Automator — agent guide

Splunk Platform Automator (SPA) provisions and deploys Splunk Enterprise on **AWS Linux** using Ansible + Terraform. Configuration is driven by `config/splunk_config.yml`.

## Start here

| Task | Path / command |
|------|----------------|
| Main config | `config/splunk_config.yml` (copy from `examples/`) |
| Config keys reference | `examples/configuration_description.yml` |
| Guided human + agent workflow | [docs/Splunk_Config_Guided_Setup.md](docs/Splunk_Config_Guided_Setup.md) |
| New AWS lab (one clone, many labs) | `./bin/init_spa_dir.sh --example cm_2idxc_sh_uf_aws.yml ~/labs/my-lab` then `cd ~/labs/my-lab` (direnv loads venv + `SPA_*`; otherwise `source bin/spa_venv.sh --lab DIR` and `eval "$(./bin/spa_env.sh --start-dir DIR)"`). Existing clone env: `./bin/init_spa_dir.sh ~/labs/my-lab` (migrates config/inventory/tfstate). |
| Python env (Ansible, Pydantic) | `source bin/spa_venv.sh` (shared `SPA_HOME/.venv`; lab `.venv` wins when present). Labs get an `.envrc` for direnv; `init_spa_dir.sh` creates the venv if missing and runs `direnv allow` when direnv is installed. |
| Host tools (terraform, direnv, …) | `./bin/spa_doctor.sh` (also run at end of `init_spa_dir.sh`; `--skip-doctor` to skip). Terraform only for AWS labs; Vagrant only for VirtualBox (`virtualbox:` in config). Not brew ansible/pydantic — use `spa_venv`. |
| Validate before provision | `./bin/validate_splunk_config.sh` |
| Provision AWS | `ansible-playbook "$SPA_HOME/ansible/provision_terraform_aws.yml" -e auto_approve=true` |
| Deploy Splunk | `ansible-playbook "$SPA_HOME/ansible/deploy_site.yml"` |
| VirtualBox | Config in the **clone**; `vagrant up` from `SPA_HOME` only. Lab dirs have no Vagrantfile. |
| Local tests | `./tests/run_local_tests.sh` |
| Release | [RELEASE.md](RELEASE.md), `./scripts/release.sh --check` |

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

- Splunkbase: `SPLUNKBASE_USERNAME`, `SPLUNKBASE_PASSWORD` — report **set** / **not set** only in YAML use `lookup('env', ...)`.
- AWS: prefer `python3 bin/splunk_config_aws.py --check-auth --json`; never echo `AWS_SECRET_ACCESS_KEY` or similar.

Full rules: [skills/spa/spa-create-config/references/secrets-handling.md](skills/spa/spa-create-config/references/secrets-handling.md).

## Do not

- Auto-run provision, deploy, or destroy without explicit user approval.
- Echo, `printenv`, or `grep` secret environment variables.
- Paste Splunkbase passwords or AWS secret keys into configs or chat.

## Layout

```text
ansible/          Playbooks and roles (SPA_HOME)
bin/              init_spa_dir.sh, spa_env.sh, spa_venv.sh, spa_doctor.sh, validate_splunk_config.sh, …
config/           splunk_config.yml in the clone (gitignored) or in SPA_LAB_DIR
saved_base_config_apps/  optional pull-back of rendered PS apps (lab)
examples/         Example configs and configuration_description.yml
skills/spa/       Agent skill packages (canonical)
tests/            Schema, local, and AWS deployment tests
```

**Path contract:** `SPA_HOME` is this checkout (framework). `SPA_LAB_DIR` is a lab (`config/`, `.spa.yml`, `inventory/`, Terraform state, optional `saved_base_config_apps/`). Unset both → the clone; existing `ansible-playbook` usage is unchanged. When they differ, do not write lab state into the prefix. `../Software` and `../apps` prefer a sibling of the **lab**, then the clone (`Software/` sibling or `$SPA_HOME/apps`). `.spa.yml` may set `software_dir`, `baseconfig_dir`, `apps_dir`. Config-file overrides: `splunk_dirs.splunk_software_dir`, `splunk_dirs.splunk_baseconfig_dir`, `splunk_app_deployment.local_app_repo_path`. Pulled-back PS apps: `splunk_apps.splunk_save_baseconfig_apps_dir` (default `saved_base_config_apps` under the lab). See [Multiple labs, one clone](README.md#multiple-labs-one-clone).
