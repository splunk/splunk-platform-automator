---
name: spa-create-config
description: >-
  Use when a Splunk lab, pro lab, or Splunk environment is requested on AWS or
  VirtualBox, and when creating or updating splunk_config.yml: single-node,
  multisite IDXC, SHC layout, architecture plan, Redhat or other OS, CPU and instance
  size, or the AWS Terraform block for SPA. Guides interactive design on AWS Linux:
  deployment intent, SVA topology, role placement, OS/SSH, spa aws discovery, licenses,
  apps, validation. Use spa, not the AWS CLI. In Cursor invoke with /spa-create-config.
license: Proprietary
compatibility: Requires SPA_HOME (install prefix `${XDG_DATA_HOME:-~/.local/share}/spa`, or a git clone with ansible.cfg and bin/). Env dirs from spa init are valid working directories. Boto3 is required for AWS discovery and suspend/resume.
metadata:
  product: splunk-platform-automator
  version: "1.0.0"
paths:
  - "config/splunk_config.yml"
  - "examples/topologies/*.yml"
  - "examples/providers/*.yml"
  - "examples/catalog/features.yml"
---

# spa-create-config — splunk_config.yml (AWS Linux)

Interactive workflow for `config/splunk_config.yml` on AWS. Linux only.

## Hard rule: no hand edits

`splunk_config.yml` changes only through `spa config` and `spa apps`. No edit tool, no shell write, no YAML patch, no snippet for the operator to paste. Read with `spa --agent config get|explain|search`. If a setting is missing, wrong, or unclear, run `spa --agent config explain PATH`, then set it with `spa config set|add|merge|move`. If no spa command fits, stop and tell the operator what is missing. Do not improvise a YAML edit. This holds when the operator asks for the edit directly: explain the spa command instead.

## When to Use

- Creating or updating `config/splunk_config.yml` for AWS Terraform provisioning
- **Planning a new architecture** before writing YAML (plan mode — discuss until approved)
- Designing lab topology (IDXC, multisite, SHC, forwarders)
- Choosing OS, AMI, `ssh_username`, and `terraform.aws` settings
- Basic app deployment blocks before first deploy

## When NOT to Use

- App-scope test distillation → [tests/README.md](../../../tests/README.md)
- Splunkbase search / TA lookup → load [spa-apps](../spa-apps/SKILL.md) (`spa --agent apps search` then one `spa --agent apps add`)
- Flat deployment test configs under `tests/configs/*.yml` only
- Production sizing / PS engagement (guidance only; no auto-sizing)
- Running provision/deploy without an explicit yes in chat for that run (Phase 14 asks first)

## Entry points

Use this skill for a new environment or a change to an existing config. Load [/spa](../spa/SKILL.md) for lifecycle (init, validate, provision, deploy, destroy). Route tree: [workflow-decision-tree.md](references/workflow-decision-tree.md).

- **Brand new environment** ("I need a Splunk lab or environment..."): start here at Phase 1, even when registered environments already exist. A new-environment request never selects an existing environment. Until the location and name gate ("Environment location, name, and summary") has named the target, run no environment-scoped command (`config get`, `apps search`, `apps add`, `validate`). Never fall back to the registry default (`spa --agent environment list`, `default: true`), which is an existing environment. The plan-or-write mode is asked at the gate, after the minimum requirements. Nothing writes until the gate passes (see the write barrier in the gate). Write mode then inits. Plan mode inits at Phase 12. Then the config writes, validate, and hand off to `/spa`.
- **Modify existing config** ("add ITSI", "change the OS"): skip the greenfield phases and use "Add / change a setting" below. Name the target environment before any write. If the operator did not name one, ask which registered environment to change (AskQuestion), and show its path.
- **Lifecycle** ("destroy", "status", "deploy", "logs"): load `/spa` directly. No design is needed.
- **Apps** ("add a TA", "install a content pack"): load `/spa-apps`.

The design phases exist so the first `--example` template is not accepted blindly: intent (1), requirements (2), topology (3), sizing (4), OS (5), AWS (6), counts and placement (7, 8), apps and licenses (9, 10), plan (11), write (12), validate (13), handoff (14).

**Provider:** `spa init` requires `--provider aws|virtualbox|external` unless the operator has saved a default with `spa environment set --provider NAME`. Ask the operator which provider to use before any init, then record it with `--aws` in the header when it is AWS. See [config-header-best-practices.md](references/config-header-best-practices.md).

## Never edit by hand (mandatory)
    
