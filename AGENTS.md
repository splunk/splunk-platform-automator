# Splunk Platform Automator — agent guide

SPA provisions and deploys Splunk Enterprise (AWS Linux + Terraform, or VirtualBox) from testing through production. Config is `$SPA_ENV_DIR/config/splunk_config.yml`. Operators and agents use **`spa` only**.

## Contract

- **`SPA_HOME`**: framework (prefix or clone). **`SPA_ENV_DIR`**: one environment. Operator `spa` needs `spa init` first. Path diagram: [user guide](docs/user-guide.md#understand-the-paths).
- Call **`bin/spa`** only (`spa --agent schema`, `spa --agent config search QUERY`, `spa --agent apps`). Do not import `spa.api`. Do not start a daemon. Flag catalog: `spa --agent schema` / `spa --no-agent agent schema`.
- Do not hand-edit `splunk_config.yml`. Change it with `spa config ...` (skill `/spa-create-config`) and add apps with `spa apps ...` (skill `/spa-apps`).
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Exception: `/spa-create-config` Phase 14 option A hands off to `/spa`, which runs `provision`, then `deploy`, each only after its own explicit yes in chat. Never answer `Proceed?` interactively.
- Never print secrets (Splunkbase, AWS keys, vault). Report env vars as **set / not set**. YAML: `lookup('env', ...)`. Do not pass `-v` on provision/deploy/run (unredacted Ansible stdout).
- Full command names (`spa hosts ssh`, `spa validate`), not `spa sh` / `spa val`.
- Playbooks: `spa --agent run list` then `spa run NAME --help`. Confirmation: `--yes`. Extra Ansible args: `spa run NAME -- …`.

Load **`/spa`** only for a Splunk lab, Splunk environment, or env lifecycle (including deploy to existing hosts). Do not load it for contributor work on spa itself.

Human loop (same as README): [docs/user-guide.md](docs/user-guide.md).

## Start here

| Task | Command / path |
| --- | --- |
| Config | `$SPA_ENV_DIR/config/splunk_config.yml` via `spa init --example TOPOLOGY --provider aws|virtualbox|external NAME` |
| Schema vs catalog | Pydantic (`spa validate`); `spa config search` then `spa config explain PATH` |
| New config key | [docs/contributing.md](docs/contributing.md#adding-a-configuration-feature) |
| All settings | `spa --no-agent config schema --markdown` |
| CLI flags | `spa --no-agent agent schema --markdown` |
| Guided design | [docs/user-guide.md](docs/user-guide.md#configure-an-environment) · `spa config search` then `spa config explain` |
| 2.x → 3.0 | [docs/migrate.md](docs/migrate.md) |
| New env | `spa environment init --example cm_2idxc_sh --provider aws NAME` then `spa --env NAME …`, `spa environment set --default NAME`, or `cd` into it |
| Features / apps | `spa --agent config search QUERY`; `spa --agent apps search QUERY` then `snippet APP_ID`. For 5391: `spa --agent apps content-packs list 5391`. AWS live values: `spa --agent aws check-auth`, `regions list`, `latest-ami`, `survey` |
| Python | `spa venv create --shared --yes` (`spa init` creates it when missing) |
| Repair Python venv | `spa venv reinstall --shared --yes` (or `spa venv rebuild --shared --yes`) |
| Upgrade Python/Ansible in the venv | `spa venv upgrade --shared --yes` |
| Host tools | `spa doctor` |
| Validate | `spa validate` |
| Provision + deploy | `spa provision --yes && spa deploy --yes` |
| Deploy only | `spa deploy --yes` (`--hosts` checks only those hosts) |
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
| [spa](skills/spa/spa/SKILL.md) (`/spa`) | Splunk lab or environment request (any topology, OS, or CPU count), Splunk deploy to existing hosts, Software, env lifecycle, operator loop. Use spa, not the AWS CLI or Terraform. |
| [spa-create-config](skills/spa/spa-create-config/SKILL.md) | `splunk_config.yml` in an existing env |
| [spa-apps](skills/spa/spa-apps/SKILL.md) | Splunkbase search / snippet / download |

Cursor: `/spa`, `/spa-create-config`, `/spa-apps` after `spa skills install`. See [docs/contributing.md](docs/contributing.md#agent-skills). App-scope scenarios are in [tests/README.md](tests/README.md).

Backend vs GUI: [docs/architecture.md](docs/architecture.md#controller-architecture).

## Changing spa

At each gate, stop, name one next step, and wait. Completing todos is not authorization to implement, commit, or merge. Full procedure: [Feature development lifecycle](docs/architecture.md#feature-development-lifecycle), [Test-driven development](docs/architecture.md#test-driven-development), [Feature completion review](docs/architecture.md#feature-completion-review).

- Feature lifecycle: before the first file edit, fetch and update the recorded base branch and create the feature branch. Never assume `distribution` or `master`. Record that base. A plan, a todo list, or an implement-this request does not skip these steps. For each behavior, add one test, run it alone, and see it fail before changing production code. Regenerate generated catalogs only after its drift test has failed (`spa --no-agent agent schema --markdown`, `spa --no-agent config schema --markdown`). Close the slice on the required local gates (the new test, tests for every touched module, and `./tests/run_cli_tests.sh` when parser, help, routing, schema, session, or provider contracts changed). PR CI runs the full suite.
- Do not commit until the user explicitly authorizes it. When the user says the feature is complete, concluded, or ready to ship, that does not skip the review report, even when the user already said the feature is complete. Discuss what was found, what was fixed, and what was left out, and wait for the user to confirm the left-out items, then ask whether to commit. A completion request that arrived before the report is not that confirmation. Then ask before opening a PR, and again before merge.
- New command: [Adding a spa command](docs/contributing.md#adding-a-spa-command). CLI change gate: `./tests/run_cli_tests.sh`.
- New config key: [Adding a configuration feature](docs/contributing.md#adding-a-configuration-feature).
- Skills live only under `skills/spa/`. Install them with `spa skills install`.
- Examples, help, errors, and schema descriptions never contain passwords, tokens, private keys, or certificates. Use `lookup('env', ...)`.
