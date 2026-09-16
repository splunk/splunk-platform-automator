# Contributing

Operators should start with the [user guide](user-guide.md). The generated CLI catalog is [commands.md](commands.md) (`spa --no-agent agent schema --markdown`). This page collects framework-development topics that should not expand the operator documentation.

## Development setup

Clone the repository as `SPA_HOME`, then use the shared environment:

```bash
source bin/spa_venv.sh
./tests/run_local_tests.sh
```

`spa_venv.sh` installs the pinned Python and Ansible dependencies plus collections. Do not rely on Homebrew/system Ansible. If the host Python is too old, install Python 3.9+ with pyenv or a private prefix and pass that interpreter to `spa_venv.sh --python` or `spa init --python`.

Use `tests/README.md` for suites and app-scope scenarios. Release steps are in [RELEASE.md](../RELEASE.md).

## Agent skills

Canonical skills live only under `skills/spa/`:

| Task | Skill |
| --- | --- |
| Design `splunk_config.yml` | `spa-create-config` |
| Find and configure Splunkbase apps | `spa-apps` |
| Add app-scope test scenarios | `spa-add-test-scenario` |

Cursor symlinks under `.cursor/skills/` point to those directories. Claude Code and generic agents can point directly at each `SKILL.md`; do not duplicate skill content. The index and setup commands are in [`skills/spa/README.md`](../skills/spa/README.md).

Agents invoke `bin/spa`, never import `spa.api`, and follow [AGENTS.md](../AGENTS.md).

## Controller architecture

The current CLI opens a local `LocalSpaSession` behind `spa.api.open_session`. Commands return a JSON-serializable `CommandResult`; the CLI renderer owns human/agent presentation. Skills and automation still call the binary so they exercise the same validation, confirmation, and envelope contracts.

A future GUI or remote controller may reuse the session protocol. Remote transport is intentionally not implemented. Before remote access is enabled it must provide authentication, authorization, TLS, secret redaction, audit events, bounded progress streams, cancellation, and version negotiation.

Confirmation belongs in the session boundary, not a UI renderer. Mutating operations require explicit confirmation; agent/GUI clients never answer an interactive prompt.

## Windows box maintenance

Windows guest operation is not currently a first-class SPA workflow. The historical box-authoring process used a VirtualBox Windows template, WinRM, `vagrant package`, and `vagrant box add`. If Windows guests return, implement and document them through `spa` rather than restoring a second operator CLI. The detailed former recipe remains available in Git history.

## Documentation

- Well-known root files stay uppercase: `README.md`, `AGENTS.md`, `CHANGELOG.md`, `ROADMAP.md`, `RELEASE.md`.
- Other documentation uses lowercase kebab-case.
- Commands are `spa`-first; raw backend commands belong only in implementation/test context.
- Prefer links to `spa --help`, `spa features`, `spa apps`, schema, and upstream Splunk docs over duplicated reference tables.
- Never add credentials, private keys, certificates, or decrypted values to examples.
