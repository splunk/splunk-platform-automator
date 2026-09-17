# SPA agent skills

Framework-neutral [Agent Skills](https://agentskills.io/specification.md) packages for Splunk Platform Automator. **Edit content here only** — not under `.cursor/skills/` (symlinks).

## Skills

| Skill | Purpose |
|-------|---------|
| [spa](spa/) | Product entry (`/spa`): Software, environments, operator loop |
| [spa-create-config](spa-create-config/) | Design and write `config/splunk_config.yml` (plan mode, SVA topology, AWS, licenses, validation) |
| [spa-apps](spa-apps/) | Splunkbase search, kind-aware apps[] snippets, optional download |
| [spa-add-test-scenario](spa-add-test-scenario/) | Distill app-scope scenario tests under `tests/configs/app_scope/` |

Human guide: [docs/user-guide.md](../../docs/user-guide.md). Repo index: [AGENTS.md](../../AGENTS.md).

## Cursor

This repo ships symlinks:

```text
.cursor/skills/spa                  → ../../skills/spa/spa
.cursor/skills/spa-create-config  → ../../skills/spa/spa-create-config
.cursor/skills/spa-apps           → ../../skills/spa/spa-apps
.cursor/skills/spa-add-test-scenario → ../../skills/spa/spa-add-test-scenario
```

Invoke with `/spa`, `/spa-create-config`, `/spa-apps`, or `/spa-add-test-scenario`.

If symlinks are missing after clone, recreate from repo root:

```bash
mkdir -p .cursor/skills
ln -s ../../skills/spa/spa .cursor/skills/spa
ln -s ../../skills/spa/spa-create-config .cursor/skills/spa-create-config
ln -s ../../skills/spa/spa-apps .cursor/skills/spa-apps
ln -s ../../skills/spa/spa-add-test-scenario .cursor/skills/spa-add-test-scenario
```

## Claude Code (manual)

Symlink or copy the **leaf directory** (the folder that contains `SKILL.md`):

```bash
# Project-scoped (this repo only)
ln -s "$(pwd)/skills/spa/spa" .claude/skills/spa
ln -s "$(pwd)/skills/spa/spa-create-config" .claude/skills/spa-create-config
ln -s "$(pwd)/skills/spa/spa-apps" .claude/skills/spa-apps

# Or user-scoped
ln -s /path/to/splunk-platform-automator/skills/spa/spa-create-config ~/.claude/skills/spa-create-config
ln -s /path/to/splunk-platform-automator/skills/spa/spa-apps ~/.claude/skills/spa-apps
```

Repeat for `spa-add-test-scenario` if needed.

## Other agents

Load `skills/spa/spa/SKILL.md` first, then a task skill when the user works on `splunk_config.yml`, Splunkbase apps, or app-scope tests. Follow `references/` on demand.

## Windows

Git symlinks may require `git config core.symlinks true` or Windows Developer Mode. If symlinks do not work, copy `skills/spa/<name>/` into `.cursor/skills/<name>/` and prefer editing the canonical tree when syncing back.

## Validation (optional)

If you have the Agent Skills reference tooling installed:

```bash
skills-ref validate ./skills/spa/spa
skills-ref validate ./skills/spa/spa-create-config
skills-ref validate ./skills/spa/spa-apps
skills-ref validate ./skills/spa/spa-add-test-scenario
```
