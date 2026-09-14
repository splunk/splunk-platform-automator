# Migrate existing Splunk Platform Automator Environments from 2.x to 3.0

3.0 is not a Splunk-config rewrite. Day-to-day `ansible-playbook` from a clone still works when `SPA_HOME` and `SPA_ENV_DIR` are the same directory. What changes is the **operator surface**: one `spa` binary, a split between framework and environment directories, and AWS lifecycle through Terraform.

Keep this page as the short “what do I change?” list. Full history is in [CHANGELOG.md](../CHANGELOG.md). 1.x → 2.x inventory work is still [Migrate_SPA_1x_to_2x.md](Migrate_SPA_1x_to_2x.md).

## Commands and `bin/`

Only `bin/spa` and `bin/spa_venv.sh` remain. Source the venv script; do not invoke the old wrappers.

| 2.x | 3.0 |
| --- | --- |
| `bin/spash` | `spa hosts ssh NAME` (aliases: `spa sh`, `spa shell`) |
| `bin/spash -l` | `spa hosts list` (optional `--status`) |
| `bin/spash -c` | `spa hosts copy SRC DST` (`spa shell -c` still copies) |
| `bin/init_spa_dir.sh` | `spa init` |
| `bin/spa_env.sh` | `spa env --export` |
| `bin/spa_doctor.sh` | `spa doctor` |
| `bin/validate_splunk_config.sh` | `spa validate` |
| `bin/splunk_config_aws.py` | `spa aws` |
| `bin/splunk_config_licenses.py` | `spa licenses` |

`spa shell` stays as an SSH alias. There is no `spa shell -l`; list hosts with `spa hosts list`.

Skills and agents should use full names (`spa hosts ssh`, `spa validate`), not `spa sh` / `spa val`.

## Names and flags

- `--lab` is `--env` (for example `spa doctor --env DIR`).
- `SPA_LAB_DIR` is gone. Use `SPA_ENV_DIR`. There is no alias.
- Jinja `SPADirName` is `spa_env_dir | basename`.

## Path contract

- **`SPA_HOME`** is the framework (playbooks, Terraform modules, `bin/`, skills).
- **`SPA_ENV_DIR`** is one Splunk environment (`config/splunk_config.yml`, optional `.spa.yml`, `inventory/hosts`, Terraform state, optional `saved_base_config_apps/`). Do not copy `ansible/` into the env.
- Unset both → the git clone (same layout as 2.x).
- When they differ, Terraform **modules** stay under `$SPA_HOME/terraform/aws`; **state** stays in the env.
- `../Software` and `../apps` prefer a sibling of the **env**, then the clone.
- Env dirs get an `.envrc`. `spa` is `$SPA_HOME/bin/spa` on `PATH`, not a per-env `bin/`.

Move an existing clone env out of the checkout:

```bash
spa init ~/envs/my-env
# or from a new framework tree:
spa init --from /path/to/old-clone ~/envs/my-env
cd ~/envs/my-env
eval "$(spa env --export)"
spa validate
```

If you copied a whole old checkout as the env directory, `spa init DIR` exits 2 until `--force`. Then env state is kept and framework leftovers under that dir are stripped.

## Python / Ansible

Do not use Homebrew Ansible or Pydantic. Create or refresh the venv:

```bash
source bin/spa_venv.sh --create
```

`boto3` is in `requirements.txt`. Recreate older venvs so `spa aws`, suspend/resume, and `spa hosts list --status` work.

## AWS and VirtualBox

- `spa provision`, `spa destroy`, `spa suspend`, and `spa resume` require **`terraform.aws`** in `splunk_config.yml`. A top-level `aws:` block is inventory-only (legacy vagrant-aws).
- vagrant-aws is not the 3.0 path. Use Terraform AWS for new work.
- VirtualBox is not managed by `spa` yet. Keep `virtualbox:` config in the **clone** and run `vagrant` from `SPA_HOME`. Env dirs have no `Vagrantfile`; `vagrant up` from `~/envs/...` is unsupported.

Recommended AWS loop:

```bash
spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env
cd ~/envs/my-env
spa validate
spa provision --yes && spa deploy
```

`ansible-playbook ansible/deploy_site.yml` still works from a clone after `eval "$(spa env --export)"`. Default docs and agents use `spa`.

## Host targeting

`--hosts` on `deploy`, `run`, `suspend`, `resume`, and `hosts list` takes inventory names or roles (for example `indexer`). That is not Ansible `--limit` in user help; playbooks still receive `--limit` internally.

Do not delete a live host from `splunk_config.yml` and run `spa provision`. Terraform will terminate that instance. Later work will refuse instance destroys on provision and add `spa destroy --hosts` / `--all` (see [ROADMAP.md](../ROADMAP.md)).

## Playbook stems (3.0)

`spa run --list` shows current names. `spa run OLD` still resolves and prints `use spa run NEW`. Prefer `spa provision` / `spa destroy` / `spa deploy` over running the AWS or site pipeline playbooks directly.

| 2.x | 3.0 |
| --- | --- |
| `start_splunk` | `splunk_start` |
| `stop_splunk` | `splunk_stop` |
| `restart_splunk` | `splunk_restart` |
| `run_splunk_command` | `splunk_cli` |
| `call_splunk_rest` | `splunk_rest` |
| `install_splunk` | `splunk_install` |
| `remove_splunk` | `splunk_remove` |
| `enable_splunkweb` | `splunk_web_enable` |
| `disable_stop_splunkweb` | `splunk_web_disable` |
| `add_splunk_license` | `splunk_license` |
| `backup_splunk_etc` | `splunk_backup_etc` |
| `cleanup_backup_dir` | `splunk_backup_cleanup` |
| `update_splunk_certs_web` | `splunk_certs_web` |
| `update_splunk_certs_inputs` | `splunk_certs_inputs` |
| `setup_splunk_roles` | `splunk_setup_roles` |
| `setup_splunk_conf` | `splunk_setup_conf` |
| `upgrade_splunk_shc_rolling` | `upgrade_shc_rolling` |
| `upgrade_splunk_idxc_rolling` | `upgrade_idxc_rolling` |
| `upgrade_splunk_dist_env` | `upgrade_distributed` |
| `provision_terraform_aws` | `aws_provision` |
| `destroy_terraform_aws` | `aws_destroy` |
| `wait_for_terraform_aws_hosts` | `aws_wait_hosts` |
| `deploy_splunk_apps` | `splunk_apps_deploy` |
| `remove_splunk_apps` | `splunk_apps_remove` |
| `run_apps_playbook` | `splunk_apps_playbook_run` |
| `install_ssh_keys` | `ssh_keys` |
| `test_ansible_prereqs` | `ansible_check` |

Unchanged: `deploy_site`, `preflight_deploy`, `setup_common`, `create_linkpage`, `setup_other_roles`, `update_hosts_file`, `upgrade_splunk`.

First-party playbooks carry a `# spa-run:` comment. `spa run NAME --help` prints it; `spa --json run --list` includes `summary` / `risk` / `category`.

## Already in 2.5.x

If you jump from an older 2.x (before 2.5) to 3.0:

- `splunk_license_file` and a `license_manager` host are both required (and the reverse).
- Deploy runs a fact-cache preflight (`spa_preflight_deploy`, default on).
