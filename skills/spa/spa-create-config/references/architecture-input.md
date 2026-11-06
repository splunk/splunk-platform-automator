# Architecture input (splunk.architecture 0.4.0)

`/spa-create-config` can start from a confirmed `kind: splunk.architecture` file (schema `0.4.0`). Checked-in examples: `examples/architectures/c1.json`, `c3.json`, `m4.json`. Operator flow, mermaid diagram, and commands: [Configure an environment](../../../../docs/user-guide.md#configure-an-environment).

This skill has two first-class entry points. An architecture file is optional.

## Path A — no architecture file

Keep the existing questionnaire (Phases 1–5), location/name gate, then `spa init --example TOPOLOGY --provider`. Do not run `spa architecture plan`, `apply`, or `check`.

## Path B — confirmed 0.4.0 file present

Do not run the SVA questionnaire. Check is mandatory on this path, before validate:

1. `spa architecture plan FILE`. Acknowledge it.
2. Provider, then location/name gate (recommend `environment.name`).
3. Write mode, after the gate yes: `spa environment init PARENT/NAME --architecture FILE --provider PROVIDER`. Plan mode: record location/name; do **not** init until Phase 12.
4. Host ↔ role map; `spa config move role` / `config add` as answered.
5. Optional `spa config move host --prefix` / `--postfix` / `move host OLD --to NEW`.
6. Sizing, OS, AWS if `aws`. For a shipped bundle such as remote-provider defaults, `spa --agent config templates list` then `spa --agent config merge NAME --yes`. Keep `merge --file` for an operator-authored fragment.
7. Apps (always ask Phase 9). SPA ignores `apps.by_role` (ClusterBaseConfigs / BaseConfigs); it installs PS baseconfigs internally from `splunk_baseconfig_dir`. Do not AskQuestion about importing those folders as local apps. ES search heads may already exist; app 263 still goes through `/spa-apps` if they want ES.
8. Licenses. If a file is chosen and `license_manager` is missing, say so and add it.
9. **`spa architecture check FILE` (required).** Then `spa validate`. Phase 14 handoff.

`/spa` given an architecture file loads this skill on path B; it does not provision.

```bash
spa architecture plan examples/architectures/c3.json
spa environment init PARENT/NAME --architecture examples/architectures/c3.json --provider aws
spa config move role license_manager --from cm --to lm --yes
spa config move host --prefix acme- --yes
spa config move host --postfix=-lab --yes
spa architecture check examples/architectures/c3.json
spa validate
```

`--architecture` and `--example` are exclusive. `confirmed: false` refuses init and apply. Plan warns and still prints the overlay.

Do not parse the architecture file in this skill. `spa architecture plan FILE` is the reader. The checked-in shape is `examples/architectures/c3.json`. SPA ignores `apps.by_role` and `delivery`. It installs PS baseconfigs itself; do not add those folders via `/spa-apps`. If `secrets` is present, only environment variable **names** are collected; values are never shown. Phases 9 and 10 (apps and licenses) are still asked.

## Version gate

Supported version is `0.4.0`. Missing `kind` or `schema_version` is an error. Newer than `0.4.0`: upgrade spa. Older (including unreleased `0.3.0`): not supported. Do not default a missing version.

## Rules

- Every `deployment.roles` entry must map to an AllowedRole. An unknown extra role is a hard error.
- Architecture overlay still defers writing `license_manager` until a license file is set. The schema allows an LM host without files (trial). Plan still shows the proposed host. Init and apply warn and list `license_manager` under Remaining; they do not fail. After licenses, add it if missing, then `spa architecture check`.
- Indexers and SHC members stay on their own hosts. Overlay scales `idxN` / `shN`.
- Secret-shaped values are rejected and never echoed.
