# Splunk Platform Automator — agent guide

Splunk Platform Automator (SPA) provisions and deploys Splunk Enterprise on **AWS Linux** using Ansible + Terraform. Configuration is driven by `config/splunk_config.yml`.

## Start here

| Task | Path / command |
|------|----------------|
| Main config | `config/splunk_config.yml` (copy from `examples/`) |
| Config keys reference | `examples/configuration_description.yml` |
| Guided human + agent workflow | [docs/Splunk_Config_Guided_Setup.md](docs/Splunk_Config_Guided_Setup.md) |
| Validate before provision | `./bin/validate_splunk_config.sh config/splunk_config.yml` |
| Provision AWS | `ap ansible/provision_terraform_aws.yml -e auto_approve=true` |
| Deploy Splunk | `ap ansible/deploy_site.yml` |
| Local tests | `./tests/run_local_tests.sh` |

## Agent skills (portable packages)

Canonical location: `skills/spa/` ([Agent Skills spec](https://agentskills.io/specification.md)).

| Skill | When to load |
|-------|----------------|
| [skills/spa/spa-create-config/SKILL.md](skills/spa/spa-create-config/SKILL.md) | Creating/updating `splunk_config.yml`, architecture planning, SVA topology, AWS `terraform.aws`, licenses, apps |
| [skills/spa/spa-add-test-scenario/SKILL.md](skills/spa/spa-add-test-scenario/SKILL.md) | App-scope routing tests in `tests/configs/app_scope/` |

**Cursor:** skills are symlinked under `.cursor/skills/` — use `/spa-create-config` and `/spa-add-test-scenario`.

**Other tools:** see [docs/Agent_Skills.md](docs/Agent_Skills.md) and [skills/spa/README.md](skills/spa/README.md).

## Secrets (mandatory)

Never display credential values in chat or terminal output.

- Splunkbase: `SPLUNKBASE_USERNAME`, `SPLUNKBASE_PASSWORD` — report **set** / **not set** only in YAML use `lookup('env', ...)`.
- AWS: prefer `python3 bin/splunk_config_aws.py --check-auth --json`; never echo `AWS_SECRET_ACCESS_KEY` or similar.

Full rules: [skills/spa/spa-create-config/references/secrets-handling.md](skills/spa/spa-create-config/references/secrets-handling.md).

## Do not

- Auto-run provision, deploy, or destroy without explicit user approval.
- Echo, `printenv`, or `grep` secret environment variables.
- Paste Splunkbase passwords or AWS secret keys into configs or chat.

## Layout

```text
ansible/          Playbooks and roles
bin/              splunk_config_aws.py, validate_splunk_config.sh, …
config/           splunk_config.yml (gitignored local copy)
examples/         Example configs and configuration_description.yml
skills/spa/       Agent skill packages (canonical)
tests/            Schema, local, and AWS deployment tests
```
