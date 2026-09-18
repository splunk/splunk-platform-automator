# Splunk Platform Automator — agent guide

SPA provisions and deploys Splunk Enterprise (AWS Linux + Terraform, or VirtualBox) from testing through production. Config is `$SPA_ENV_DIR/config/splunk_config.yml`. Operators and agents use **`spa` only**.

## Contract

- **`SPA_HOME`**: framework (prefix or clone). **`SPA_ENV_DIR`**: one environment. Operator `spa` needs `spa init` first. Path diagram: [user guide](docs/user-guide.md#understand-the-paths).
- Call **`bin/spa`** only (`spa agent schema`, `spa --json features`, `spa --json apps`). Load **`/spa`** first ([skills/spa/spa/SKILL.md](skills/spa/spa/SKILL.md)). Do not import `spa.api`. Do not start a daemon. Flag catalog: [docs/commands.md](docs/commands.md).
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Never answer `Proceed?` interactively.
- Never print secrets (Splunkbase, AWS keys, vault). Report env vars as **set / not set**. YAML: `lookup('env', ...)`. Do not pass `-v` on provision/deploy/run (unredacted Ansible stdout).
- Full command names (`spa hosts ssh`, `spa validate`), not `spa sh` / `spa val`.
- Playbooks: `spa --json run --list` then `spa run NAME --help`. Confirmation: `--yes`. Extra Ansible args: `spa run NAME -- …`.

Human loop (same as README): [docs/user-guide.md](docs/user-guide.md).

## Start here

| Task | Command / path |
| --- | --- |
| Config | `$SPA_ENV_DIR/config/splunk_config.yml` via `spa init --example` |
| Schema vs catalog | Pydantic (`spa validate`); `spa features` / `examples/catalog/features.yml` |
| CLI flags | [docs/commands.md](docs/commands.md) (`spa --no-agent agent schema --markdown`) |
| Guided design | [docs/user-guide.md](docs/user-guide.md#configure-an-environment) · `spa features` |
| 2.x → 3.0 | [docs/migrate.md](docs/migrate.md) |
| New env | `spa environment init --example cm_2idxc_sh_uf NAME` then `spa --env NAME …`, `spa environment set --default NAME`, or `cd` into it |
| Features / apps | `spa --json features search QUERY`; `spa --json apps search QUERY` then `snippet APP_ID`. AWS live values: `spa aws --json` |
| Python | `spa venv --shared --create --yes` (`spa init` creates it when missing) |
| Repair Python venv | `spa venv --shared --reinstall --yes` (or `--rebuild`) |
| Upgrade Python/Ansible in the venv | `spa venv --shared --upgrade --yes` |
| Host tools | `spa doctor` |
| Validate | `spa validate` |
| Provision + deploy | `spa provision --yes && spa deploy --yes` |
| Deploy only | `spa deploy --yes` (`--hosts`; `--allow-unprovisioned` only if the operator asked) |
| Run a playbook | `spa run --list` / `NAME --help` / `--yes` |
| Run logs | `spa logs` / `spa logs --last` (open `data.log` only when debugging a failure). Do not pass `-v` (unredacted Ansible stdout). |
| Power | `spa suspend --yes` / `spa resume --yes` |
| SSH / copy | `spa hosts list --status`, `spa hosts ssh NAME`, `spa hosts copy SRC DST` |
| Destroy | `spa destroy --yes` |
| VirtualBox | `spa init --example single_node --provider virtualbox ENV` then the same spa loop |
| Install | [README](README.md#install) · [docs/install.md](docs/install.md) |
| Tests / release | `./tests/run_local_tests.sh` · [RELEASE.md](RELEASE.md) |

Provider is `terraform.aws` or `virtualbox:` in config.

`--hosts` on deploy, run, suspend, resume, hosts list: inventory names or roles. Missing Software/baseconfig/local apps or unprovisioned hosts: fail as today (see user guide). Do not delete a live host from config and `spa provision` (ROADMAP destroy-guard).

## Skills

Canonical: `skills/spa/`. When to load:

| Skill | When |
| --- | --- |
| [spa](skills/spa/spa/SKILL.md) (`/spa`) | Load first: Software, env lifecycle, operator loop |
| [spa-create-config](skills/spa/spa-create-config/SKILL.md) | `splunk_config.yml` in an existing env |
| [spa-apps](skills/spa/spa-apps/SKILL.md) | Splunkbase search / snippet / download |
| [spa-add-test-scenario](skills/spa/spa-add-test-scenario/SKILL.md) | App-scope tests |

Cursor: `/spa`, `/spa-create-config`, `/spa-apps`, `/spa-add-test-scenario`. See [docs/contributing.md](docs/contributing.md#agent-skills).

Backend vs GUI: [docs/contributing.md](docs/contributing.md#controller-architecture).
