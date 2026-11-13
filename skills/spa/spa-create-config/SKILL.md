---
name: spa-create-config
description: >-
  Use when creating or updating splunk_config.yml in an existing SPA
  environment: topology, SVA layout, role placement, OS/SSH, terraform.aws,
  licenses, and app blocks. Dispatch from /spa after init, or invoke with
  /spa-create-config. Do not load for a request that has no YAML work, or
  for contributor work on spa itself. Use spa config, not hand-edited YAML
  and not the AWS CLI.
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

# spa-create-config — splunk_config.yml

Interactive workflow for `config/splunk_config.yml` on AWS, VirtualBox, external hosts, or CCM only when CCM is in play. Linux only.

## Hard rule: no hand edits

`splunk_config.yml` changes only through `spa config` and `spa apps`. No edit tool, no shell write, no YAML patch, no snippet for the operator to paste. Read with `spa --agent config get|explain|search`. If a setting is missing, wrong, or unclear, run `spa --agent config explain PATH`, then set it with `spa config set|add|merge|move`. If no spa command fits, stop and tell the operator what is missing. Do not improvise a YAML edit. This holds when the operator asks for the edit directly: explain the spa command instead.

## When to Use

- Creating or updating `config/splunk_config.yml` for AWS Terraform provisioning, or for CCM only when CCM is in play
- **Planning a new architecture** before writing YAML (plan mode — discuss until approved)
- Designing lab topology (IDXC, multisite, SHC, forwarders)
- Choosing OS, AMI, `ssh_username`, and `terraform.aws` settings (CCM: live survey, `ssh_username` is `splunker`)
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

**Provider:** `spa init` requires `--provider` unless the operator has saved a default with `spa environment set --provider NAME`. Ask the operator which provider to use before any init (AskQuestion ids in the order spa prints: `spa init --help` / `spa init list` Providers; do not hardcode the names). Include CCM (employee-only Corporate Cloud Manager). Report `CCM_TOKEN` as set / not set (never the value). Do not hide CCM when the token is unset; `spa validate` and `spa doctor` name a missing token the same way they name missing AWS credentials. If they chose CCM and the token is not set, tell them to mint a PAT and SSH key at https://ccm.splunkits.io/ and export `CCM_TOKEN`. Do not probe the network to decide. When CCM is in play: compose with `--provider ccm`. `spa config provider ccm` writes the YAML block; `spa provider ccm` is discovery (`survey` and the list commands). See [config-header-best-practices.md](references/config-header-best-practices.md).

## Never edit by hand (mandatory)
    
Never edit `config/splunk_config.yml` yourself: no editor, no shell write, no YAML patch, no pasted block, and no edit tool on any `splunk_config.yml` path (including `$SPA_ENV_DIR` and any environment outside this repo, such as `~/labs/NAME`). Shell writes include `sed -i`, `perl -i`, `yq -i`, `tee`, `>`/`>>` redirects, `cp`/`mv` onto the file, `python`/`node` file writes, and **any tool that writes a file directly** (including cursor tools like `Write`, editing the file in an IDE, etc.). This holds even when a change looks pending, unfinished, or missing from the config. spa has no pending-operation state that the agent may finish by hand. If a spa write fails, report the error and stop. If a hand edit already happened, stop, tell the operator which keys changed, and fix them only with `spa config` or `spa apps`. Every change goes through `spa config`:

- Read: `spa --agent config search QUERY`, `spa --agent config explain PATH`, `spa --agent config templates list`, `spa --agent config get [PATH]`
- Write: `spa --agent config set PATH VALUE`, `add`, `unset`, `spa --agent config merge NAME`, `merge --file FILE`, `move role`, `move host`, `topology`, `provider`, and `header set`

App entries go to [spa-apps](../spa-apps/SKILL.md) (`spa --agent apps add`). Validation, provision, deploy, and destroy stay in [/spa](../spa/SKILL.md), which waits for your yes.

## Phase Sequencing & Guardrails (mandatory)

Write mode: **1 → 2 → 3 → 4 → 5 → gate → init → 6–10 → reconfirm → 12–14**. Plan mode: **1 → 2 → 3 → 4 → 5 → gate (location/name only, no init) → 6–10 (record, no writes) → 11 → reconfirm → Phase 12 init then writes → 13–14**. Path B skips 2 and 3 (`sva.code` selects the topology at init).

