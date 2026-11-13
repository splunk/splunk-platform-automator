# Splunk Platform Automator — agent guide

SPA provisions and deploys Splunk Enterprise (AWS Linux + Terraform, or VirtualBox) from testing through production. Config is `$SPA_ENV_DIR/config/splunk_config.yml`. Operators and agents use **`spa` only**.

## Contract

- **`SPA_HOME`**: framework (prefix or clone). **`SPA_ENV_DIR`**: one environment. Operator `spa` needs `spa init` first. Path diagram: [user guide](docs/user-guide.md#understand-the-paths).
- Call **`bin/spa`** only (`spa --agent schema`, `spa --agent config search QUERY`, `spa --agent apps`). Do not import `spa.api`. Do not start a daemon. Flag catalog: `spa --agent schema` / `spa --no-agent agent schema`.
- Do not hand-edit `splunk_config.yml`. Change it with `spa config ...` (skill `/spa-create-config`) and add apps with `spa apps ...` (skill `/spa-apps`).
- Mutating commands need **`--yes`**. Never auto-run deploy, suspend, resume, or destroy. Exception: `/spa-create-config` Phase 14 option A hands off to `/spa`, which runs `deploy` only after an explicit yes in chat. Never answer `Proceed?` interactively.
- Never print secrets (Splunkbase, AWS keys, vault). Report env vars as **set / not set**. YAML: `lookup('env', ...)`. Do not pass `-v` on deploy/run (unredacted Ansible stdout).
- Full command names (`spa hosts ssh`, `spa validate`), not `spa sh` / `spa val`.
- Playbooks: `spa --agent run list` then `spa run NAME --help`. Confirmation: `--yes`. Extra Ansible args: `spa run NAME -- …`.

Load **`/spa`** only for a Splunk lab, Splunk environment, or env lifecycle (including deploy to existing hosts). Do not load it for contributor work on spa itself.

Human loop (same as README): [docs/quick-start.md](docs/quick-start.md).

## Install from this checkout

When this directory has `ansible.cfg` and `bin/spa` and spa is not yet usable (in-place venv; `./install.sh` stays the prefix path):

1. `bin/spa venv create --shared --yes` (clone is `SPA_HOME`)
2. `spa skills install` (or `spa skills install cursor`)
3. `spa doctor` — surface every WARN/FAIL Software row; do not download; do not `spa init` / `spa deploy` until Enterprise + UF tarballs and extracted PS baseconfigs are present (licenses may stay absent for a trial lab)
4. If Software is not a sibling of the env or of `SPA_HOME`: `spa environment set --software-dir DIR`. If the PS `baseconfigs/` tree is not a sibling: `spa environment set --baseconfig-dir DIR`

## Install from a repo URL

If this directory is not an SPA checkout (`ansible.cfg` + `bin/spa` absent): do not `git clone`. Use `curl -fsSL https://github.com/splunk/splunk-platform-automator/releases/latest/download/install.sh | sh` (or `./install.sh` / `./install.sh --from tarball` when the script is already local). Add `~/.local/bin` to `PATH` if `spa` is not found. Then `spa skills install` and `spa doctor`: do not download; do not `spa init` / `spa deploy` until Enterprise + UF tarballs and extracted PS baseconfigs are present (licenses may stay absent for a trial lab). If Software is not a sibling of the env or of `SPA_HOME`: `spa environment set --software-dir DIR`. If the PS `baseconfigs/` tree is not a sibling: `spa environment set --baseconfig-dir DIR`.

## Start here

| Task | Command |
| --- | --- |
| Init | `spa init --example TOPOLOGY --provider aws|virtualbox|external NAME` |
| Validate | `spa validate` |
| Deploy | `spa deploy --yes` |
| Logs | `spa logs list` / `spa logs --last` |
| Hosts | `spa hosts list --status`, `spa hosts ssh NAME` |
| Destroy | `spa destroy --yes` |
| Schema | `spa --no-agent agent schema --markdown`, `spa --no-agent config schema --markdown` |

Other flags: `spa --agent schema`. Provider is `terraform.aws`, `virtualbox:`, or `ccm:` in config.

## Skills

Canonical: `skills/spa/`. Load [spa](skills/spa/spa/SKILL.md) (`/spa`) for a Splunk lab (use spa, not the AWS CLI). [spa-create-config](skills/spa/spa-create-config/SKILL.md) for `splunk_config.yml`. [spa-apps](skills/spa/spa-apps/SKILL.md) for Splunkbase. Install with `spa skills install`. See [docs/contributing.md](docs/contributing.md#agent-skills). Backend vs GUI: [docs/architecture.md](docs/architecture.md#controller-architecture).

## Changing spa

Contributor work: Read [token-budget.md](skills/spa/spa/references/token-budget.md) before the first tool call. Procedure: [Feature development lifecycle](docs/architecture.md#feature-development-lifecycle), [Test-driven development](docs/architecture.md#test-driven-development), [Feature completion review](docs/architecture.md#feature-completion-review), [contribute.md](skills/spa/spa/references/contribute.md). New command: [Adding a spa command](docs/contributing.md#adding-a-spa-command) (`./tests/run_cli_tests.sh`). New config key: [Adding a configuration feature](docs/contributing.md#adding-a-configuration-feature).

- One plan todo per implement chat. After the parent review, stop. Next slice is a new chat.
- After compaction, start a new chat. Do not continue a compacted implement thread.
- At most one explore subagent, including Plan mode. Do not fan out parallel explorers.
- Do not load `/spa` or Read a `SKILL.md` when changing spa itself.
- Discover flags with `spa --agent schema`. Do not Read `lib/spa/cli.py`.
- Skills live only under `skills/spa/`. Examples, help, errors, and schema descriptions never contain passwords, tokens, private keys, or certificates. Use `lookup('env', ...)`.
