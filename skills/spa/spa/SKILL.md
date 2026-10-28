---
name: spa
description: >-
  Load first for any request for a Splunk lab, Splunk environment, or Splunk Enterprise
  deployment: a Splunk lab, pro lab, single-node, clustered, ITSI, or ES environment on AWS
  or VirtualBox, including a Redhat, Rocky, Ubuntu, or Amazon Linux host with a given CPU
  count, or Splunk deployed to existing hosts (register them with spa hosts register). Use
  it to create, provision, deploy, validate, suspend, resume, destroy, or list environments
  and hosts. Use spa, not the AWS CLI, Terraform, or Ansible directly. Dispatch YAML to
  spa-create-config and apps to spa-apps. Lifecycle and prerequisites stay in this skill.
---

# spa skill

Product entry for SPA (same role as cup’s main skill). **Load `/spa` first.** `spa skills install` links this package into the user IDE skill directory.

## When to use

Anything SPA: shared Software, registered environments, validate / provision / deploy / hosts / run. Task skills apply **after** an env exists, for that env’s YAML or Splunkbase apps.

## Skill selection

Classify the request first, then load the one skill that owns the next step. Load one skill at a time, in the order the work needs them. For example, `/spa-create-config` hands the write to `/spa` and apps to `/spa-apps`. Route tree: [workflow-decision-tree.md](../spa-create-config/references/workflow-decision-tree.md).

| Request | Load | Keywords |
| --- | --- | --- |
| New environment or lab | `/spa-create-config` (Phases 0a–9, plan mode) | create, need, set up, new lab |
| Change an existing config | `/spa-create-config` ("Add / change a setting") | add, change, update, enable |
| Lifecycle | `/spa` | provision, deploy, destroy, status, logs, validate, suspend, resume |
| Apps | `/spa-apps` | Splunkbase, TA, app, content pack |
| Deploy to existing hosts | `/spa` (`spa hosts register`, then `spa deploy`) | existing hosts |

## Contract

- **Config is command-only:** never edit `splunk_config.yml` by hand (no editor, no shell write, no YAML patch). Read and change it only with `spa config ...` (`search`, `explain`, `get`, `set`, `add`, `unset`, `merge`, `topology`, `provider`, `header set`). Config design and setting changes go to `/spa-create-config`. App entries go to `/spa-apps`. Both end with `spa --agent validate`; deploy stays here and waits for your yes.
- **Routing:** a request for a Splunk lab, production, staging, or any other Splunk environment (create, deploy, change, check, or tear down), including a deploy to existing hosts (`spa hosts register`, then `spa deploy`), starts here. Do not use the AWS CLI, Terraform, Ansible, or Vagrant to create or change hosts for a Splunk environment. Use `spa`.
- **`SPA_HOME`**: framework. **`SPA_ENV_DIR`**: one environment. Call **`bin/spa` only**. Do not import `spa.api`. Do not start a daemon.
- Mutating commands need **`--yes`**. Never auto-run provision, deploy, suspend, resume, or destroy. Never answer `Proceed?`.
- Never print secrets. Report env vars as set / not set. YAML: `lookup('env', ...)`. Do not pass `spa -v` (unredacted Ansible stdout).
- Full command names (`spa environment list`, `spa hosts ssh`, `spa validate`). Humans may type `spa env`.
- No raw Ansible or Vagrant for operators. Ask in chat and wait before provision, deploy, destroy, suspend, resume, or environment remove. See [lifecycle.md](references/lifecycle.md) and [prerequisites.md](references/prerequisites.md).

Discovery: `spa agent schema` / [docs/commands.md](../../../docs/commands.md). All settings: [docs/config.md](../../../docs/config.md) (`spa --no-agent config schema --markdown`). Building `splunk_config.yml` follows the `spa-create-config` loop: discover with `spa --agent config search QUERY` and `spa --agent config explain PATH`. `spa --agent config explain PATH` returns that feature's one mutation command and does not apply it. Update an existing path with `spa --agent config set`, append a new non-app identity with `spa --agent config add SELECTOR JSON_OBJECT`, or send a deliberate fragment with `spa --agent config merge --file FILE`, then run `spa --agent validate`. App entries use `spa --agent apps add`. Catalog snippets are examples and are never applied implicitly. Explain paths omit empty brackets (`splunk_hosts`, `splunk_app_deployment.apps.premium_app`). Mutation selectors such as `splunk_hosts[name=NAME]` keep the identity. In zsh, quote a selector that contains `[]`. Playbooks: `spa --agent run list` then `spa run NAME --help`. Do not guess flags.

## Dispatch

| Work | Skill / command |
| --- | --- |
| Env lifecycle (init, list, set, remove, `--env`, validate, provision, deploy, power, destroy, hosts) | **this skill** (`/spa`) — [lifecycle.md](references/lifecycle.md) |
| Prerequisites (doctor, validate, archives, credentials) | **this skill** (`/spa`) — [prerequisites.md](references/prerequisites.md) |
| Config design or any setting change (SVA, AWS, licenses, header, `spa config ...`) | `spa-create-config` — `spa config` only; not init, not deploy |
| Apps: Splunkbase search, add, remove, local archives, content packs | `spa-apps` — `spa apps` only |

