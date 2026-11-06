# Create-config phases

Load one section at a time from this file. Hard rules stay in [SKILL.md](../SKILL.md).

## Step 0 — Environment setup

**Entry:** User wants a deployment config or a design summary (plan mode).

**Actions:**

1. Confirm **project root** (contains `ansible.cfg`, `bin/`).
2. **Mode** — not asked here. The plan-or-write question is asked in the gate, after the minimum requirements (topology, provider, OS) are defined and before init. If the user already stated intent, note it now and confirm it at the gate:
   - **plan** — Phases 1–10 + design summary; **no** `splunk_config.yml` write until user approves.
   - **write** — Full flow through Phase 12–14 (or continue after approved plan).
   Infer **plan** from phrases like “design”, “discuss”, “plan architecture”; infer **write** from “create config”, “write yaml”, “approve and write”.
3. Target: the environment chosen at the gate, or the named existing environment under "Add / change a setting". Its config is `<env path>/config/splunk_config.yml`. Never assume the current directory or the registry default is the target.
4. If the target config already exists and **mode=write** (or approving plan): **merge vs overwrite** — AskQuestion if available, otherwise ask in chat, before any write. Skip in **plan** mode until Phase 12.
5. **AWS API probe** — `spa --agent aws check-auth` (needs `boto3`; no region required). Read `ok` and `data.account`. Record result:
   - **Available** → Phase 6 uses API discovery; optional `spa validate --splunk-config aws` at validate.
   - **Unavailable** → follow [aws-without-credentials.md](aws-without-credentials.md); do not block the workflow.
6. Read existing config if merging or revising an existing plan from prior config.
7. Licenses are not scanned here. Phase 10 scans the Software directory once, after the apps decision.
8. **Architecture input (optional).** Two entry points: [architecture-input.md](architecture-input.md). **Path A (no file):** keep this questionnaire and `spa init --example TOPOLOGY --provider` (write mode at the gate; plan mode at Phase 12). **Path B (confirmed 0.4.0 file):** skip the SVA questionnaire; run `spa architecture plan FILE`, then the same init timing, place/size with `spa config move`, then **`spa architecture check FILE` before validate**. Phases 9 and 10 are always asked, even when `confirmed` is true. SPA ignores `apps.by_role`; it installs PS baseconfigs internally. Do not import those folders as local apps.

**Exit:** Intent noted (mode is confirmed at the gate); target path known; merge policy clear when applicable; **AWS API status recorded**; if a file was given, `spa architecture plan FILE` has been run (the skill does not parse the JSON).

## Pre-Phase Checkpoint — user input classification

After Step 0, classify what the user has already specified. Phases marked "Can skip" need no question when the value is clear. Phases marked "Must reconfirm" are always asked.

| User Specified | Can Skip | Must Reconfirm |
|---|---|---|
| Topology only | 2, 8 | 9, 10 |
| Topology + OS | 2, 5, 8 | 9, 10 |
| Topology + OS + sizing | 2, 4, 5, 8 | 9, 10 |
| All four (topology, OS, sizing, provider) | 2, 4, 5, 6, 8 | **9, 10 (MANDATORY)** |

**MANDATORY:** Phase 9 (apps) and Phase 10 (licenses) are asked every time before Phase 12. Skipping a phase is recorded in the reconfirmation table before Phase 12.

## Phase 1 — Deployment intent

Ask: *What are you proving with this environment?*

| Intent | Behavior |
|--------|----------|
| Config / infra test | Minimal hosts; lab co-location OK; flag SVA gaps |
| Feature / app lab | Right tier sizes; Java 21 for ITSI; licenses |
| Production-like | SVA separation; multisite; document RTO/RPO |

See [architecture-requirements.md](architecture-requirements.md).

**Exit:** Intent recorded for header comment.

## Phase 2 — Architecture requirements

Gather workload, DR, data path, retention (light touch). Feed into SVA path; do not duplicate blindly.

Ask scale-out vs scale-up; default **scale out** for Splunk.

**Exit:** Short requirements summary for header.

## Phase 3 — Topology path

**Entry:** Requirements known or skipped for config-test. Path B (confirmed architecture file): skip this questionnaire; `sva.code` selects the topology at init.