Never edit `config/splunk_config.yml` yourself: no editor, no shell write, no YAML patch, no pasted block, and no edit tool on any `splunk_config.yml` path (including `$SPA_ENV_DIR` and any environment outside this repo, such as `~/labs/NAME`). Shell writes include `sed -i`, `perl -i`, `yq -i`, `tee`, `>`/`>>` redirects, `cp`/`mv` onto the file, `python`/`node` file writes, and **any tool that writes a file directly** (including cursor tools like `Write`, editing the file in an IDE, etc.). This holds even when a change looks pending, unfinished, or missing from the config. spa has no pending-operation state that the agent may finish by hand. If a spa write fails, report the error and stop. If a hand edit already happened, stop, tell the operator which keys changed, and fix them only with `spa config` or `spa apps`. Every change goes through `spa config`:

- Read: `spa --agent config search QUERY`, `spa --agent config explain PATH`, `spa --agent config get [PATH]`
- Write: `spa --agent config set PATH VALUE`, `add`, `unset`, `merge --file FILE`, `move role`, `move host`, `topology`, `provider`, and `header set`

App entries go to [spa-apps](../spa-apps/SKILL.md) (`spa --agent apps add`). Validation, provision, deploy, and destroy stay in [/spa](../spa/SKILL.md), which waits for your yes.

## Phase Sequencing & Guardrails (mandatory)

Write mode: **1 → 2 → 3 → 4 → 5 → gate → init → 6–10 → reconfirm → 12–14**. Plan mode: **1 → 2 → 3 → 4 → 5 → gate (location/name only, no init) → 6–10 (record, no writes) → 11 → reconfirm → Phase 12 init then writes → 13–14**. Path B skips 2 and 3 (`sva.code` selects the topology at init).

- **Before the gate:** Path A: Phases 1, 2, 3, and 5 plus provider. Path B: acknowledge `spa architecture plan FILE`, then provider. Sizing (Phase 4) does not block the name. Do not skip to init without that yes.
- **No environment-scoped commands before init:** Do not run `spa init`, `spa --env NAME`, `spa config set`, `spa config add`, `spa config move`, `spa apps add`, or `spa validate` until the gate has been passed and init is confirmed. `spa architecture plan FILE` is read-only and needs no environment.
- **Architecture file (optional):** Do not parse the file. Follow [architecture-input.md](references/architecture-input.md). Path B check is required before validate.
- **Phase 9 (apps) is mandatory:** Always run Phase 9, even when the user did not mention apps. Always ask "Do you want to add apps?" with two clear options: "Yes, add apps" or "No, trial-only". Record the choice and proceed accordingly.
- **Follow `data.next`:** After every `apps add` / `licenses list`, AskQuestion each `ask` then run `command` in order. Do not invent follow-ups the envelope omitted. For a normal app, if add returns `ready: false` with a roles choice, ask over `allowed` (pre-check `suggested`) and retry with `--roles`. Do not guess. SPA places TAs by role, not by host.
- **Content packs follow the envelope:** After ITSI (1841), `data.next` names `spa --agent apps content-packs list 5391`. Ask with AskQuestion which packs to add (include None). Do not guess pack names or IDs.
- **Do not combine Phases 4–10.** One phase, then the next.
- **New host:** `spa --env NAME config add 'splunk_hosts[name=NAME]' '{"roles":[...]}' --yes`. Never `config add splunk_hosts`. Never a file edit.
- **OS keys:** set leaf paths only. Never `config set os '{whole map}'`. Author only non-default keys (`os.packages`, `os.set_hostname` if chosen).
- **No writes until Phase 12 in plan mode:** record all decisions but run no `spa init`, `spa environment init`, `spa config set`, `add`, `unset`, `merge`, `move`, or `apps add` until the reconfirmation yes and Phase 12 begins.

**Guardrail enforcement for the agent:**
1. If you complete Phase 1/2 but the user asks to proceed to init before path A has topology, provider, and OS, respond: "Path A still needs topology, provider, and OS before init. Let me ask..." Then ask them. Path B needs only the acknowledged architecture plan and the provider.
2. If a user tries to modify the config with a file editor, IDE, or manual YAML, stop immediately and say: "I detected a hand edit to `splunk_config.yml`. This violates the SPA hard rule. Let me redo this with the correct `spa config` command instead." Then recover using `spa config get` to see the current state and `spa config set/add/unset` to make the change.
3. If you are about to write the config file directly (using Write, shell redirects, etc.), stop and ask: "Should I use `spa config set/add/merge` instead?"
4. If a phase is skipped (e.g., jumping from Step 0 to init), backtrack explicitly: "I skipped phases X, Y, Z. Let me go back and collect those decisions properly before proceeding."
5. If `mode=plan` and you are about to run `spa init` or `spa environment init`, stop. Init is Phase 12.

