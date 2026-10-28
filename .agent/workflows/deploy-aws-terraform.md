---
description: Legacy pointer. AWS Terraform deploy now runs through the /spa and /spa-create-config skills.
---

# Deploy Splunk to AWS (legacy workflow)

This file is a legacy runbook. The skills own the flow now. Agents use `/spa-create-config` to design and write `config/splunk_config.yml`, and `/spa` for every lifecycle command. Do not follow step lists from older copies of this file.

## Rules that apply

- Use only `spa` from the environment directory (`SPA_ENV_DIR`), or pass `--env NAME`. Do not call `ansible-playbook`, `terraform`, or `python3 bin/…` directly.
- Never edit `config/splunk_config.yml` by hand. Change it with `spa config …`.
- `provision`, `deploy`, `destroy`, `suspend`, `resume`, and `environment remove` each wait for an explicit yes in chat for that run. A request in the same message is not that yes. Then pass `--yes`.
- Do not pass `-v` or `--ansible-output` to `provision`, `deploy`, or `run`.
- Use full command names: `spa hosts ssh <host>`, not `spa sh`.

## Where each step lives

| Step | Owner |
|------|-------|
| Design, AWS settings, and config writes | `/spa-create-config` |
| Credential probe | `spa aws --check-auth --json` (report set / not set only) |
| Preview, provision, host check, deploy, suspend, resume, destroy | `/spa` |
| Host status and SSH | `spa hosts list --status`, `spa hosts ssh <host>` |
| Logs | `spa logs --last` |