| Path | Action |
|------|--------|
| User knows SVA code | Confirm code → [sva-topology-map.md](sva-topology-map.md) → record the topology id. Init runs at the location, name, and summary gate after Phase 5. |
| Needs help | [sva-questionnaire.md](sva-questionnaire.md) then `spa --agent config search` |
| Config test only | Minimal topology (`single_node` or `cm_2idxc_sh`) |

**Exit:** SVA code or lab compromise; topology id from `spa init list` (not a mixed `_aws` file).

## Phase 4 — Sizing tier

| Purpose | Default |
|---------|---------|
| Config test | `t3.medium`, 50 GB global `terraform.aws` |
| App lab | Larger SH if needed; ITSI Java 21 |
| Production-like | Document overrides |

**Exit:** Default instance type and volume size for global block.

## Phase 5 — Linux OS

Pick OS via `spa --agent config search os`, then `spa --agent config explain os`, `os.packages`, or `terraform.aws.ssh_username`. Author each chosen leaf with `spa --agent config set`; never `config set os '{whole map}'`. Omit schema-default booleans. Do not pass OS through `spa init`.

**Recommended:** Amazon Linux 2023, RHEL 10, or Ubuntu 24.04 LTS (latest AMI in region).

Set `os.packages` (acl plus **polkit** on AL/RHEL or `policykit-1` on Ubuntu), `os.set_hostname` if chosen, and `terraform.aws.ssh_username`.

**Exit:** OS family chosen; `os:` template ready.

## Environment location, name, and summary (mandatory before init)

Run this before the first `spa init` or `spa environment init` for a new environment. Skip it when the operator names an existing environment to change (see "Add / change a setting").

**Minimum requirements first:** Path A: the topology (Phase 3), the provider, and the OS (Phase 5) must be chosen before this gate. Path B: `spa architecture plan FILE` acknowledged and the provider chosen; OS and sizing come after init. AWS settings (Phase 6) are set after init with `spa config set`, so they do not block the name.

1. **Mode** — ask plan or write (see Step 0, item 2). Use AskQuestion if available, otherwise ask in chat, unless the user already chose one. Do not ask this before the minimum requirements above are defined. **Plan:** collect location and name (steps 2–5). Do **not** run step 6 (`spa init`). Phases 6–10 become recorded values. Init and every `spa config` / `spa apps add` run at Phase 12 after the plan is approved. **Write:** continue with steps 2–6 now, including init after the step-5 yes.

2. **Gather facts (read-only).**
   - Current directory: `pwd`.
   - Registered environments: `spa --agent environment list`. Each row has `name`, `path`, `default`, and `exists`.
   - If the current directory is the SPA framework checkout (it contains `bin/spa` and `ansible.cfg`) or lies inside `SPA_HOME`, do not recommend it. Recommend the default parent from `spa environment list` instead, and say why.
   - Existing target: a proposed `PARENT/NAME` whose folder exists, or whose name is already registered, is not a new environment. Do not init it or write to it. Write to it only when the operator names it as the environment to change ("Add / change a setting"), and only after a merge-vs-overwrite answer.

3. **Ask the location** with AskQuestion, or in chat if AskQuestion is not available. Offer these options, in this order:
   - `<current directory>/<NAME>`: **recommended default**.
   - The parent folder of each registered environment whose `exists` is true. Show each parent once, with its path.
   - A new path that the operator types.

4. **Recommend a name.** Path A: derive one name from topology and OS, for example `rhel10-single`, `cm-2idx-sh-aws`, or `itsi-lab-vbox`. Path B: prefer `environment.name` from `spa architecture plan`. Use lowercase letters, digits, and hyphens. The folder name is the registry name by default. Use `--name` only when the operator wants a registry name that differs from the folder. The name must not match a `name` in `spa environment list`; if it does, add a suffix. Ask the operator to accept it or type another name.

5. **Summarize and wait for yes.** Show exactly what will run:
   - Name, full path (parent plus name), provider, topology example, OS, and whether the parent is already registered.
   - The command: path A `spa environment init PARENT/NAME --example TOPOLOGY --provider PROVIDER`; path B `spa environment init PARENT/NAME --architecture FILE --provider PROVIDER`. `--architecture` and `--example` are exclusive. Add `--name REGISTRY_NAME` only when the registry name differs from the folder name.
   - What it does: creates the folder, scaffolds `config/splunk_config.yml`, and registers the name. Every later write goes to this environment only.
   - Wait for an explicit yes in chat. A request in the same message is not the yes.

