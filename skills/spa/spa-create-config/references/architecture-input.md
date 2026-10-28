# Architecture input (JSON from another skill or CI)

Use this when the user gives a path to a JSON file with architecture decisions. The file is read in chat. There are no CLI flags for it: the agent reads the file, validates it, and follows the rules below. Every config change still goes through `spa --agent config set`, `add`, or `merge` (see [SKILL.md](../SKILL.md)).

## Contract

Each phase is an object with `confirmed` (boolean). Phases can be omitted.

```json
{
  "metadata": { "source_skill": "architecture-planner", "version": "1.0" },
  "environment": { "name": "rhel10-single" },
  "phase_0a": { "intent": "Feature / app lab", "confirmed": true },
  "phase_0b": { "workload": "moderate", "retention_period": "30-90 days", "confirmed": true },
  "phase_1": { "topology": "single_node", "confirmed": true },
  "phase_2": { "instance_type": "t3.xlarge", "root_volume_size": 50, "confirmed": true },
  "phase_3": { "os": "rhel10", "ssh_username": "ec2-user", "confirmed": true },
  "phase_4": { "provider": "aws", "region": "eu-central-1", "ami": "ami-xxxxxxxx", "confirmed": true },
  "phase_5b": { "placement_strategy": "all-roles-colocated", "confirmed": true },
  "phase_6": { "apps": [], "confirmed": true },
  "phase_6b": { "license_file": "Splunk_Enterprise.lic", "license_manager_host": "shidx", "confirmed": true }
}
```

Values are suggestions until checked against `spa --agent config search` and `spa --agent config explain PATH`. Topology ids come from `spa init list`.

## Processing

1. **Load and validate.** Read the file. If it is not valid JSON, or a value is not a legal option, show each error with its phase and key, then ask: fix the file and retry, start over, or override the value now. Do not guess a replacement.
2. **Reject credentials.** If any key looks like a secret (`password`, `secret`, `token`, `key`, `credential`), stop and ask the user to remove it. Never print the value. Splunkbase and AWS secrets come from env vars, not from this file.
3. **Record the source.** Every value gets the source `Architecture file` in the reconfirmation table.
4. **Skip the covered collection.** For a phase with `"confirmed": true`, use the value and do not ask again, except for phases 6 and 6b (see below). For `"confirmed": false` or a missing phase, collect it from the user as normal.
5. **Apps and licenses are still asked.** Phases 6 and 6b are asked even when `confirmed` is true. The JSON value is shown as the proposed answer ("Use these apps?", "Use this license?"). This keeps the mandatory reconfirmation from the Pre-Phase Checkpoint.
6. **Reconfirmation table.** Show every value with its source before Phase 7, as described in the Reconfirmation Checkpoint section of [SKILL.md](../SKILL.md). Phase 7 starts only after the explicit yes.

## Conflicts

If values conflict with the topology (for example an instance type too small for the topology), show a warning and ask the user to override or keep the value. Do not change it silently.

## Out of scope

- Remote URLs and environment-variable input.
- Any `spa` command that imports the file. The file is only read by the skill.
