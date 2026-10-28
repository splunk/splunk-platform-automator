# Contributing

Operators should start with the [user guide](user-guide.md). The generated CLI catalog is [commands.md](commands.md) (`spa --no-agent agent schema --markdown`). The generated settings list is [config.md](config.md) (`spa --no-agent config schema --markdown`). This page collects framework-development topics that should not expand the operator documentation.

Start framework changes with the [architecture and contributor standards](architecture.md), including module and Ansible boundaries, extension contracts, test layers, controller direction, and the feature development lifecycle. The sections below contain the detailed procedures linked from that guide.

## Development setup

Clone the repository and create the shared venv as in [Develop SPA](install.md#develop-spa-git-clone). Then activate it and run the local suite:

```bash
source bin/spa_venv.sh
./tests/run_local_tests.sh
```

Do not rely on Homebrew or system Ansible.

Use `tests/README.md` for suites and app-scope scenarios. Release steps are in [RELEASE.md](../RELEASE.md).

## Agent skills

Canonical skills live only under `skills/spa/`:

| Task | Skill |
| --- | --- |
| Load SPA first (Software, envs, operator loop) | `spa` (`/spa`) |
| Design `splunk_config.yml` | `spa-create-config` |
| Find and configure Splunkbase apps | `spa-apps` |

Cursor symlinks are not part of this repo. Install the packages into the user IDE directory with `spa skills install` (see [`skills/spa/README.md`](../skills/spa/README.md)). Do not duplicate skill content.

Agents invoke `bin/spa`, never import `spa.api`, and follow [AGENTS.md](../AGENTS.md).

## Framework group_vars

Ansible group and host vars for SPA live in `$SPA_HOME/ansible/group_vars`, next to the playbooks. The env inventory directory only holds generated `hosts`. A vars plugin (`spa_group_vars`) loads the framework files so a separate env does not need `inventory/group_vars` as a symlink into the repo. `spa init --force` and migrate remove a leftover 2.x `inventory/group_vars` symlink; a real directory is left alone. Like the builtin `host_group_vars`, the plugin loads with `trusted_as_template=True`: ansible-core 2.19+ does not template untrusted strings, so without it a value like `splunk_software` reaches tasks as literal jinja.

## Env-dir run logs

Mutating `spa` commands write `$SPA_ENV_DIR/logs/{run_id}.jsonl` plus a `.meta.json` sidecar. The id is the local stamp, the command, and the playbook stem (`2026-10-14T183216+0200-run-upgrade_splunk`). This is per-environment output, not XDG `~/.local/state`.

Each JSONL line is one event. `time` is local ISO-8601 with a **numeric offset** and milliseconds, for example `2026-09-17T17:02:00.123+02:00`. Never naive, never `Z`-only (UTC hosts use `+00:00`). Offset is taken at event time so DST is unambiguous. A later Splunk TA can set `_time` from that field with `TIME_FORMAT = %Y-%m-%dT%H:%M:%S.%3N%:z` and should not force `TZ = GMT`.

Stable fields: `time`, `run_id`, `spa_env`, `command`, `playbook`, optional `play_file` / `task_file` / `role_path` (imported play and role origins), `phase` / `phase_id`, `play`, `task`, `role`, `host`, `status`, `kind`, `duration_ms`, and `msg`. Native Ansible lines are stored in arrival order as `kind: ansible_output`, with `source: ansible`, ANSI-free `text`, and a monotonic `sequence`; blank lines are retained. Optional `tf_summary` is an allowlisted Terraform host diff (not the full plan JSON). Human compact progress is **one named TTY line per group that actually runs** (`Deploy  App deployment · Search Head Cluster apps`), not a `[n/m]` catalog. While a group runs, the mutable line includes the active host and task. Rolling upgrades settle one line per host and include installed and target Splunk versions when the playbook reports them. The same group ids apply to `spa run` of every first-party `ansible/*.yml` file, with play-name fallback outside known roles and functions. Agent-sparse NDJSON on stderr is derived from structured events and can include phase/host/task names, but never native transcript text. Stdout in agent mode stays one JSON envelope (`data.log`, `data.run_id`; on failure phase/host/task names only), serialized compact — a command keeps its payload small and sends per-item detail only when a step fails or the operator asked for it (`spa validate` sends `data.licenses`, not the whole scan). Color uses ANSI on a TTY unless `NO_COLOR`, `ANSIBLE_NOCOLOR`, or `TERM=dumb`. A finished line ends with `ok` (green, no changes), `changed` (yellow), or `failed` (red). `tasks N` counts distinct task names, while `changed N/M` and `skipped N` count task-host results. Terraform provision/destroy groups only move forward so late setup tasks fold into the open step. Provision/destroy grouping is per provider: Ansible-driven providers (`terraform.aws`) map task names onto the ordered Terraform steps, while a provider that streams its own CLI (`virtualbox`, Vagrant) is parsed by a dialect in `PROVIDER_LINE_EVENTS`, tags its events `source: provider`, groups them per machine (`vm:NAME`), and replays as the tool's own text instead of PLAY/TASK banners. The live line is fitted to the terminal width (Terraform details shrink before elapsed time and status) so `\r` never smears a wrapped line.

`spa logs` / `spa logs --last` / `spa logs --follow` read this store (raw JSONL by default). `--ansible-output` shows the captured native Ansible transcript both live and from stored runs; older runs without native events fall back to the structured reconstruction. `--timestamps` prefixes each displayed line with the stored event time, and `--color` colors the live Ansible stream or recolors a stored transcript. Neither flag changes the stored `text`. `-v` through `-vvvv` on a live playbook run passes the exact verbosity count to `ansible-playbook` and also shows native output. Run transcripts are intentionally unredacted until [#88](https://github.com/splunk/splunk-platform-automator/issues/88); they stay on the operator's machine and may contain secrets. Native output never enters the agent envelope. `spa logs` does not accept `-v`; use `--ansible-output`.

## Windows box maintenance

Windows guest operation is not currently a first-class SPA workflow. The historical box-authoring process used a VirtualBox Windows template, WinRM, `vagrant package`, and `vagrant box add`. If Windows guests return, implement and document them through `spa` rather than restoring a second operator CLI. The detailed former recipe remains available in Git history.

## Adding a configuration feature

`spa config explain` and [config.md](config.md) are generated. A new `splunk_config.yml` key is not listed until the Pydantic schema describes it and, when an operator must choose it, `examples/catalog/features.yml` groups it. Do not hand-edit `docs/config.md`.

Use the architecture guide's
[test-driven development](architecture.md#test-driven-development) procedure
and finish with its
[feature completion review](architecture.md#feature-completion-review).
Changes to config mutation behavior must also update the normative
[config-editing contract](config-editing.md) and its mapped test in the same
red-green-refactor cycle.

Read the code that honors the key before writing text: the field on `ansible/plugins/inventory/schema.py`, `defaults/*.yml`, role `default()` values, the inventory plugin, and templates. That behavior is the description.

### Schema description

Every field needs `Field(description=...)`. The sentence says what this key does. A container (any path that has children, including `path[]`) is one line and does not name those children. A required field ends with `Required.` A key with nothing to publish uses `No default.` plus what omit does, for example `No default. Omit the key to set no tags.`

An omit-safe literal uses this shape, with the period before `Omit`:

```text
Default splk. Omit the key to keep that.
```

The renderer copies `splk` into the `default` qualifier and then removes that sentence from the public description. The same parser accepts `true` / `false`, an integer, `none` (a list becomes `[]`), `Default is TOKEN.`, and a site factor such as `origin:2, total:3`. A sentence with spaces that is not a site factor stays prose and does not become `default`. Examples: the controller time zone, an AMI id, or "a lab password".

Leave the Pydantic default unset (`Field(None)` or no default) unless validation itself must inject the value. Publishing `default: splk` must not make `spa validate` write `splk` into a config that omitted the key.

Paths whose leaf matches `password`, `secret`, `token`, or `private_key` never get a `default` field. Say that the value is a lab secret resolved with `lookup('env', 'NAME')`. Do not put the secret, a private-key body, or a certificate (`-----BEGIN`) in the description, a catalog note, or a snippet.

Per-host copies under `splunk_hosts[].os`, `splunk_hosts[].virtualbox`, and `splunk_hosts[].terraform` use the same sentence as the global key. The renderer prefixes `Per-host override of \`os.time_zone\`:`. SSL text that says "this endpoint" is specialized to Splunk Web, receiving inputs, or forwarding outputs from the path. `spa config explain` adds `SCOPE` when the same setting exists globally and on a host, including `custom` and flattened `splunk_defaults` fields such as `splunk_version`. Each host gets the global list plus its own items for list fields under `os` and `custom`. Other paired values replace the global value for that host. A setting with no counterpart omits `SCOPE`.

### Catalog record

Add a record only when it helps someone choose or apply config.

A **setting** (`kind: setting`) has a `selector` that is one of its own schema paths. `keys` lists those paths. `when_to_use` or `when_not_to_use` is at least a short sentence about the decision, not a repeat of the title or the selector. Catalog snippets are examples, not applicable fragments. `spa config explain PATH` prints the one mutation command for that feature. Operators update an existing path with `spa config set` and append a non-app identity with `spa config add`. App entries use `spa apps add`. A snippet writes only declared paths. Passwords in a snippet use `lookup('env', ...)` or Ansible Vault, never a literal. Settings are public by user path (`spa config explain os`). `setting.*` ids are unknown. Explain paths omit empty `[]`. Mutation selectors such as `splunk_hosts[name=NAME]` keep the identity. In zsh, quote a selector that contains `[]`.

A key `note` is only for a constraint the schema sentence does not already say (Java 21 on the ITSI host, gp3, AMI login user). Notes attach to leaves. A note that mostly repeats the description is dropped. Do not use a note to name children of a container.

A **layout** is an SVA topology (`topology.s1`, `topology.d1`, `topology.d11`, `topology.c1`, `topology.c11`, `topology.c3`, `topology.c13`, `topology.m2`, `topology.m12`, `topology.m3`, `topology.m13`, `topology.m14`) or an implemented provider (`provider.aws`, `provider.virtualbox`). It has `kind: topology` or `kind: provider`, no `selector`, schema-backed `keys`, and a `suggest` line with the `spa init --example` or `--provider` command. Layouts have no `apply` object. Other `spa init --example` files stay on disk; do not add another `topology.*` row for them. A future skill can own extra topology design.

Do not add a record with no schema paths. Those rows are unsupported and `spa config explain` is only for settings and layouts that can be written. Command help that is not a config key belongs in the operator docs (`docs/apps.md` for `spa apps`).

Guidance, notes, and snippets must not contain internal ids (`setting.`, `topology.`, `provider.`). Search does not index those ids either. `related` may cite `#NN` issues or another catalog id; a missing id is skipped, so delete the link when you delete the record.

A new top-level schema root needs an entry in `CONFIG_AREAS` in `lib/spa/catalog.py`, in config-writing order: Identity, General, OS, Provider, Defaults, Hosts, Apps, Clustering. An unknown root lands in an "Other" section, which the settings dump must not have.

### Check

Regenerate the settings dump and confirm the new key with the feature command:

```bash
bin/spa --no-agent config schema --markdown > docs/config.md
bin/spa config explain PATH
```

`tests/test_docs.py` requires the committed `docs/config.md` to match that command. If `COMMAND_SCHEMA` in `lib/spa/agent.py` changes, regenerate `docs/commands.md` with `bin/spa --no-agent agent schema --markdown` the same way. Release bump regenerates both; do not edit them by hand.

## Adding a spa command

Operator docs stay in the user guide. This is the command-authoring contract.
Follow [CLI UX and output conventions](architecture.md#cli-ux-and-output-conventions).
Use [test-driven development](architecture.md#test-driven-development) and the
[feature completion review](architecture.md#feature-completion-review).
Commands that read or write `splunk_config.yml` also follow the
[config-editing contract](config-editing.md).

1. Add one parser per action. Fixed action sets (`features`, `hosts`, `apps`, `aws`) use required subparsers. A command whose operand is a free name (`run NAME`, `init ENV_DIR`, `logs RUN_ID`) keeps that positional and reserves the literal operand `list`. Do not add a hidden subcommand or rewrite argv. A catalog action is the last word (`spa hosts list`, `spa aws regions list`).
2. Put required operands and flags only on the action that accepts them. A catalog is `list`. Do not add `--list` or `--list-*`.
3. Usage failures exit 2. Name the legal command in the error. Human mode writes that text to stderr and does not print a catalog. Agent mode (`--agent`, `--json`, or a detected agent) writes one compact JSON object on stdout and leaves stderr empty: `{"ok":false,"schema_version":1,"error":"..."}`. Do not add `data` on failure. The same rule covers success: one JSON object, and no human sentence on stdout or stderr. Do not print a progress or cache notice in agent mode. Long-running progress, when emitted, is one JSON object per stderr line. Runtime and provider failures stay exit 1. Explicit `--help` stays exit 0.
4. Register the action in `COMMAND_SCHEMA` in `lib/spa/agent.py` in the same change: required positional names, action-specific flags, and one legal example. `spa agent schema` is how agents discover commands.
5. Regenerate [commands.md](commands.md) with `bin/spa --no-agent agent schema --markdown`. Do not hand-edit it or [config.md](config.md).
6. Extend `tests/test_spa_cli_contract.py` so the help surface and `COMMAND_SCHEMA` stay equal, list flags are not advertised on the parent, and a parent that requires an action rejects a bare call with the agent envelope above. Run `./tests/run_cli_tests.sh`. A parser change does not need an AWS or live-Splunk run. `./tests/run_local_tests.sh` is the broader local gate.
7. Choose one command class from [CLI UX and output conventions](architecture.md#cli-ux-and-output-conventions): catalog or search, selected definition, current value, mutation, validation, or long-running. Return a `CommandResult`. Add one human test and one agent test for that class. Do not add a second renderer unless two commands in the class are changing to the same rule.
8. Support agent mode. When an agent is detected, `spa COMMAND --help` is that one `COMMAND_SCHEMA` entry, not argparse text. Examples use the full command name and `--agent`. `--json` stays a synonym. A short alias, if one already exists, appears only on that command's `Aliases:` line.
9. Stay completable. One schema entry per action, canonical names only. On a flag or positional, set `choices` for a closed set, `takes_value` when the flag consumes the next token, and `completes_from` when the values come from a local list command such as `run list` or `environment list`. A command is not done until `spa completion` can offer it. Do not add a command whose arguments can only be discovered by reading help, and do not restore a removed command.
10. A required operand's missing-argument and unknown-value errors name the legal values, or say what the operand is, name the command that lists the values, and give one example. Human stderr and the agent `error` string use those sentences. Put the same sentence on the positional help. A non-TTY mutation exits 2 and names `-y/--yes` without saying "agent mode".

Examples, help, errors, and schema descriptions never contain passwords, tokens, private keys, or certificates. Use `lookup('env', ...)`.

## Documentation

- Well-known root files stay uppercase: `README.md`, `AGENTS.md`, `CHANGELOG.md`, `ROADMAP.md`, `RELEASE.md`.
- Other documentation uses lowercase kebab-case.
- Commands are `spa`-first; raw backend commands belong only in implementation/test context.
- Prefer links to `spa --help`, `spa config explain`, `spa apps`, schema, and upstream Splunk docs over duplicated reference tables.
- The user guide explains how to use spa after it is installed. Framework install, uninstall, shell completion setup, controller Python, VirtualBox, and WSL belong in [install.md](install.md). Link there. Do not copy those commands.
- A development clone is installed from [Develop SPA](install.md#develop-spa-git-clone). This page owns the test and authoring loop.
- One procedure lives on one page.
- New `splunk_config.yml` keys and `spa config explain` records follow [Adding a configuration feature](#adding-a-configuration-feature).
- New `spa` commands follow [Adding a spa command](#adding-a-spa-command).
- Never add credentials, private keys, certificates, or decrypted values to examples.