- **Before the gate:** Path A: Phases 1, 2, 3, and 5 plus provider. Path B: acknowledge `spa architecture plan FILE`, then provider. Sizing (Phase 4) does not block the name. Do not skip to init without that yes.
- **No environment-scoped commands before init:** Do not run `spa init`, `spa --env NAME`, `spa config set`, `spa config add`, `spa config move`, `spa apps add`, or `spa validate` until the gate has been passed and init is confirmed. `spa architecture plan FILE` is read-only and needs no environment.
- **Architecture file (optional):** Do not parse the file. Follow [architecture-input.md](references/architecture-input.md). Path B check is required before validate.
- **Phase 9 (apps) is mandatory:** Always run Phase 9, even when the user did not mention apps. Always ask "Do you want to add apps?" with two clear options: "Yes, add apps" or "No, trial-only". Record the choice and proceed accordingly.
- **Follow `data.next`:** After every `apps add` / `licenses list`, AskQuestion each `ask` then run `command` in order. Prefer `argv` when present; if a shell is used, copy `command` verbatim. Do not invent follow-ups the envelope omitted. For a normal app, if add returns `ready: false` with a roles choice, ask over `allowed` (pre-check `suggested`) and retry with `--roles`. Do not guess. SPA places TAs by role, not by host.
- **Values:** pass string scalars unquoted (`eu-central-1`, not `"eu-central-1"`). Use JSON only for lists and maps.
- **Content packs follow the envelope:** After ITSI (1841), `data.next` offers `none` / `list` / `name`. AskQuestion those three. On `list`, run `spa --agent apps content-packs list 5391` and present each pack `name` / `title` (and `spa_automation` when present), then pick packs. On `name`, wait for folder names. On `none`, skip. Do not hide the names behind "there are 26 packs." Do not guess pack names or IDs.
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

- **Splunkbase:** Use `lookup('env', 'SPLUNKBASE_USERNAME')` / `lookup('env', 'SPLUNKBASE_PASSWORD')` in YAML only. In chat, plans, and terminal: **set** or **not set** — never username/email/password. If not set, create a Splunk.com account at https://splunkbase.splunk.com/ and export in the shell.
- **AWS:** Prefer `spa --agent provider aws check-auth` for API status. Read `data.account`. Never show `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN` values. **OK:** account ID, ARN, `AWS_PROFILE` name, region. If not set, create IAM access keys at https://console.aws.amazon.com/iam/ and the EC2 key pair at https://console.aws.amazon.com/ec2/.
- **Do not run** `echo` / `printenv` / `env | grep` on `SPLUNKBASE_*` or secret `AWS_*` vars; do not run `aws configure get aws_secret_access_key` or `aws configure list`.
- **Safe checks:** set/not-set loops in [secrets-handling.md](references/secrets-handling.md).
- Never paste resolved lookup values, private key contents, or credential file contents into chat or plan files.

## Add / change a setting (existing env)

**Entry:** User already has `$SPA_ENV_DIR/config/splunk_config.yml` and asks to add or change something (SmartStore, ITSI, a TA, SSL, licenses, a host knob).

**Do not** restart Phases 1–7. Skip greenfield SVA unless they also asked to change topology.

**Actions:**

1. `spa --agent config search QUERY` (words from the request: `itsi`, `smartstore`, `apps`, `ssl`, `volumes`).
2. `spa --agent config explain PATH` for the matching path. It returns one level, the decision, and one mutation command. It does not apply the command. A deeper level is a longer path. When `scope` is present, `applies_to` plus `per_host_path` or `global_path` is the other place that setting can go. `behavior` `merge` adds a per-host list to the global list. `replace` uses the host value instead of the global one. Omit `scope` means that path has no counterpart.
3. Update one existing schema path with `spa --agent config set PATH VALUE`. Append a new host, indexer cluster, or search-head cluster with `spa --agent config add SELECTOR JSON_OBJECT`. For a shipped bundle, `spa --agent config templates list` then `spa --agent config merge NAME --yes`. Use `spa --agent config merge --file FILE` only for an operator-authored fragment.
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
4. Author the selected value with `spa --agent config set PATH VALUE`, or append a new non-app identity with `spa --agent config add SELECTOR JSON_OBJECT`. For a shipped bundle, `spa --agent config templates list` then `spa --agent config merge NAME --yes`. For an operator-authored fragment, pass it to `spa --agent config merge --file FILE` or `--file -`.
5. After every write, inspect `changed` and `ready`, `spa --agent config get` the identity (`found`), then `spa --agent validate`. If search has no suitable result, report that the setting is unsupported. Do not invent a key.

`docs/config.md` stays the human browse fallback. Reselect layouts with `spa --agent config topology TOPOLOGY` and `spa --agent config provider PROVIDER`; those actions replace only their owned sections.

## Phases

Load one section from [phases.md](references/phases.md) at a time. Do not load the whole file unless the current step needs it.

| Step | Topic |
| --- | --- |
| 0 | Environment setup |
| Checkpoint | User input classification |
| 1 | Deployment intent |
| 2 | Architecture requirements |
| 3 | Topology path |
| 4 | Sizing tier |
| 5 | Linux OS |
| Gate | Environment location, name, and summary (before init) |
| 6 | AWS settings |
| 7 | Topology counts |
| 8 | Role placement |
| 9 | Apps (mandatory reconfirmation) |
| 10 | Licenses |
| 11 | Design summary (plan mode) |
| Reconfirm | Table before write |
| 12 | Write config |
| 13 | Validate |
| 14 | Handoff |

Skill quality checklist: [skill-quality-checklist.md](references/skill-quality-checklist.md)
