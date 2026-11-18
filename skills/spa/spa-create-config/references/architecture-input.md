# Architecture input (splunk.architecture schema 1)

`/spa-create-config` can start from a confirmed `kind: splunk.architecture` file (schema `1`, JSON integer). Checked-in examples: `examples/architectures/c1.json`, `c3.json`, `m4.json`. Operator flow, mermaid diagram, and commands: [Configure an environment](../../../../docs/user-guide.md#configure-an-environment).

This skill has two first-class entry points. An architecture file is optional.

## Path A — no architecture file

Follow spa envelopes. Do not run architecture `plan`, `apply`, or `check` on this path. No `spa config wizard`. Phases 1–2 (intent/requirements) are optional header input, not blockers before `spa init list`. Optional SVA help ([sva-questionnaire.md](sva-questionnaire.md)) is "needs help", then `spa init list` — not the default loop.

1. `spa init list`. Follow `data.next`: topology from the catalog (do not dump every stem as `choice.allowed`), then provider over `choice.allowed`.
2. Location/name gate (explicit yes). Path A still AskQuestions plan vs write here.
3. Write mode: `spa environment init PARENT/NAME --example TOPOLOGY --provider PROVIDER`.
4. Follow init `data.next` / `remaining` in order (explain, latest-ami, apps, licenses). AskQuestion each `ask`, then run `command` / `argv`. Do not invent follow-ups the envelope omitted. If remaining omitted apps or licenses because the config already settled them, do not re-ask. If remaining includes them, AskQuestion those items (that is the mandatory ask).
5. `spa validate` (follow validate `next` for missing required keys). Phase 14 handoff unchanged.

Plan mode: collect location and name at the gate; do not init. Record remaining answers. Init and writes run at Phase 12 after the plan is approved.

## Path B — confirmed schema 1 file present

Do not run the SVA questionnaire. Check is mandatory on this path, before validate:

1. `spa architecture plan FILE`. Follow `data.next`. `mode.write` means the architecture file is the plan; do not AskQuestion plan vs write.
2. AskQuestion `provider` over `choice.allowed`, then the location/name gate (recommend `environment.name`).
3. After the gate yes: `spa environment init PARENT/NAME --architecture FILE --provider PROVIDER` (copy `argv` / `command` from `mode.write`).
4. Host ↔ role map; `spa config move role` / `config add` as answered.
5. Optional `spa config move host --prefix` / `--postfix` / `move host OLD --to NEW`.
6. Follow remaining for hardware, OS, and AWS. CCM only when CCM is in play: size from `spa provider ccm survey` / `operating-systems list` / `instance-types list` / `disk-storage list`, not a hardcoded catalog. Follow survey `data.next`: set `ccm.operating_system`, `ccm.instance_type`, and `ccm.disk_storage` once for all hosts; do not ask per role. Write YAML with `spa config provider ccm` (that is not `spa provider ccm`). Auth is `CCM_TOKEN` (set / not set). Remote-provider defaults (hostname, host-side download, TLS) are already in `spa init` for AWS, CCM, and external (not VirtualBox). For an existing env that lacks them, `spa --agent config templates list` then `spa --agent config merge remote-provider --yes`. Keep `merge --file` for an operator-authored fragment.
7. Follow remaining for apps and licenses. If remaining omitted them, do not re-ask. If remaining includes them, AskQuestion those items. SPA ignores `apps.by_role` (ClusterBaseConfigs / BaseConfigs); it installs PS baseconfigs internally from `splunk_baseconfig_dir`. Do not AskQuestion about importing those folders as local apps. ES search heads may already exist; app 263 still goes through `/spa-apps` if they want ES.
8. If remaining includes licenses and a file is chosen and `license_manager` is missing, say so and add it.
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

Do not parse the architecture file in this skill. `spa architecture plan FILE` is the reader. The checked-in shape is `examples/architectures/c3.json`. SPA ignores `apps.by_role` and `delivery`. It installs PS baseconfigs itself; do not add those folders via `/spa-apps`. If `secrets` is present, only environment variable **names** are collected; values are never shown. If remaining omitted apps or licenses, do not re-ask. If remaining includes them, AskQuestion those items.

## Version gate

Supported version is JSON integer `1`. Missing `kind` or `schema_version` is an error. Bool and string values (including `"1"` and `"0.4.0"`) are rejected. Newer integer: upgrade spa. Older integers are not supported. There is no 0.4.0 migrator. Do not default a missing version.

## Rules

- Every `deployment.roles` entry must map to an AllowedRole. An unknown extra role is a hard error.
- Architecture overlay still defers writing `license_manager` until a license file is set. The schema allows an LM host without files (trial). Plan still shows the proposed host. Init and apply warn and list `license_manager` under Remaining; they do not fail. After licenses, add it if missing, then `spa architecture check`.
- Indexers and SHC members stay on their own hosts. Overlay scales `idxN` / `shN`.
- Secret-shaped values are rejected and never echoed.
