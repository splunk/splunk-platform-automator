# Workflow decision tree

Classify the user message, then load the one skill that owns the next step. Finish that step before loading the next skill.

```
User message
├─ New environment or lab ("I need a Splunk environment...")
│     ├─ Confirmed 0.4.0 architecture file given
│     │     → /spa-create-config path B (skip SVA questionnaire)
│     │     → spa architecture plan FILE → provider → location/name gate
│     │     → write: spa environment init --architecture FILE --provider
│     │     → plan: record Phases 6–11; init at Phase 12
│     │     → move role / move host / sizing / OS / AWS / apps / licenses
│     │     → spa architecture check FILE → spa validate (Phase 13)
│     │     → /spa handoff for provision and deploy (only after your explicit yes for each)
│     └─ No architecture file
│           → /spa-create-config path A, Phases 1–14, plan mode
│           → plan approved → environment gate (if not passed) → spa init --example --provider → write config (Phase 12) → spa validate (Phase 13)
│           → /spa handoff for provision and deploy (only after your explicit yes for each)
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
- `spa init` runs once per new environment, after the location, name, and summary gate. In write mode the gate runs after Phase 5; in plan mode it runs at the start of Phase 12. It does not run on the first message.
- Nothing writes before the gate passes. Every write names its target environment and checks the `resolved_env_name` in the response.
- A new-environment request never writes to an existing environment. Change one only when the operator names it.
- Provision, deploy, destroy, suspend, resume, environment remove, and environment cleanup wait for your yes in chat.
