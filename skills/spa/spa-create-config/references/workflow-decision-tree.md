# Workflow decision tree

Classify the user message, then load the one skill that owns the next step. Finish that step before loading the next skill.

```
User message
├─ New environment or lab ("I need a Splunk environment...")
│     → /spa-create-config, Phases 0a–9, plan mode
│     → plan approved → environment gate (if not passed) → init → write config (Phase 7) → spa validate (Phase 8)
│     → /spa handoff for provision and deploy (only after your explicit yes for each)
├─ Change an existing config ("add ITSI", "change the OS")
│     → /spa-create-config, "Add / change a setting" (skip greenfield phases)
│     → spa validate → /spa only if you ask to deploy
├─ Apps ("add a TA", "Splunkbase", "content pack")
│     → /spa-apps
│     → spa validate → /spa only if you ask to deploy
└─ Lifecycle ("provision", "deploy", "destroy", "status", "logs", "suspend", "resume")
      → /spa
```

Rules that apply on every branch:

- Config is changed only with `spa config` commands, never by hand.
- App entries are added only with `spa apps` commands.
- `spa init` runs once per new environment, after the location, name, and summary gate. In write mode the gate runs after Phase 3; in plan mode it runs at the start of Phase 7. It does not run on the first message.
- Nothing writes before the gate passes. Every write names its target environment and checks the `resolved_env_name` in the response.
- A new-environment request never writes to an existing environment. Change one only when the operator names it.
- Provision, deploy, destroy, suspend, resume, environment remove, and environment cleanup wait for your yes in chat.
