# Splunk Platform Automator — agent guide

SPA provisions and deploys Splunk Enterprise (AWS Linux + Terraform, or VirtualBox) from testing through production. Config is `$SPA_ENV_DIR/config/splunk_config.yml`. Operators and agents use **`spa` only**.

## Contract

- **`SPA_HOME`**: framework (prefix or clone). **`SPA_ENV_DIR`**: one environment. Operator `spa` needs `spa init` first. Path diagram: [user guide](docs/user-guide.md#understand-the-paths).
- Call **`bin/spa`** only (`spa agent schema`, `spa --json config search QUERY`, `spa --json apps`). Load **`/spa`** first ([skills/spa/spa/SKILL.md](skills/spa/spa/SKILL.md)). Do not import `spa.api`. Do not start a daemon. Flag catalog: [docs/commands.md](docs/commands.md).
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Never answer `Proceed?` interactively.
- Never print secrets (Splunkbase, AWS keys, vault). Report env vars as **set / not set**. YAML: `lookup('env', ...)`. Do not pass `-v` on provision/deploy/run (unredacted Ansible stdout).
- Full command names (`spa hosts ssh`, `spa validate`), not `spa sh` / `spa val`.
- Playbooks: `spa --json run list` then `spa run NAME --help`. Confirmation: `--yes`. Extra Ansible args: `spa run NAME -- …`.

Human loop (same as README): [docs/user-guide.md](docs/user-guide.md).

## Start here

| Task | Command / path |
| --- | --- |
| Config | `$SPA_ENV_DIR/config/splunk_config.yml` via `spa init --example` |
| Schema vs catalog | Pydantic (`spa validate`); `spa config search` then `spa config explain PATH` |
| New config key | [docs/contributing.md](docs/contributing.md#adding-a-configuration-feature) |
| All settings | [docs/config.md](docs/config.md) (`spa --no-agent config schema --markdown`) |
| CLI flags | [docs/commands.md](docs/commands.md) (`spa --no-agent agent schema --markdown`) |
| Guided design | [docs/user-guide.md](docs/user-guide.md#configure-an-environment) · `spa config search` then `spa config explain` |
| 2.x → 3.0 | [docs/migrate.md](docs/migrate.md) |
| New env | `spa environment init --example cm_2idxc_sh_uf NAME` then `spa --env NAME …`, `spa environment set --default NAME`, or `cd` into it |
| Features / apps | `spa --json config search QUERY`; `spa --json apps search QUERY` then `snippet APP_ID`. For 5391: `spa --json apps content-packs list 5391`. AWS live values: `spa aws --json` |
| Python | `spa venv --shared --create --yes` (`spa init` creates it when missing) |
| Repair Python venv | `spa venv --shared --reinstall --yes` (or `--rebuild`) |
| Upgrade Python/Ansible in the venv | `spa venv --shared --upgrade --yes` |
| Host tools | `spa doctor` |
| Validate | `spa validate` |
| Provision + deploy | `spa provision --yes && spa deploy --yes` |
| Deploy only | `spa deploy --yes` (`--hosts`; `--allow-unprovisioned` only if the operator asked) |
| Run a playbook | `spa run list` / `NAME --help` / `--yes` |
| Run logs | `spa logs list` / `spa logs RUN_ID` / `spa logs --last` (open `data.log` only when debugging a failure). Do not pass `-v` (unredacted Ansible stdout). |
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

Cursor: `/spa`, `/spa-create-config`, `/spa-apps`, `/spa-add-test-scenario` after `spa skills install`. See [docs/contributing.md](docs/contributing.md#agent-skills).

Backend vs GUI: [docs/architecture.md](docs/architecture.md#controller-architecture).

## Changing spa

- Feature lifecycle: before the first file edit, fetch and update the recorded base branch and create the feature branch. Never assume `distribution` or `master`. Record that base. A plan, a todo list, or an implement-this request does not skip these steps. For each behavior, add one test, run it alone, and see it fail before changing production code. Regenerate `docs/commands.md` or `docs/config.md` only after its drift test has failed. Leave the slice open until `./tests/run_local_tests.sh` passes. Follow [Test-driven development](docs/architecture.md#test-driven-development), [Feature completion review](docs/architecture.md#feature-completion-review), and [Feature development lifecycle](docs/architecture.md#feature-development-lifecycle). Do not commit until the user explicitly authorizes it. When the user says the feature is complete, concluded, or ready to ship, complete the independent review, run the gate, commit authorized changes, open the pull request against that recorded base, fix CI until green, merge, verify the base-branch pipeline, close the issue, and clean up both feature branches without requiring the user to enumerate those steps.
- New command: [Adding a spa command](docs/contributing.md#adding-a-spa-command). One parser per action. A catalog is `list`. Usage errors exit 2 and name the legal command. Human text goes to stderr. Agent mode (`--agent`, `--json`, or a detected agent) returns one JSON object `{"ok":false,"schema_version":1,"error":"..."}` and does not include `data`. Register the action in `COMMAND_SCHEMA` in the same change.
- New config key: [Adding a configuration feature](docs/contributing.md#adding-a-configuration-feature).
- [docs/commands.md](docs/commands.md) and [docs/config.md](docs/config.md) are generated. Do not hand-edit them. Regenerate `docs/commands.md` with `spa --no-agent agent schema --markdown` and `docs/config.md` with `spa --no-agent config schema --markdown`. [tests/test_docs.py](tests/test_docs.py) fails when they drift.
- CLI change gate: `./tests/run_cli_tests.sh`. Broader local gate: `./tests/run_local_tests.sh`. A parser change does not need an AWS run.
- Commands return `CommandResult`. Confirmation stays in the session. Agents call `bin/spa` and do not import `spa.api`. Do not add a second operator CLI or a remote controller ([controller architecture](docs/architecture.md#controller-architecture)).
- Skills live only under `skills/spa/`. Install them with `spa skills install`. Do not copy skill text into this repo.
- Examples, help, errors, and schema descriptions never contain passwords, tokens, private keys, or certificates. Use `lookup('env', ...)`.