6. **Run init only after the yes, and only in write mode.** Plan mode skips this step; Phase 12 runs it. Write mode then continues with Phase 6 (AWS settings) and the later config steps, and the app step (Phase 9).

**Write barrier.** Until step 6 has run, no writing command runs: no `spa init`, `spa environment init`, `spa architecture apply`, `spa config set|add|unset|merge|move|topology|provider|header set`, or `spa apps add|remove`. These stay allowed: `spa architecture plan`, `spa --agent config search|explain|get`, `spa aws ...`, `spa --agent environment list`, `spa --agent licenses list`, and `spa --agent apps search|snippet`.

**Target check (every write).** Pass `--env NAME` on each write, or run it from the target directory. Config and apps success envelopes include `resolved_env_name`, `env_dir`, and `config_file`. After each write, confirm they match the step 5 target. If they do not, stop, report the mismatch, and do not run another write. Never write to the registry default by accident.

## Phase 6 — AWS settings

**With creds:** Run named `spa --agent aws` actions — see [aws-baseline.md](aws-baseline.md). Read `data.*` from the envelope.

1. **Region.** Run `spa --agent aws regions list` immediately before AskQuestion. Option 1 is **only** `data.aws_config_region`, first, marked as the default, labelled exactly ``<region> (from AWS config, profile <aws_config_profile>)``.
   - Do not use `selected`, `region`, or `region_source`. Those can be `AWS_REGION` or scaffold `terraform.aws.region` (`eu-central-1` in `examples/providers/aws.yml`), not a choice.
   - Never mark `us-east-1` as default unless `data.aws_config_region` is exactly `us-east-1`. No city names. If `data.aws_config_region` is null, show no default. Never choose a default from your own knowledge.
   - Then up to four other names from `data.items`, common regions first (`us-east-1`, `us-west-2`, `eu-central-1`, `ap-southeast-1` when present), and "Other: type a region".
   - If `ok` is false, `data.items` is empty. Still show option 1 from `data.aws_config_region`, and offer "Other".
   - Use the "Recommended" label only on option 1, and only when it came from `data.aws_config_region`.
2. AMI — if unknown, `spa --agent aws latest-ami --region REGION --os <rhel|ubuntu|amazon_linux|debian>` or `spa --agent aws survey --region REGION` → user picks from `data.recommended_amis` (preference: RHEL first). REGION is the Phase 6 region, the same as `terraform.aws.region`; every AMI lookup names it.
3. `ssh_username` (`spa --agent aws describe-ami --region REGION --ami-id AMI_ID`)
4. Instance type (`spa --agent aws instance-types list --family t3`; suggest `t3.medium` for config tests)
5. Key pair (`spa --agent aws key-pairs list`)
6. Security groups (`spa --agent aws security-groups list`)
7. Local: `ssh_private_key_file`, tags, volume size
8. `spa --agent aws validate` before write

**Without creds:** [aws-without-credentials.md](aws-without-credentials.md) — static matrix, example AMIs, user-supplied key/SG names; **warn AMIs may be stale**; header note `AWS API: not available`. Do **not** run `spa validate --splunk-config aws`.

Cap displayed API results (~10–15 AMIs, ~5 instance types).

**Exit:** All `terraform.aws` fields chosen (API-validated if creds available, else documented as unverified).

## Phase 7 — Topology counts

Determine roles and node counts (not host mapping yet):

- IDXC vs standalone indexers
- Multisite: `site`, RF/SF — [sva-topology-map.md](sva-topology-map.md) + [rf-sf-sizing.md](rf-sf-sizing.md) (Splunk doc formulas; ingest/users → performance table)
- Standalone SH vs SHC (min 3)
- MC, LM, DS, HF, UF needed?

Start from the example chosen at Phase 3 (path A) or from `spa architecture plan FILE` (path B; the overlay exists only after init). Do not run init again. Do not rebuild host counts from the JSON by hand. Set remaining `splunk_idxclusters` / `splunk_shclusters` values with `spa --agent config set` or `add`, in write mode after the gate or in plan mode at Phase 12. Path B extras and co-location use `spa config move`. Apply the RF/SF table from the topology map.