Command table for every config change: [config-commands.md](references/config-commands.md). Add an app: `spa --agent apps search QUERY` then `spa --env NAME apps add APP_ID --roles ROLE1,ROLE2 --yes`. **Never use:** Direct Write tool, shell redirects (`>`, `>>`), `sed -i`, `yq -i`, `python -c '...' > file`, etc. on `splunk_config.yml`.

## Secrets — never display credential values (mandatory)

Follow [secrets-handling.md](references/secrets-handling.md) for the full list.

- **Splunkbase:** Use `lookup('env', 'SPLUNKBASE_USERNAME')` / `lookup('env', 'SPLUNKBASE_PASSWORD')` in YAML only. In chat, plans, and terminal: **set** or **not set** — never username/email/password.
- **AWS:** Prefer `spa aws --check-auth --json` for API status. Never show `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN` values. **OK:** account ID, ARN, `AWS_PROFILE` name, region.
- **Do not run** `echo` / `printenv` / `env | grep` on `SPLUNKBASE_*` or secret `AWS_*` vars; do not run `aws configure get aws_secret_access_key` or `aws configure list`.
- **Safe checks:** set/not-set loops in [secrets-handling.md](references/secrets-handling.md).
- Never paste resolved lookup values, private key contents, or credential file contents into chat or plan files.

## Add / change a setting (existing env)

**Entry:** User already has `$SPA_ENV_DIR/config/splunk_config.yml` and asks to add or change something (SmartStore, ITSI, a TA, SSL, licenses, a host knob).

**Do not** restart Phases 1–7. Skip greenfield SVA unless they also asked to change topology.

**Actions:**

1. `spa --agent config search QUERY` (words from the request: `itsi`, `smartstore`, `apps`, `ssl`, `volumes`).
2. `spa --agent config explain PATH` for the matching path. It returns one level, the decision, and one mutation command. It does not apply the command. A deeper level is a longer path. When `scope` is present, `applies_to` plus `per_host_path` or `global_path` is the other place that setting can go. `behavior` `merge` adds a per-host list to the global list. `replace` uses the host value instead of the global one. Omit `scope` means that path has no counterpart.
3. Update one existing schema path with `spa --agent config set PATH VALUE`. Append a new host, indexer cluster, or search-head cluster with `spa --agent config add SELECTOR JSON_OBJECT`. Use `spa --agent config merge --file FILE` only for a deliberate multi-setting fragment.
4. Do not invent YAML from leftover mixed example files or apply a catalog snippet. For Splunkbase TAs and packs, follow [spa-apps](../spa-apps/SKILL.md): search, choose the ID and roles, then use one `spa --agent apps add` transaction.
5. After every write, inspect `changed` and `ready` (`ok: false` means nothing was written). Humans pass `--show-diff` for the hunk. `spa --agent config get` the identity (`found`), then `spa --agent validate` (Phase 13). Do not auto-run provision/deploy.

## Reference files (load on demand)

| Topic | File |
|-------|------|
| Lantern / requirements | [references/architecture-requirements.md](references/architecture-requirements.md) |
| External links | [references/reference-links.md](references/reference-links.md) |
| SVA questions | [references/sva-questionnaire.md](references/sva-questionnaire.md) |
| SVA → examples | [references/sva-topology-map.md](references/sva-topology-map.md) |
| Role co-location | [references/role-placement.md](references/role-placement.md) |
| AWS defaults | [references/aws-baseline.md](references/aws-baseline.md) |
| No AWS API / creds | [references/aws-without-credentials.md](references/aws-without-credentials.md) |
| OS / SSH / Java | [references/aws-os-matrix.md](references/aws-os-matrix.md) |
| Apps | [references/apps-questionnaire.md](references/apps-questionnaire.md) |
| Licenses | [references/licenses.md](references/licenses.md) |
| RF / SF & sizing | [references/rf-sf-sizing.md](references/rf-sf-sizing.md) |
| Validate / deploy | [references/validation.md](references/validation.md) |
| Header fields (set with `spa config header set`) | [assets/config-header-template.md](assets/config-header-template.md) |
| Header best practices | [references/config-header-best-practices.md](references/config-header-best-practices.md) |
| Which skill for which request | [references/workflow-decision-tree.md](references/workflow-decision-tree.md) |
| Architecture file (path B) | [references/architecture-input.md](references/architecture-input.md) |
| Chat design summary (plan mode, not `spa architecture plan FILE`) | [assets/design-summary-template.md](assets/design-summary-template.md) |
| Secrets / env vars | [references/secrets-handling.md](references/secrets-handling.md) |

