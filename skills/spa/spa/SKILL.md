---
name: spa
description: >-
  Load first for any request for a Splunk lab, Splunk environment, or Splunk Enterprise
  deployment: a Splunk lab, pro lab, single-node, clustered, ITSI, or ES environment on AWS
  or VirtualBox, including a Redhat, Rocky, Ubuntu, or Amazon Linux host with a given CPU
  count, a CCM lab, or Splunk deployed to existing hosts (register
  them with spa hosts register). Use it to create, provision, deploy, validate, suspend,
  resume, destroy, or list environments and hosts. Use spa, not the AWS CLI, Terraform, or
  Ansible directly. Dispatch YAML to spa-create-config and apps to spa-apps. Lifecycle and
  prerequisites stay in this skill.
---

# spa skill

Product entry for SPA (same role as cup’s main skill). **Load `/spa` first.** `spa skills install` links this package into the user IDE skill directory.

## When to use

Anything SPA: shared Software, registered environments, validate / provision / deploy / hosts / run. Task skills apply **after** an env exists, for that env’s YAML or Splunkbase apps.

## Skill selection

Classify the request first, then load the one skill that owns the next step. Load one skill at a time, in the order the work needs them. For example, `/spa-create-config` hands the write to `/spa` and apps to `/spa-apps`. Route tree: [workflow-decision-tree.md](../spa-create-config/references/workflow-decision-tree.md).

| Request | Load | Keywords |
| --- | --- | --- |
| New environment or lab | `/spa-create-config` (path A questionnaire, or path B if a confirmed architecture file is given) | create, need, set up, new lab, architecture file |
| Change an existing config | `/spa-create-config` ("Add / change a setting") | add, change, update, enable |
| Lifecycle | `/spa` | provision, deploy, destroy, status, logs, validate, suspend, resume |
| Apps | `/spa-apps` | Splunkbase, TA, app, content pack |
| Deploy to existing hosts | `/spa` (`spa hosts register`, then `spa deploy`) | existing hosts |

## Contract

- **Config is command-only:** never edit `splunk_config.yml` by hand (no editor, no shell write, no YAML patch). Read and change it only with `spa config ...` (`search`, `explain`, `get`, `set`, `add`, `unset`, `merge`, `move`, `topology`, `provider`, `header set`). Config design and setting changes go to `/spa-create-config`. A confirmed architecture file still loads `/spa-create-config` (path B); this skill does not provision from that file. App entries go to `/spa-apps`. Both end with `spa --agent validate`; deploy stays here and waits for your yes.
- **Routing:** a request for a Splunk lab, production, staging, or any other Splunk environment (create, deploy, change, check, or tear down), including a deploy to existing hosts (`spa hosts register`, then `spa deploy`), starts here. Do not use the AWS CLI, Terraform, Ansible, or Vagrant to create or change hosts for a Splunk environment. Use `spa`.
- **`SPA_HOME`**: framework. **`SPA_ENV_DIR`**: one environment. Call **`bin/spa` only**. Do not import `spa.api`. Do not start a daemon.
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Exception: `/spa-create-config` Phase 14 option A hands off here, and this skill then runs `provision`, then `deploy`, each only after its own explicit yes in chat. Never answer `Proceed?`.
- Never print secrets. Report env vars as set / not set. YAML: `lookup('env', ...)`. Do not pass `spa -v` (unredacted Ansible stdout).
- **CCM:** employee-only. Report `CCM_TOKEN` as set / not set. AskQuestion ids in the order spa prints (`spa init --help`), including CCM. Do not hide CCM when the token is unset; `spa validate` and `spa doctor` name a missing token. If they chose CCM and the token is not set, tell them to mint a PAT and SSH key at https://ccm.splunkits.io/ and export `CCM_TOKEN`. Lifecycle already works when the env has `ccm:`.
- Full command names (`spa environment list`, `spa hosts ssh`, `spa validate`). Humans may type `spa env`.
- **`data.next`:** AskQuestion each `ask`, then prefer `argv`. If a shell is used, copy `command` verbatim. String scalars are unquoted; JSON is only for lists and maps.
- No raw Ansible or Vagrant for operators. Ask in chat and wait before provision, deploy, destroy, suspend, resume, environment remove, or environment cleanup. See [lifecycle.md](references/lifecycle.md) and [prerequisites.md](references/prerequisites.md).