**Exit:** Tier counts documented; RF/SF match peer counts per checklist.

## Phase 8 — Role placement

[role-placement.md](role-placement.md) — strategy: SVA-aligned, lab-minimal, hybrid, or user-defined.

Enforce SPA hard constraints (CM+idxcluster, deployer+shcluster, LM+license file, etc.).

Summarize hosts before YAML write.

**Exit:** Host ↔ role map; strategy for header.

**Next:** Phase 9 (apps). Do not skip to 10, 11, or 12 until Phase 9 has an answer, even when the user did not mention apps.

## Phase 9 — Apps (mandatory reconfirmation)

Always ask, even when the user did not mention apps. Use AskQuestion if available, otherwise ask in chat:

- **Yes, add apps:** ask the [apps-questionnaire.md](apps-questionnaire.md) sections in order, one AskQuestion each, using [/spa-apps](../../spa-apps/SKILL.md): (a) Premium ITSI (section 5); (b) ITSI content packs (section 6), only if ITSI is yes; (c) technical add-ons (section 7): ask which technologies, such as Windows, Linux, Cisco, or AWS, then run `spa --agent apps search TECHNOLOGY` for each and offer only the apps those searches return; (d) local org apps (section 8). Never offer an app from memory or with a generic query such as "common". Each `spa --agent apps add` uses the `app_id` from a search result.
- **No, trial-only:** reconfirm once: "Confirmed: no apps for this environment. Continue?" Leave out `splunk_app_deployment` only after that yes.

**Loop (when the answer is yes):**

1. Search and add one app with [spa-apps](../../spa-apps/SKILL.md). For a normal app, ask with AskQuestion which roles it goes to before `spa --agent apps add`. ITSI and content packs have no roles question.
1b. **ITSI (1841) first.** Do not refuse the add for missing license files. Follow `data.next` after the add: licenses list is optional (skip = trial / IT Essentials Work), then AskQuestion `none` / `list` / `name` for content packs. On `list`, run `spa --agent apps content-packs list 5391` and present each pack `name` / `title` (and `spa_automation` when present). On `name`, wait for folder names. On `none`, skip. Add each chosen pack with `spa --agent apps add 5391 --content-pack NAME`. Then go to step 2.
2. After each add, ask with AskQuestion: **"Add another app?"** Options: Yes, add another; No, done with apps.
3. On yes, repeat from step 1 until the operator answers no. Do not skip the question after any add.
4. On no, show the current list with `spa --agent config get splunk_app_deployment` and confirm it is right. Then move on to Phase 10.

The loop ends only when the operator answers no. Apps added in this session go into the reconfirmation table with source "User input (chat)". In plan mode, record each app ID and its roles in the plan. Run `spa --agent apps add` only in Phase 12, after the environment gate.

**Exit:** App list confirmed in the loop (at least one app added, or trial-only confirmed).

## Phase 10 — Licenses

[licenses.md](licenses.md). Run **after Phase 9** so ITSI detection is accurate. Always ask, even when no license file is found: a trial-only decision is reconfirmed before Phase 12.

```bash
spa --env NAME --agent licenses list
```

1. Scan the Software directory for `*.lic` / `*.License` and inspect sanitized parsed
   metadata: `license_type`, `group_id`, `addons`, `capabilities`, `expires_at`,
   and `status`. Never expose raw license XML, signatures, or GUIDs.
2. Always ask (AskQuestion if available), after showing the scan. This step runs whether or not a file was proposed:
   - **Files found:** add the proposed file, pick another from the list, or stay trial-only.
   - **No usable file:** stay trial-only, or add a license file to the Software directory before deploy.
   Trial-only is reconfirmed once: "Confirmed: trial-only license. Continue?"
