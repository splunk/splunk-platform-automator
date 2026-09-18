# Contributing

Operators should start with the [user guide](user-guide.md). The generated CLI catalog is [commands.md](commands.md) (`spa --no-agent agent schema --markdown`). This page collects framework-development topics that should not expand the operator documentation.

## Development setup

Clone the repository as `SPA_HOME`, then create or activate the shared environment:

```bash
bin/spa venv --shared --create --yes
source bin/spa_venv.sh
./tests/run_local_tests.sh
```

`spa venv` installs the pinned Python and Ansible dependencies plus collections (`bin/spa_venv.sh` is the implementation). Do not rely on Homebrew/system Ansible. If the host Python is too old, install Python 3.9+ with pyenv or a private prefix and pass that interpreter to `spa venv --python` or `spa init --python`.

Use `tests/README.md` for suites and app-scope scenarios. Release steps are in [RELEASE.md](../RELEASE.md).

## Agent skills

Canonical skills live only under `skills/spa/`:

| Task | Skill |
| --- | --- |
| Load SPA first (Software, envs, operator loop) | `spa` (`/spa`) |
| Design `splunk_config.yml` | `spa-create-config` |
| Find and configure Splunkbase apps | `spa-apps` |
| Add app-scope test scenarios | `spa-add-test-scenario` |

Cursor symlinks under `.cursor/skills/` point to those directories. Claude Code and generic agents can point directly at each `SKILL.md`; do not duplicate skill content. The index and setup commands are in [`skills/spa/README.md`](../skills/spa/README.md).

Agents invoke `bin/spa`, never import `spa.api`, and follow [AGENTS.md](../AGENTS.md).

## Controller architecture

The current CLI opens a local `LocalSpaSession` behind `spa.api.open_session`. Commands return a JSON-serializable `CommandResult`; the CLI renderer owns human/agent presentation. Skills and automation still call the binary so they exercise the same validation, confirmation, and envelope contracts.

A future GUI or remote controller may reuse the session protocol. Remote transport is intentionally not implemented. Before remote access is enabled it must provide authentication, authorization, TLS, secret redaction, audit events, bounded progress streams, cancellation, and version negotiation.

Confirmation belongs in the session boundary, not a UI renderer. Mutating operations require explicit confirmation; agent/GUI clients never answer an interactive prompt.

## Framework group_vars

Ansible group and host vars for SPA live in `$SPA_HOME/ansible/group_vars`, next to the playbooks. The env inventory directory only holds generated `hosts`. A vars plugin (`spa_group_vars`) loads the framework files so a separate env does not need `inventory/group_vars` as a symlink into the repo. `spa init --force` and migrate remove a leftover 2.x `inventory/group_vars` symlink; a real directory is left alone. Like the builtin `host_group_vars`, the plugin loads with `trusted_as_template=True`: ansible-core 2.19+ does not template untrusted strings, so without it a value like `splunk_software` reaches tasks as literal jinja.

## Env-dir run logs

Mutating `spa` commands write `$SPA_ENV_DIR/logs/{run_id}.jsonl` plus a `.meta.json` sidecar. This is per-environment output, not XDG `~/.local/state`.

Each JSONL line is one event. `time` is local ISO-8601 with a **numeric offset** and milliseconds, for example `2026-09-17T17:02:00.123+02:00`. Never naive, never `Z`-only (UTC hosts use `+00:00`). Offset is taken at event time so DST is unambiguous. A later Splunk TA can set `_time` from that field with `TIME_FORMAT = %Y-%m-%dT%H:%M:%S.%3N%:z` and should not force `TZ = GMT`.

Stable fields: `time`, `run_id`, `spa_env`, `command`, `playbook`, optional `play_file` / `task_file` / `role_path` (imported play and role origins), `phase` / `phase_id`, `play`, `task`, `role`, `host`, `status`, `kind`, `duration_ms`, `msg` (redacted). Optional `tf_summary` is an allowlisted Terraform host diff (not the full plan JSON). Human compact progress is **one named TTY line per group that actually runs** (`Deploy  App deployment · Search Head Cluster apps`), not a `[n/m]` catalog. The same group ids apply to `spa run` of first-party `ansible/*.yml` files (including upgrade playbooks). Unknown playbooks use the play name. Agent-sparse NDJSON on stderr is derived from these events. Stdout in agent mode stays one JSON envelope (`data.log`, `data.run_id`; on failure phase/host/task names only), serialized compact — a command keeps its payload small and sends per-item detail only when a step fails or the operator asked for it (`spa validate` sends `data.licenses`, not the whole scan). Color uses ANSI on a TTY unless `NO_COLOR`, `ANSIBLE_NOCOLOR`, or `TERM=dumb`. A finished line ends with `ok` (green, no changes), `changed` (yellow), or `failed` (red). `tasks N` counts distinct task names, while `changed N/M` and `skipped N` count task-host results. Terraform provision/destroy groups only move forward so late setup tasks fold into the open step. Provision/destroy grouping is per provider: Ansible-driven providers (`terraform.aws`) map task names onto the ordered Terraform steps, while a provider that streams its own CLI (`virtualbox`, Vagrant) is parsed by a dialect in `PROVIDER_LINE_EVENTS`, tags its events `source: provider`, groups them per machine (`vm:NAME`), and replays as the tool's own text instead of PLAY/TASK banners. Raw Ansible stderr text is stored as `kind: note`: it stays in the transcript and the replay but is not a step, so warnings never open or close a group; `ERROR!` notes are reported as failures. The live line is fitted to the terminal width (Terraform details shrink before elapsed time and status) so `\r` never smears a wrapped line.

`spa logs` / `spa logs --last` / `spa logs --follow` read this store (raw JSONL by default). `--ansible-output` prints the redacted Ansible-style view rebuilt from these events (live and stored). `-v` on a live playbook run streams Ansible's own stdout byte for byte, **unredacted** (secrets included until [#88](https://github.com/splunk/splunk-platform-automator/issues/88)), with Ansible color on a TTY; `spa_jsonl` still writes the redacted store and compact progress. Native output never enters the agent envelope. On `spa logs`, `-v` is the same reconstruction as `--ansible-output`. That reconstruction is not a recording of the original Ansible or Terraform CLI.

## Windows box maintenance

Windows guest operation is not currently a first-class SPA workflow. The historical box-authoring process used a VirtualBox Windows template, WinRM, `vagrant package`, and `vagrant box add`. If Windows guests return, implement and document them through `spa` rather than restoring a second operator CLI. The detailed former recipe remains available in Git history.

## Documentation

- Well-known root files stay uppercase: `README.md`, `AGENTS.md`, `CHANGELOG.md`, `ROADMAP.md`, `RELEASE.md`.
- Other documentation uses lowercase kebab-case.
- Commands are `spa`-first; raw backend commands belong only in implementation/test context.
- Prefer links to `spa --help`, `spa features`, `spa apps`, schema, and upstream Splunk docs over duplicated reference tables.
- Never add credentials, private keys, certificates, or decrypted values to examples.
