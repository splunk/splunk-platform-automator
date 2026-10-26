---
name: spa
description: Load first for Splunk Platform Automator — Software, registered environments, and the spa operator loop. Dispatch YAML/apps/tests to spa-create-config, spa-apps, spa-add-test-scenario.
---

# spa skill

Product entry for SPA (same role as cup’s main skill). **Load `/spa` first.** `spa skills install` links this package into the user IDE skill directory.

## When to use

Anything SPA: shared Software, registered environments, validate / provision / deploy / hosts / run. Task skills apply **after** an env exists, for that env’s YAML, Splunkbase apps, or app-scope tests.

## Contract

- **`SPA_HOME`**: framework. **`SPA_ENV_DIR`**: one environment. Call **`bin/spa` only**. Do not import `spa.api`. Do not start a daemon.
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Never answer `Proceed?`.
- Never print secrets. Report env vars as set / not set. YAML: `lookup('env', ...)`. Do not pass `spa -v` (unredacted Ansible stdout).
- Full command names (`spa environment list`, `spa hosts ssh`, `spa validate`). Humans may type `spa env`.
- No `ansible-playbook` / raw Vagrant for operators.

Discovery: `spa agent schema` / [docs/commands.md](../../../docs/commands.md). All settings: [docs/config.md](../../../docs/config.md) (`spa --no-agent config schema --markdown`). Building `splunk_config.yml` follows the `spa-create-config` loop: discover with `spa --agent config search QUERY` and `spa --agent config explain PATH`. `spa --agent config explain PATH` returns that feature's one mutation command and does not apply it. Update an existing path with `spa --agent config set`, append a new non-app identity with `spa --agent config add SELECTOR JSON_OBJECT`, or send a deliberate fragment with `spa --agent config merge --file FILE`, then run `spa --agent validate`. App entries use `spa --agent apps add`. Catalog snippets are examples and are never applied implicitly. Explain paths omit empty brackets (`splunk_hosts`, `splunk_app_deployment.apps.premium_app`). Mutation selectors such as `splunk_hosts[name=NAME]` keep the identity. In zsh, quote a selector that contains `[]`. Playbooks: `spa --agent run list` then `spa run NAME --help`. Do not guess flags.

## Dispatch

| Work | Skill / command |
| --- | --- |
| Env lifecycle (init, list, set, remove, `--env`, validate, provision, deploy, power, destroy, hosts) | **this skill** (`/spa`) |
| Create or edit **`splunk_config.yml` only** (SVA, AWS YAML, licenses) | `spa-create-config` — not init, not deploy |
| Splunkbase search / snippet / download | `spa-apps` |
| App-scope tests | `spa-add-test-scenario` |

## Environments

Canonical: `spa environment` (alias `env`). `spa init` aliases `spa environment init`.

```bash
spa environment list
spa environment set --env-dir ~/work/spa-envs          # persist default parent (not ~/Splunk-Platform-Automator)
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa environment set --default my-lab                   # fallback when cwd does not select an env
spa environment set --provider virtualbox              # providers.yml; aws is implicit (no file)
spa environment init --example cm_2idxc_sh my-lab   # name-only under default parent
spa environment init --env-dir /custom --name my-lab   # one-off; does not change default parent
spa init /custom/my-lab                                # same dest as the line above
spa env init my-lab --force                            # adopt an existing env (cwd or default parent) into the list
spa --env my-lab validate
spa environment remove my-lab --yes                    # not spa destroy; --force if it looks deployed
```

`--name` is the registry key (default: folder basename). `spa` resolves `--env`, cwd, or the registered default and applies the required environment internally. `spa environment --export` is the canonical form for external tools. `spa env --export` remains the human alias.

## Software

One shared directory per machine, not inside `SPA_HOME` and not copied per env. Linux tgz installers, extracted PS baseconfig apps, optional `Splunk_Enterprise.lic`. Splunk / Cisco employees: [https://go2.cisco.com/baseconfigs](https://go2.cisco.com/baseconfigs). Others: Splunk PS. Checklist: [Prepare Software](../../../docs/user-guide.md#prepare-software).

```bash
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa venv reinstall --shared --yes                    # repair shared Python requirements
spa venv upgrade --shared --yes                      # bump Ansible and other requirements
spa venv rebuild --shared --yes                      # recreate the shared venv
spa doctor
spa validate
spa provision --yes && spa deploy --yes
spa hosts list --status
spa logs --last
```

`spa deploy` runs an Ansible ping with become for the selected hosts after you confirm and before the playbook, then compares `splunk_architecture` with the machine. The expected value is the host override, then that host's `splunk_environments` entry, then `splunk_defaults`, then `amd64`. `spa hosts check` is that check on its own. `spa deploy --hosts ROLE` includes every config host in that role, including one that is not provisioned yet. `spa provision` does not run the check. Before `spa run` of a playbook that needs root, run `spa hosts check`.

`external` hosts are registered with `spa hosts register`, which checks SSH and writes the address, user, and key only in `inventory/hosts`. The config only needs `external:`. `spa validate` stays the local config check. `spa deploy` pings with become and compares `splunk_architecture` with the machine before the playbook for AWS, VirtualBox, and external hosts. The expected value is the host override, then that host's `splunk_environments` entry, then `splunk_defaults`, then `amd64`. `spa hosts check` is that check without deploying. Run it before `spa run` when the playbook needs root. Provision and destroy do not create or terminate external hosts. Suspend and resume report that SPA does not own power for those hosts.

## Anti-patterns

Import `spa.api`; answer `Proceed?`; invent playbook names; dump full Ansible logs into the model context (use `spa logs` / `data.log` only when the user asked to debug); put installers inside `SPA_HOME`.

Human journey: [docs/user-guide.md](../../../docs/user-guide.md). Install: README curl `| sh`.