3. **If user accepts a license file** → add `license_manager` role on a host in Phase 8 (typical lab: co-locate on `cm` or dedicated `mc`).
4. **ITSI in config** → the `license_manager` **role** is required (Phase 8). License *files* are optional: AskQuestion; skip means ITSI runs as IT Essentials Work. Do not infer capability from filenames.
5. **Enterprise Security in config** (app ID `263` or exact ES name) → require parsed `enterprise` + `es` capabilities. `premium_app: es` is not supported by the deployment schema; do not add it.
6. **License manager role** → warning if no `splunk_license_file` (trial until files are added). **License file in config** → `license_manager` role is required (schema).
7. Reject configured files that are missing, invalid, expired, or do not collectively satisfy the selected premium apps. Warn for expiration within 30 days or an unknown expiration.
8. **Trial-only, after the reconfirmation in step 2** → omit both `splunk_license_file` and `license_manager`. Do not add a license file from the Software scan alone.

Use `spa --agent config explain splunk_defaults.splunk_license_server` or the licenses result's `proposed_splunk_license_file`, then author it under `splunk_defaults` in Phase 12 with `spa --agent config set`.

**Exit:** License decision confirmed (a file added, or trial-only after reconfirmation); LM + ITSI/ES warnings addressed.

## Phase 11 — Design summary (plan mode)

This is the chat write-preview before YAML. It is not `spa architecture plan FILE` (that command already ran on path B). Path B still runs this step for OS, AWS, apps, licenses, and placement.

**Entry:** `mode=plan`. Write mode skips to the reconfirmation table.

**Actions:**

1. Fill [design-summary-template.md](../assets/design-summary-template.md) from phase exits (1–10). The summary must show:
   - **Infrastructure:** provider, region, instance type, OS, storage size.
   - **Splunk topology:** each host and its roles, and the SVA target.
   - **Apps:** the count, and which are premium (ITSI, content packs).
   - **License:** the file name, or trial-only.
   - **Environment variables:** `SPLUNKBASE_USERNAME`, `SPLUNKBASE_PASSWORD`, and the AWS profile or key variables, each as set / not set only.
2. Present the summary in chat. Offer optional file: `docs/plans/<short-name>-design-summary.md`.
3. Continue to the reconfirmation table. Do not ask for a second yes here.

**Revision loop:** User changes (“add multisite”, “drop HF”) → update affected phases mentally, refresh the summary; do **not** write YAML.

**Exit:** Summary presented. The one yes that starts Phase 12 is the reconfirmation table.

## Reconfirmation Checkpoint (before Phase 12)

Show one table of every decision and where it came from:

| Phase | Source | Value | Status |
|---|---|---|---|
| 1 Intent | User input (chat) | e.g. Feature / app lab | Confirmed |
| 2 Requirements | Auto-skip or default | e.g. moderate workload | Confirmed |
| 3 Topology | User input (chat) or architecture file (`sva.code`) | e.g. `single_node` | Confirmed |
| 4 Sizing | User input (chat) | e.g. `t3.xlarge` | Confirmed |
| 5 OS | User input (chat) | e.g. RHEL 10 | Confirmed |
| 6 Provider | User input (chat) | e.g. AWS `eu-central-1` | Confirmed |
| 8 Placement | User input (chat); path B starts from the overlay then `config move` | e.g. LM on `lm` | Confirmed |
| 9 Apps | User input (chat) | none, or app IDs | Reconfirm now if not yet answered |
| 10 Licenses | Software scan | file, or trial-only | Reconfirm now if not yet answered |

Sources: `User input (chat)`, `Architecture file`, `Auto-skip (fully specified)`, `Default`. Status: `Confirmed` or `Reconfirm now`.

Answer every `Reconfirm now` row first. Then ask: "Confirm all values and write the config?" Wait for an explicit yes in chat. Phase 12 does not start without it. A request in the same message is not the yes.

## Phase 12 — Write config

**Entry:** the reconfirmation table is confirmed. `mode=write` still waits for that yes. “approve and write config” counts as that yes.

**Do not enter** until it. A request in the same message is not the yes.

