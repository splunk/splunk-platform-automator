# Migrate existing Splunk Platform Automator Environments from 2.x to 3.0

3.0 is not a Splunk-config rewrite. Operators always use an env dir (`spa init`) and the **`spa`** CLI. The git clone is `SPA_HOME` (framework) only; clone-equal `SPA_HOME`/`SPA_ENV_DIR` is not valid for operator `spa`.

This is the short “what do I change?” list. Full release history is in [CHANGELOG.md](../CHANGELOG.md).

## Commands and `bin/`

Only `bin/spa` and `bin/spa_venv.sh` remain in a clone. Operators can install a prefix with `install.sh` instead of cloning ([Install](install.md)). Source the venv script; do not invoke the old wrappers.

| 2.x | 3.0 |
| --- | --- |
| `bin/spash` | `spa hosts ssh NAME` (aliases: `spa sh`, `spa shell`) |
| `bin/spash -l` | `spa hosts list` (optional `--status`) |
| `bin/spash -c` | `spa hosts copy SRC DST` (`spa shell -c` still copies) |
| `bin/init_spa_dir.sh` | `spa init` |
| `bin/spa_env.sh` | Not needed by `spa`; `spa env --export` remains for external tools |
| `bin/spa_doctor.sh` | `spa doctor` |
| `bin/validate_splunk_config.sh` | `spa validate` |
| `bin/splunk_config_aws.py` | `spa aws` |
| `bin/splunk_config_licenses.py` | `spa licenses` |

`spa shell` stays as an SSH alias. There is no `spa shell -l`; list hosts with `spa hosts list`.

Skills and agents should use full names (`spa hosts ssh`, `spa validate`), not `spa sh` / `spa val`.

## Names and flags

- `--lab` is `--env` (for example `spa doctor --env NAME` or a dest path). `spa environment` is the env family; `spa env` is its alias.
- `SPA_LAB_DIR` is gone. Use `SPA_ENV_DIR`. There is no alias.
- Jinja `SPADirName` is `spa_env_dir | basename`.

## Path contract

- **`SPA_HOME`** is the framework (playbooks, Terraform modules, `Vagrantfile`, `bin/`, skills). A clone is develop-only for `spa`; operators use a prefix or clone as home, never as the env.
- **`SPA_ENV_DIR`** is one Splunk environment (`config/splunk_config.yml`, optional `.spa.yml`, `inventory/hosts`, Terraform state, `.vagrant/`, optional `saved_base_config_apps/`). Do not copy `ansible/` into the env. Do not put a Vagrantfile in the env.
- Unset both → cwd discovery and then the registered default select the env. A clone-equal layout is **not** valid for operator commands.
- When they differ, Terraform **modules** stay under `$SPA_HOME/terraform/aws`; **state** stays in the env. VirtualBox uses `VAGRANT_CWD=$SPA_HOME` and `VAGRANT_DOTFILE_PATH=$SPA_ENV_DIR/.vagrant`.
- `../Software` and `../apps` prefer a sibling of the **env**, then the clone.
- Env dirs do not get an `.envrc`. Install the `spa` launcher once; each command resolves cwd or `--env NAME` and applies its own environment.

Move an existing 2.x clone env out of the checkout:

```bash
spa init ~/envs/my-env
# or from a new framework tree:
spa init --from /path/to/old-clone ~/envs/my-env
cd ~/envs/my-env
spa validate
```

`spa init` migrates `config/`, `inventory/`, Terraform state, and **`.vagrant/`** (VirtualBox machine IDs). If `.vagrant` is left in the clone, `spa provision` would create a second set of VMs.

If you copied a whole old checkout as the env directory, `spa init DIR` exits 2 until `--force`. Then env state is kept and framework leftovers under that dir are stripped. After conversion (or for any older lab that already has config), `spa env init NAME --force` registers that directory so it appears in `spa environment list`.

## Python / Ansible

Do not use Homebrew Ansible or Pydantic. Recreate the shared venv:

```bash
spa venv --shared --rebuild --yes
```

Use `spa venv --shared --reinstall --yes` when the venv itself is sound and
only missing packages need filling in. Use `spa venv --shared --upgrade --yes`
to bump Ansible and other requirements in place (`pip install --upgrade` plus
`ansible-galaxy collection install --upgrade`). `boto3` is in `requirements.txt`.

## AWS and VirtualBox

- `spa provision`, `spa destroy`, `spa suspend`, and `spa resume` follow `splunk_config.yml`: **`terraform.aws`** or **`virtualbox:`**. Same env-dir loop for both.
- A top-level `aws:` block is inventory-only (legacy vagrant-aws). vagrant-aws is removed in 3.0; use Terraform AWS for cloud.
- VirtualBox env dirs have no `Vagrantfile`; provision and deploy through `spa`.

Playbooks are invoked with `spa run NAME` (discover: `spa run --list`). Site deploy is `spa deploy --yes`.

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

First-party playbooks carry a `# spa-run:` comment. `spa run NAME --help` prints it; `spa --json run --list` includes `summary` / `risk` / `category` / `requires_provisioned`. Set `requires_provisioned: true` when the playbook needs live hosts; omit it (or `false`) for controller-only stems such as `aws_provision`.

## Already in 2.5.x

If you jump from an older 2.x (before 2.5) to 3.0:

- `splunk_license_file` and a `license_manager` host are both required (and the reverse).
- Deploy runs a fact-cache preflight (`spa_preflight_deploy`, default on).

## Coming from 1.x

SPA 2.0 introduced a dynamic Ansible inventory plugin and moved topology into `splunk_config.yml`. Before going to 3.0, first ensure the old config includes `plugin: splunk-platform-automator` and that values formerly held in static `inventory/group*` files are represented in config.

For VirtualBox, `start_ip` moved from `general` to `virtualbox`. For old Ansible-only environments, export the effective inventory before migration and compare it with `spa hosts list` afterwards.

The 1.x AWS path depended on vagrant-aws tags and is no longer an operator path. Do not reproduce the old tagging/Vagrant procedure on 3.0. Inventory-only AWS leftovers must be redesigned as `terraform.aws` or registered as external hosts; see [AWS](aws.md).

## Splunk 9 terminology

Update old config and local apps to current Splunk terminology:

- role `cluster_master` → `cluster_manager`
- role `license_master` → `license_manager`
- clustering mode `master`/`slave` → `manager`/`peer`
- `master_uri` → `manager_uri`
- `clustermaster` stanzas → `clustermanager`

SPA applies current terms in generated configuration for Splunk 9+, but custom/local apps remain your responsibility.
