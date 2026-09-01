# Agent skills for SPA

SPA ships portable [Agent Skills](https://agentskills.io/specification.md) packages so Cursor, Claude Code, and other agents can follow the same workflows.

## Canonical location

All skill content lives under **`skills/spa/`**. Each skill is a directory with `SKILL.md` plus optional `references/`, `assets/`, and `scripts/`.

| Skill | Directory |
|-------|-----------|
| Guided `splunk_config.yml` setup | `skills/spa/spa-create-config/` |
| App-scope test scenarios | `skills/spa/spa-add-test-scenario/` |

Index: [skills/spa/README.md](../skills/spa/README.md). Repo overview: [AGENTS.md](../AGENTS.md).

## Cursor

The repo includes symlinks so Cursor discovers skills automatically:

```text
.cursor/skills/spa-create-config → ../../skills/spa/spa-create-config
.cursor/skills/spa-add-test-scenario → ../../skills/spa/spa-add-test-scenario
```

Use `/spa-create-config` or `/spa-add-test-scenario` in chat.

If skills do not appear after clone, recreate symlinks (see [skills/spa/README.md](../skills/spa/README.md#cursor)).

## Claude Code

No `.claude/skills/` adapters are committed. Install manually:

```bash
# From SPA repo root — project-scoped
mkdir -p .claude/skills
ln -s "$(pwd)/skills/spa/spa-create-config" .claude/skills/spa-create-config
ln -s "$(pwd)/skills/spa/spa-add-test-scenario" .claude/skills/spa-add-test-scenario
```

Or link into `~/.claude/skills/` for all projects.

## Generic agents

Point the agent at `skills/spa/<skill-name>/SKILL.md` when the user:

- Designs or edits `config/splunk_config.yml`
- Plans SVA-aligned lab topology on AWS
- Adds app-scope tests under `tests/configs/app_scope/`

Load `references/` files only when the task needs depth (progressive disclosure).

## Validation (optional)

With [skills-ref](https://agentskills.io/specification.md) installed:

```bash
skills-ref validate ./skills/spa/spa-create-config
skills-ref validate ./skills/spa/spa-add-test-scenario
```

## Maintenance

- **Edit only** `skills/spa/` — never duplicate content under `.cursor/skills/` (symlinks).
- After changing skills, run `./tests/run_local_tests.sh -q` (skills are not unit-tested; ensures repo integrity).
- Related human doc: [Splunk_Config_Guided_Setup.md](Splunk_Config_Guided_Setup.md).

## Windows

Symlinks may require `git config core.symlinks true` or Developer Mode. Fallback: copy `skills/spa/<name>/` to `.cursor/skills/<name>/`.
