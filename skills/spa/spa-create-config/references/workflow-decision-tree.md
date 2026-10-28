# Workflow decision tree

Classify the user message, then load the one skill that owns the next step. Finish that step before loading the next skill.

```
User message
├─ New environment or lab ("I need a Splunk environment...")
│     → /spa-create-config, Phases 0a–9, plan mode
│     → plan approved → write config (Phase 7) → spa validate (Phase 8)
│     → /spa for provision and deploy (only after your explicit yes)
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
- `spa init` runs once, at Phase 1, after the location, name, and summary gate. It does not run on the first message.
- Provision, deploy, destroy, suspend, and resume wait for your yes in chat.
