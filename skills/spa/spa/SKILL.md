---
name: spa
description: Load first for Splunk Platform Automator — Software, registered environments, and the spa operator loop. Dispatch YAML/apps/tests to spa-create-config, spa-apps, spa-add-test-scenario.
---

# spa skill

Product entry for SPA (same role as cup’s main skill). **Load `/spa` first.** A later `spa skills install` ([#55](https://github.com/splunk/splunk-platform-automator/issues/55)) should treat this package as the default entry; do not invent install/remove here.

## When to use

Anything SPA: shared Software, registered environments, validate / provision / deploy / hosts / run. Task skills apply **after** an env exists, for that env’s YAML, Splunkbase apps, or app-scope tests.

## Contract

- **`SPA_HOME`**: framework. **`SPA_ENV_DIR`**: one environment. Call **`bin/spa` only**. Do not import `spa.api`. Do not start a daemon.
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Never answer `Proceed?`.
- Never print secrets. Report env vars as set / not set. YAML: `lookup('env', ...)`. Do not pass `spa -v` (unredacted Ansible stdout).
- Full command names (`spa environment list`, `spa hosts ssh`, `spa validate`). Humans may type `spa env`.
- No `ansible-playbook` / raw Vagrant for operators.

Discovery: `spa agent schema` / [docs/commands.md](../../../docs/commands.md). Playbooks: `spa --json run --list` then `spa run NAME --help`. Do not guess flags.

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
spa environment init --example cm_2idxc_sh_uf my-lab   # name-only under default parent
spa environment init --env-dir /custom --name my-lab   # one-off; does not change default parent
spa init /custom/my-lab                                # same dest as the line above
spa env init my-lab --force                            # adopt an existing env (cwd or default parent) into the list
spa --env my-lab validate
spa environment remove my-lab --yes                    # not spa destroy; --force if it looks deployed
```

`--name` is the registry key (default: folder basename). `spa` resolves `--env`, cwd, or the registered default and applies the required environment internally. `spa env --export` remains only for external tools.

## Software

One shared directory per machine, not inside `SPA_HOME` and not copied per env. Linux tgz installers, extracted PS baseconfig apps, optional `Splunk_Enterprise.lic`. Splunk / Cisco employees: [https://go2.cisco.com/baseconfigs](https://go2.cisco.com/baseconfigs). Others: Splunk PS. Checklist: [Prepare Software](../../../docs/user-guide.md#prepare-software).

```bash
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa venv --shared --reinstall --yes                    # repair shared Python requirements
spa venv --shared --upgrade --yes                      # bump Ansible and other requirements
spa venv --shared --rebuild --yes                      # recreate the shared venv
spa doctor
spa validate
spa provision --yes && spa deploy --yes
spa hosts list --status
spa logs --last
```

## Anti-patterns

Import `spa.api`; answer `Proceed?`; invent playbook names; dump full Ansible logs into the model context (use `spa logs` / `data.log` only when the user asked to debug); put installers inside `SPA_HOME`.

Human journey: [docs/user-guide.md](../../../docs/user-guide.md). Install: README curl `| sh`.