## Environments

Canonical: `spa environment` (alias `env`). `spa init` aliases `spa environment init`.

```bash
spa environment list
spa environment set --env-dir ~/work/spa-envs          # persist default parent (not ~/Splunk-Platform-Automator)
spa environment set --software-dir ~/Software --apps-dir ~/labs/apps
spa environment set --default my-lab                   # fallback when cwd does not select an env
spa environment set --provider virtualbox              # saves the default for init in providers.yml (aws, virtualbox, or external)
spa environment init --example cm_2idxc_sh --provider aws my-lab   # name-only under default parent; --provider required unless a default is saved
spa environment init --env-dir /custom --name my-lab   # one-off; does not change default parent
spa init /custom/my-lab                                # same dest as the line above
spa env init my-lab --force                            # adopt an existing env (cwd or default parent) into the list
spa --env my-lab validate
spa environment remove my-lab --yes                    # not spa destroy; --force if it looks deployed
spa environment cleanup                                # lists registry entries whose dir is missing; --yes removes those entries only
```

`--name` is the registry key (default: folder basename). `spa` resolves `--env`, `SPA_ENV_DIR`, the current directory, then the registered default, and applies that environment internally. When the current directory is the environment, run `spa` with no `--env` and do not run `spa environment list`. `spa environment --export` is the canonical form for external tools. `spa env --export` remains the human alias.

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

## Long runs

`provision`, `deploy`, `destroy`, and `spa run` write one sentence to stderr when the phase or host changes. The 20-second heartbeat writes nothing. Stdout is the final JSON envelope. When the current directory is the environment, start `spa --agent provision --yes` there, and the same form for `deploy`, `destroy`, and `run NAME`. Do not pass `--env`, and do not run `spa environment list`. From any other directory, pass `--env NAME` on that same command. Do not pass `-v` or `--ansible-output`. Do not read `.spa.yml`, the terminal folder, `lib/spa`, or docs. Do not grep the repo. Do not list tools, and do not open a todo list.

Start that command once. Provision, deploy, and destroy share one lock. While one of them is running, the others are refused. The error names the running command, for example `A deploy is already running.` Report that sentence and stop. Do not start one of the other two. The lock ends when that process ends, including when it is aborted. Wait in one call until `"ok":` or the process exits. Do not poll every second, and do not put the sentence list into the wait pattern. If a sentence is already visible on the command, repeat that exact line once. Do not read the terminal file, and do not call other tools. Do not run `spa validate` unless the user asked for it. The heartbeat writes nothing. When the process exits, report the envelope in one sentence. Do not wait on the word `phase` or a Terraform banner.

Provision and destroy: `Planning the infrastructure.`, `Creating HOST.`, `HOST is up.`, `Destroying HOST.` Deploy: `Host is prepared.`, `Hosts are already prepared.`, `Downloading Splunk on HOST.`, `Splunk is already downloaded on HOST.`, `Extracting Splunk on HOST.`, `Splunk is already extracted on HOST.`, `Configuring the cluster manager.`, `The cluster manager is already configured.`, `Configuring Splunk.`, `Installing cluster manager apps.`, `Installing ITSI.`, `Installing apps on HOST.` A role's already-configured sentence is printed when that role's own tasks finish with nothing changed. Opening checks do not count, and baseconfig between those tasks does not finish the role. A role play with no matching hosts is silent. `spa run` uses those same sentences, plus `Upgrading indexer HOST.`, `Restarting Splunk on HOST.`, and `Running TITLE.` for any other playbook.

`spa deploy` runs an Ansible ping with become for the selected hosts after you confirm and before the playbook, then compares `splunk_architecture` with the machine. The expected value is the host override, then that host's `splunk_environments` entry, then `splunk_defaults`, then `amd64`. `spa hosts check` is that check on its own. `spa deploy --hosts ROLE` includes every config host in that role, including one that is not provisioned yet. `spa provision` does not run the check. Before `spa run` of a playbook that needs root, run `spa hosts check`.

`external` hosts are registered with `spa hosts register NAME --ssh-host HOST --user USER --key PATH --yes`, which checks SSH and writes the SSH host, user, and key only in `inventory/hosts`. Add `--ssh-port PORT` when SSH is not on port 22. Add `--ip-addr ADDRESS` when Splunk hosts reach that machine on a different address than SSH. Omit `--ip-addr` to use the SSH host for both. The config only needs `external:`. `spa validate` stays the local config check. `spa deploy` pings with become and compares `splunk_architecture` with the machine before the playbook for AWS, VirtualBox, and external hosts. The expected value is the host override, then that host's `splunk_environments` entry, then `splunk_defaults`, then `amd64`. `spa hosts check` is that check without deploying. Run it before `spa run` when the playbook needs root. Provision and destroy do not create or terminate external hosts. Suspend and resume report that SPA does not own power for those hosts.

## Anti-patterns

Import `spa.api`; answer `Proceed?`; invent playbook names; dump full Ansible logs into the model context (use `spa logs` / `data.log` only when the user asked to debug); put installers inside `SPA_HOME`.

Human journey: [docs/user-guide.md](../../../docs/user-guide.md). Install: README curl `| sh`.