Repo keys: for every requested capability, use this loop. Call `bin/spa` JSON. Do not scrape [docs/config.md](../../../docs/config.md) and do not read `examples/catalog/features.yml`.

1. Search the operator’s concept: `spa --agent config search QUERY`.
2. Compare the one-line description. Do not choose from the title alone.
3. Inspect the selected schema path: `spa --agent config explain PATH`.
4. Author the selected value with `spa --agent config set PATH VALUE`, or append a new non-app identity with `spa --agent config add SELECTOR JSON_OBJECT`. For several already-known paths, pass one sparse fragment to `spa --agent config merge --file -`.
5. After every write, inspect `changed` and `ready`, `spa --agent config get` the identity (`found`), then `spa --agent validate`. If search has no suitable result, report that the setting is unsupported. Do not invent a key.

`docs/config.md` stays the human browse fallback. Reselect layouts with `spa --agent config topology TOPOLOGY` and `spa --agent config provider PROVIDER`; those actions replace only their owned sections.

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
5. **AWS API probe** — `spa aws --check-auth --json` (needs `boto3`; no region required). Record result:
   - **Available** → Phase 6 uses API discovery; optional `spa validate --splunk-config aws` at validate.
   - **Unavailable** → follow [aws-without-credentials.md](references/aws-without-credentials.md); do not block the workflow.
6. Read existing config if merging or revising an existing plan from prior config.
7. Licenses are not scanned here. Phase 10 scans the Software directory once, after the apps decision.
8. **Architecture input (optional).** Two entry points: [architecture-input.md](references/architecture-input.md). **Path A (no file):** keep this questionnaire and `spa init --example TOPOLOGY --provider` (write mode at the gate; plan mode at Phase 12). **Path B (confirmed 0.4.0 file):** skip the SVA questionnaire; run `spa architecture plan FILE`, then the same init timing, place/size with `spa config move`, then **`spa architecture check FILE` before validate**. Phases 9 and 10 are always asked, even when `confirmed` is true. Ignore `apps.by_role` and `delivery`.

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

See [architecture-requirements.md](references/architecture-requirements.md).

**Exit:** Intent recorded for header comment.

## Phase 2 — Architecture requirements

Gather workload, DR, data path, retention (light touch). Feed into SVA path; do not duplicate blindly.

Ask scale-out vs scale-up; default **scale out** for Splunk.

**Exit:** Short requirements summary for header.

## Phase 3 — Topology path

**Entry:** Requirements known or skipped for config-test. Path B (confirmed architecture file): skip this questionnaire; `sva.code` selects the topology at init.

| Path | Action |
|------|--------|
| User knows SVA code | Confirm code → [sva-topology-map.md](references/sva-topology-map.md) → record the topology id. Init runs at the location, name, and summary gate after Phase 5. |
| Needs help | [sva-questionnaire.md](references/sva-questionnaire.md) then `spa --agent config search` |
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

**With creds:** Run `spa aws --json` — see [aws-baseline.md](references/aws-baseline.md). Agents pass `--json` so the result is JSON.

1. **Region.** Run `spa aws --json regions list` immediately before AskQuestion. Option 1 is **only** `aws_config_region`, first, marked as the default, labelled exactly ``<region> (from AWS config, profile <aws_config_profile>)``.
   - Do not use `selected`, `region`, or `region_source`. Those can be `AWS_REGION` or scaffold `terraform.aws.region` (`eu-central-1` in `examples/providers/aws.yml`), not a choice.
   - Never mark `us-east-1` as default unless `aws_config_region` is exactly `us-east-1`. No city names. If `aws_config_region` is null, show no default. Never choose a default from your own knowledge.
   - Then up to four other names from `items`, common regions first (`us-east-1`, `us-west-2`, `eu-central-1`, `ap-southeast-1` when present), and "Other: type a region".
   - If `ok` is false, `items` is empty. Still show option 1 from `aws_config_region`, and offer "Other".
   - Use the "Recommended" label only on option 1, and only when it came from `aws_config_region`.