Discovery: `spa agent schema` / [docs/commands.md](../../../docs/commands.md). All settings: [docs/config.md](../../../docs/config.md) (`spa --no-agent config schema --markdown`). Building `splunk_config.yml` follows the `spa-create-config` loop: discover with `spa --agent config search QUERY` and `spa --agent config explain PATH`. `spa --agent config explain PATH` returns that feature's one mutation command and does not apply it. Update an existing path with `spa --agent config set`, append a new non-app identity with `spa --agent config add SELECTOR JSON_OBJECT`, or send a deliberate fragment with `spa --agent config merge --file FILE`, then run `spa --agent validate`. App entries use `spa --agent apps add`. Catalog snippets are examples and are never applied implicitly. Explain paths omit empty brackets (`splunk_hosts`, `splunk_app_deployment.apps.premium_app`). Mutation selectors such as `splunk_hosts[name=NAME]` keep the identity. In zsh, quote a selector that contains `[]`. Playbooks: `spa --agent run list` then `spa run NAME --help`. Do not guess flags. Upgrade: [upgrade.md](references/upgrade.md). Health: [health.md](references/health.md).

## Dispatch

| Work | Skill / command |
| --- | --- |
| Env lifecycle (init, list, set, remove, `--env`, validate, provision, deploy, power, destroy, hosts) | **this skill** (`/spa`) — [lifecycle.md](references/lifecycle.md) |
| Prerequisites (doctor, validate, archives, credentials) | **this skill** (`/spa`) — [prerequisites.md](references/prerequisites.md) |
| Upgrade (existing `spa run` playbooks) | **this skill** (`/spa`) — [upgrade.md](references/upgrade.md) |
| Health (hosts status and check) | **this skill** (`/spa`) — [health.md](references/health.md) |
| Config design or any setting change (SVA, AWS, licenses, header, `spa config ...`) | `spa-create-config` — `spa config` only; not init, not deploy |
| Apps: Splunkbase search, add, remove, local archives, content packs | `spa-apps` — `spa apps` only |

## Environments

Canonical: `spa environment` (alias `env`). `spa init` aliases `spa environment init`.

```bash
spa environment list
spa environment set --env-dir ~/work/spa-envs          # persist default parent (not ~/Splunk-Platform-Automator)
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa environment set --default my-lab                   # fallback when cwd does not select an env
spa environment set --provider virtualbox              # saves the default for init in providers.yml
spa environment init --example cm_2idxc_sh --provider aws my-lab   # name-only under default parent; --provider required unless a default is saved
spa environment init --architecture examples/architectures/c3.json --provider aws my-lab  # overlay a confirmed schema 1 file; exclusive with --example
spa environment init --env-dir /custom --name my-lab   # one-off; does not change default parent
spa init /custom/my-lab                                # same dest as the line above
spa env init my-lab --force                            # adopt an existing env (cwd or default parent) into the list
spa --env my-lab validate
spa environment remove my-lab --yes                    # not spa destroy; --force if it looks deployed
spa environment cleanup                                # lists registry entries whose dir is missing; --yes removes those entries only
```

`--name` is the registry key (default: folder basename). `spa` resolves `--env`, `SPA_ENV_DIR`, the current directory, then the registered default, and applies that environment internally. When the current directory is the environment, run `spa` with no `--env` and do not run `spa environment list`. `spa environment --export` is the canonical form for external tools. `spa env --export` remains the human alias.

## Software

One shared directory per machine, not inside `SPA_HOME` and not copied per env. Linux tgz installers, extracted PS baseconfig apps, optional `Splunk_Enterprise.lic`. Splunk / Cisco employees: [http://go/baseconfigs](http://go/baseconfigs). Others: Splunk PS. Checklist: [Prepare Software](../../../docs/user-guide.md#prepare-software).

```bash
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa venv reinstall --shared --yes                    # repair shared Python requirements
spa venv upgrade --shared --yes                      # bump Ansible and other requirements
spa venv rebuild --shared --yes                      # recreate the shared venv
spa validate
spa deploy --yes
spa hosts list --status
spa logs --last
```

## Long runs

When running `deploy`, `destroy`, or `spa run`, follow [long-runs.md](references/long-runs.md). Do not load it until that command is running.

## Handoff from spa-create-config

After Phase 14 option A, follow [long-runs.md](references/long-runs.md#handoff-from-spa-create-config). Each step waits for its own yes in chat.

## Anti-patterns

Import `spa.api`; answer `Proceed?`; invent playbook names; dump full Ansible logs into the model context (use `spa logs` / `data.log` only when the user asked to debug); put installers inside `SPA_HOME`; `2>&1 | grep`, `head`, or `tail` on deploy/destroy/run.

Human journey: [docs/user-guide.md](../../../docs/user-guide.md). Install: README curl `| sh`. Token budget: [token-budget.md](references/token-budget.md).