1. **Gate check.** Before the first write, confirm the environment gate passed in this session: step 6 ran init for the target, or the operator named an existing environment under "Add / change a setting". In plan mode, run steps 2–6 here first. If neither holds, STOP and run the gate. Do not run init again here. Do not invent `--addon` or OS flags on init.
2. Header values are captured as each phase closes, not reconstructed at write time:

   | Phase | Header flag |
   |---|---|
   | 1 Intent | `--intent` |
   | 2 and 4 Requirements and sizing | `--requirements` |
   | 3 Topology | `--sva` |
   | 5 OS | `--os` |
   | 6 AWS | `--aws` (API-verified, or the unverified note) |
   | 8 Placement | `--placement` |
   | 10 License | `--license` |
   | Operator-named installer | `--installer` |
   | 14 Deploy command | `--deploy` |

   After the operator confirms, run `spa --agent config header set` (`spa config header set`) with those values. Include a flag only when its phase produced a value. Omitted fields are removed, so a missing value is an open question for the operator, not a blank. Pass `--yes`. The field list and examples are in `spa config header set --help`.
3. For OS, SSL, licenses, RF/SF, and other settings: choose with `spa --agent config search QUERY`, then `spa --agent config explain PATH`. Use the one command on that page. That is `spa --agent config set PATH VALUE` for an existing scalar or map, or `spa --agent config add SELECTOR JSON_OBJECT` for a new non-app identity. Use one intentional `spa --agent config merge --file FILE` for a multi-setting fragment. Never paste a feature snippet. For **apps**, load [spa-apps](../../spa-apps/SKILL.md), search, and call `spa --agent apps add`. ITSI is app_id 1841, not 5403. After every write, inspect `changed` and `ready` (`ok: false` means nothing was written). Humans pass `--show-diff` for the hunk. `spa --agent config get` the identity (`found`), then Phase 13.
4. Global `terraform.aws` already comes from `--provider aws`; add **`ssh_username`** / AMI from catalog + discovery.
5. Matching global `os:` from selector `os` (not from the topology file).
6. `splunk_defaults` (include `splunk_license_file` from Phase 10 when chosen).
7. Cross-check authored paths against `spa --agent config explain PATH`.

**Exit:** File written at target path.

## Phase 13 — Validate (quality gate)

**Path B:** run `spa architecture check FILE` first. Do not validate until check is `ok`. Path A does not run check.

```bash
spa --agent validate
```

Run it from the target environment directory, or pass `--env NAME`. This always runs schema validation, inventory load, **license file ↔ license_manager pairing**, and playbook syntax-check. Fix any failure before handoff.

**Without AWS credentials:** default validate above is enough for handoff. **Do not** use `spa validate --splunk-config aws` (it will fail). Note in header; user re-validates with API before provision — see [aws-without-credentials.md](aws-without-credentials.md).

With AWS creds:

```bash
spa validate --splunk-config aws --config config/splunk_config.yml
```

Optional: verify license files exist, parse as valid XML, are not expired, and
provide the Enterprise / ITSI / ES capabilities required by the config:

```bash
spa validate --check-licenses --config config/splunk_config.yml
```

Optional: `./tests/run_schema_tests.sh -q`

Do not hand off until validation passes. See [validation.md](validation.md).

**On failure:** quote the failing check and the config path it names. Then ask (AskQuestion if available): **Fix and retry**, **Show config** (`spa --agent config get PATH`), or **Stop**. After each fix, run `spa --agent validate` again. Never hand off on a failed run.

**Exit:** Scripts exit 0.

## Phase 14 — Handoff

Validation passed. **Always** ask which way to continue with an AskQuestion call, even when AskQuestion is not the usual choice. Never end with only a message such as "Ready for deployment, use /spa": the operator must be able to pick the handoff in the question. Put A first and mark it "(Recommended)":

- **A) Hand off to `/spa` now (Recommended):** load [/spa](../../spa/SKILL.md) and run provision, then deploy, under its gates ("Handoff from spa-create-config" there). This skill runs no lifecycle command. Asking here does not approve provision or deploy; `/spa` asks for those yeses itself.
- **B) Show me the command:** print the commands below; you run them.
- **C) Wait:** stop here; you run them later.

```bash
spa provision --yes
spa deploy --yes
```

Each run waits for its own explicit yes in chat. A request earlier in the chat is not that yes. Provision, deploy, `spa hosts check`, destroy, suspend, resume, and logs belong to `/spa`. Do not run them from this skill.

**B and C:** print the commands and the log command (`spa logs --last`), then stop.

App-scope scenarios: [tests/README.md](../../../../tests/README.md).

Skill quality checklist: [skill-quality-checklist.md](skill-quality-checklist.md)