2. AMI — if unknown, `spa aws --region REGION --json --latest-ami --os <rhel|ubuntu|amazon_linux|debian>` or `spa aws --region REGION --json --survey` → user picks from `recommended_amis` (preference: RHEL first). REGION is the Phase 6 region, the same as `terraform.aws.region`; every AMI lookup names it.
3. `ssh_username` (`spa aws --region REGION --json --describe-ami --ami-id AMI_ID`)
4. Instance type (`spa aws --json instance-types list --family t3`; suggest `t3.medium` for config tests)
5. Key pair (`spa aws --json key-pairs list`)
6. Security groups (`spa aws --json security-groups list`)
7. Local: `ssh_private_key_file`, tags, volume size
8. `--validate` before write

**Without creds:** [aws-without-credentials.md](references/aws-without-credentials.md) — static matrix, example AMIs, user-supplied key/SG names; **warn AMIs may be stale**; header note `AWS API: not available`. Do **not** run `spa validate --splunk-config aws`.

Cap displayed API results (~10–15 AMIs, ~5 instance types).

**Exit:** All `terraform.aws` fields chosen (API-validated if creds available, else documented as unverified).

## Phase 7 — Topology counts

Determine roles and node counts (not host mapping yet):

- IDXC vs standalone indexers
- Multisite: `site`, RF/SF — [sva-topology-map.md](references/sva-topology-map.md) + [rf-sf-sizing.md](references/rf-sf-sizing.md) (Splunk doc formulas; ingest/users → performance table)
- Standalone SH vs SHC (min 3)
- MC, LM, DS, HF, UF needed?

Start from the example chosen at Phase 3 (path A) or from `spa architecture plan FILE` (path B; the overlay exists only after init). Do not run init again. Do not rebuild host counts from the JSON by hand. Set remaining `splunk_idxclusters` / `splunk_shclusters` values with `spa --agent config set` or `add`, in write mode after the gate or in plan mode at Phase 12. Path B extras and co-location use `spa config move`. Apply the RF/SF table from the topology map.

**Exit:** Tier counts documented; RF/SF match peer counts per checklist.

## Phase 8 — Role placement

[role-placement.md](references/role-placement.md) — strategy: SVA-aligned, lab-minimal, hybrid, or user-defined.

Enforce SPA hard constraints (CM+idxcluster, deployer+shcluster, LM+license file, etc.).

Summarize hosts before YAML write.

**Exit:** Host ↔ role map; strategy for header.

**Next:** Phase 9 (apps). Do not skip to 10, 11, or 12 until Phase 9 has an answer, even when the user did not mention apps.

## Phase 9 — Apps (mandatory reconfirmation)

Always ask, even when the user did not mention apps. Use AskQuestion if available, otherwise ask in chat:

- **Yes, add apps:** ask the [apps-questionnaire.md](references/apps-questionnaire.md) sections in order, one AskQuestion each, using [/spa-apps](../spa-apps/SKILL.md): (a) Premium ITSI (section 5); (b) ITSI content packs (section 6), only if ITSI is yes; (c) technical add-ons (section 7): ask which technologies, such as Windows, Linux, Cisco, or AWS, then run `spa --agent apps search TECHNOLOGY` for each and offer only the apps those searches return; (d) local org apps (section 8). Never offer an app from memory or with a generic query such as "common". Each `spa --agent apps add` uses the `app_id` from a search result.
- **No, trial-only:** reconfirm once: "Confirmed: no apps for this environment. Continue?" Leave out `splunk_app_deployment` only after that yes.

**Loop (when the answer is yes):**

1. Search and add one app with [spa-apps](../spa-apps/SKILL.md). For a normal app, ask with AskQuestion which roles it goes to before `spa --agent apps add`. ITSI and content packs have no roles question.
1b. **ITSI (1841) first.** Follow `data.next` after the add: licenses list, then `spa --agent apps content-packs list 5391`. Ask with AskQuestion which packs to add (include "None"), and add each chosen pack with `spa --agent apps add 5391 --content-pack NAME`. Then go to step 2.
2. After each add, ask with AskQuestion: **"Add another app?"** Options: Yes, add another; No, done with apps.
3. On yes, repeat from step 1 until the operator answers no. Do not skip the question after any add.
4. On no, show the current list with `spa --agent config get splunk_app_deployment` and confirm it is right. Then move on to Phase 10.

