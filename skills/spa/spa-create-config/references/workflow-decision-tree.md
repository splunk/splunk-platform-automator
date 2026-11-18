# Workflow decision tree

Classify the user message, then load the one skill that owns the next step. Finish that step before loading the next skill.

```
User message
├─ New environment or lab ("I need a Splunk environment...")
│     ├─ Confirmed schema 1 architecture file given
│     │     → /spa-create-config path B (skip SVA questionnaire)
│     │     → spa architecture plan FILE → follow data.next (write mode, provider)
│     │     → location/name gate → spa environment init --architecture FILE --provider
│     │     → move role / move host / sizing / OS / AWS / apps / licenses
│     │     → spa architecture check FILE → spa validate (Phase 13)
│     │     → /spa handoff for spa deploy (creates hosts if needed; only after your explicit yes)
│     └─ No architecture file
│           → /spa-create-config path A
│           → spa init list → follow data.next (topology, then provider)
│           → location/name gate (plan vs write)
│           → write: spa environment init --example --provider → follow remaining
│           → spa validate (Phase 13)
│           → /spa handoff for spa deploy (creates hosts if needed; only after your explicit yes)
├─ Change an existing config ("add ITSI", "change the OS")
│     → /spa-create-config, "Add / change a setting" (skip greenfield phases)
│     → spa validate
│     → apps-only on an already-up lab: /spa for spa run splunk_apps_deploy (not spa deploy)
│     → other settings: /spa only if you ask to deploy
├─ Apps ("add a TA", "Splunkbase", "content pack")
│     → /spa-apps
│     → spa validate → /spa for spa hosts check then spa run splunk_apps_deploy when the lab is already up
└─ Lifecycle ("provision", "deploy", "destroy", "status", "logs", "suspend", "resume")
      → /spa
```

Rules that apply on every branch:

- Config is changed only with `spa config` commands, never by hand.
- App entries are added only with `spa apps` commands.
- `spa init` runs once per new environment, after the location, name, and summary gate. Path A: topology and provider from `spa init list` `data.next` before the gate. In write mode the gate runs after that next; in plan mode init waits for Phase 12. It does not run on the first message.
- Nothing writes before the gate passes. Every write names its target environment and checks the `resolved_env_name` in the response.
- A new-environment request never writes to an existing environment. Change one only when the operator names it.
- Provision, deploy, destroy, suspend, resume, environment remove, and environment cleanup wait for your yes in chat.
