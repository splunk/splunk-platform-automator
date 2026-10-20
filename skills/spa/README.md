# SPA agent skills

Framework-neutral [Agent Skills](https://agentskills.io/specification.md) packages for Splunk Platform Automator. Edit content only under `skills/spa/`.

## Skills

| Skill | Purpose |
|-------|---------|
| [spa](spa/) | Product entry (`/spa`): Software, environments, operator loop |
| [spa-create-config](spa-create-config/) | Design and write `config/splunk_config.yml` (plan mode, SVA topology, AWS, licenses, validation) |
| [spa-apps](spa-apps/) | Splunkbase search, kind-aware apps[] snippets, optional download |
| [spa-add-test-scenario](spa-add-test-scenario/) | Distill app-scope scenario tests under `tests/configs/app_scope/` |

Human guide: [docs/user-guide.md](../../docs/user-guide.md). Repo index: [AGENTS.md](../../AGENTS.md).

## Install

`spa skills install` links these packages into the user IDE skill directory. It does not write skills into this repo or into an environment directory.

```bash
spa skills install                          # SPA_SKILLS_PLATFORMS, or one detected IDE
spa skills install cursor
spa skills install cursor,claude            # comma-separated; aliases allowed
export SPA_SKILLS_PLATFORMS=cursor,claude-code
spa skills remove --yes
```

Platforms: `claude-code` (`claude`), `cursor`, `codex`, `opencode`, `windsurf`, `gemini-code` (`gemini`), `pi` (`pi-dev`), `antigravity` (`agy`), or `all`. Pass several as one comma-separated argument (`cursor,claude`). An explicit platform ignores `SPA_SKILLS_PLATFORMS`. When several IDEs are present and the variable is unset, name the platform.

Install prefers a symlink to `$SPA_HOME/skills/spa/<name>`. An existing directory or link with that package name is replaced. Other names in the IDE skill directory stay. If the OS cannot create a symlink, the package is copied and recorded in `~/.config/spa/skills.yml`. `spa skills remove` deletes only registered package names and requires `--yes`.

## Other agents

Load `skills/spa/spa/SKILL.md` first, then a task skill when the user works on `splunk_config.yml`, Splunkbase apps, or app-scope tests. Follow `references/` on demand.

## Validation (optional)

If you have the Agent Skills reference tooling installed:

```bash
skills-ref validate ./skills/spa/spa
skills-ref validate ./skills/spa/spa-create-config
skills-ref validate ./skills/spa/spa-apps
skills-ref validate ./skills/spa/spa-add-test-scenario
```