The loop ends only when the operator answers no. Apps added in this session go into the reconfirmation table with source "User input (chat)". In plan mode, record each app ID and its roles in the plan. Run `spa --agent apps add` only in Phase 12, after the environment gate.

**Exit:** App list confirmed in the loop (at least one app added, or trial-only confirmed).

## Phase 10 — Licenses

[licenses.md](references/licenses.md). Run **after Phase 9** so ITSI detection is accurate. Always ask, even when no license file is found: a trial-only decision is reconfirmed before Phase 12.

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
4. **ITSI in config** → require parsed `enterprise` + `itsi` capabilities; ensure `license_manager` role (Phase 8). Do not infer capability from filenames.
5. **Enterprise Security in config** (app ID `263` or exact ES name) → require parsed `enterprise` + `es` capabilities. `premium_app: es` is not supported by the deployment schema; do not add it.
6. **License manager role** → `splunk_license_file` is required (schema). **License file in config** → `license_manager` role is required (schema).
7. Reject configured files that are missing, invalid, expired, or do not collectively satisfy the selected premium apps. Warn for expiration within 30 days or an unknown expiration.
8. **Trial-only, after the reconfirmation in step 2** → omit both `splunk_license_file` and `license_manager`. Do not add a license file from the Software scan alone.

Use `spa --agent config explain splunk_defaults.splunk_license_server` or the licenses result's `proposed_splunk_license_file`, then author it under `splunk_defaults` in Phase 12 with `spa --agent config set`.

**Exit:** License decision confirmed (a file added, or trial-only after reconfirmation); LM + ITSI/ES warnings addressed.

## Phase 11 — Design summary (plan mode)

This is the chat write-preview before YAML. It is not `spa architecture plan FILE` (that command already ran on path B). Path B still runs this step for OS, AWS, apps, licenses, and placement.

**Entry:** `mode=plan`. Write mode skips to the reconfirmation table.

**Actions:**

1. Fill [design-summary-template.md](assets/design-summary-template.md) from phase exits (1–10). The summary must show:
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
3. For OS, SSL, licenses, RF/SF, and other settings: choose with `spa --agent config search QUERY`, then `spa --agent config explain PATH`. Use the one command on that page. That is `spa --agent config set PATH VALUE` for an existing scalar or map, or `spa --agent config add SELECTOR JSON_OBJECT` for a new non-app identity. Use one intentional `spa --agent config merge --file FILE` for a multi-setting fragment. Never paste a feature snippet. For **apps**, load [spa-apps](../spa-apps/SKILL.md), search, and call `spa --agent apps add`. ITSI is app_id 1841, not 5403. After every write, inspect `changed` and `ready` (`ok: false` means nothing was written). Humans pass `--show-diff` for the hunk. `spa --agent config get` the identity (`found`), then Phase 13.
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

**Without AWS credentials:** default validate above is enough for handoff. **Do not** use `spa validate --splunk-config aws` (it will fail). Note in header; user re-validates with API before provision — see [aws-without-credentials.md](references/aws-without-credentials.md).

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

Do not hand off until validation passes. See [validation.md](references/validation.md).

**On failure:** quote the failing check and the config path it names. Then ask (AskQuestion if available): **Fix and retry**, **Show config** (`spa --agent config get PATH`), or **Stop**. After each fix, run `spa --agent validate` again. Never hand off on a failed run.

**Exit:** Scripts exit 0.

## Phase 14 — Handoff

Validation passed. **Always** ask which way to continue with an AskQuestion call, even when AskQuestion is not the usual choice. Never end with only a message such as "Ready for deployment, use /spa": the operator must be able to pick the handoff in the question. Put A first and mark it "(Recommended)":

- **A) Hand off to `/spa` now (Recommended):** load [/spa](../spa/SKILL.md) and run provision, then deploy, under its gates ("Handoff from spa-create-config" there). This skill runs no lifecycle command. Asking here does not approve provision or deploy; `/spa` asks for those yeses itself.
- **B) Show me the command:** print the commands below; you run them.
- **C) Wait:** stop here; you run them later.

```bash
spa provision --yes
spa deploy --yes
```

Each run waits for its own explicit yes in chat. A request earlier in the chat is not that yes. Provision, deploy, `spa hosts check`, destroy, suspend, resume, and logs belong to `/spa`. Do not run them from this skill.

**B and C:** print the commands and the log command (`spa logs --last`), then stop.

App-scope scenarios: [tests/README.md](../../../tests/README.md).

Skill quality checklist: [skill-quality-checklist.md](references/skill-quality-checklist.md)
