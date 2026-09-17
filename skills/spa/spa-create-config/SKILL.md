---
name: spa-create-config
description: >-
  Use when creating or updating splunk_config.yml, designing Splunk Enterprise lab
  topology, multisite IDXC, SHC layout, architecture plan before config, or AWS
  Terraform block for SPA. Guides interactive design on AWS Linux: deployment intent,
  SVA topology, role placement, OS/SSH, spa aws discovery, licenses,
  apps, validation. In Cursor invoke with /spa-create-config.
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
  - "examples/configuration_description.yml"
---

# spa-create-config — splunk_config.yml (AWS Linux)

Interactive workflow for `config/splunk_config.yml` on AWS. Linux only.

## When to Use

- Creating or updating `config/splunk_config.yml` for AWS Terraform provisioning
- **Planning a new architecture** before writing YAML (plan mode — discuss until approved)
- Designing lab topology (IDXC, multisite, SHC, forwarders)
- Choosing OS, AMI, `ssh_username`, and `terraform.aws` settings
- Basic app deployment blocks before first deploy

## When NOT to Use

- App-scope test distillation → [spa-add-test-scenario](../spa-add-test-scenario/SKILL.md)
- Splunkbase search / TA lookup → load [spa-apps](../spa-apps/SKILL.md) (`spa --json apps search` then one `snippet`)
- Flat deployment test configs under `tests/configs/*.yml` only
- Production sizing / PS engagement (guidance only; no auto-sizing)
- Auto-running provision/deploy (user runs `spa provision` / `spa deploy` after validation)

## Secrets — never display credential values (mandatory)

Follow [secrets-handling.md](references/secrets-handling.md) for the full list.

- **Splunkbase:** Use `lookup('env', 'SPLUNKBASE_USERNAME')` / `lookup('env', 'SPLUNKBASE_PASSWORD')` in YAML only. In chat, plans, and terminal: **set** or **not set** — never username/email/password.
- **AWS:** Prefer `spa aws --check-auth --json` for API status. Never show `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN` values. **OK:** account ID, ARN, `AWS_PROFILE` name, region.
- **Do not run** `echo` / `printenv` / `env | grep` on `SPLUNKBASE_*` or secret `AWS_*` vars; do not run `aws configure get aws_secret_access_key` or `aws configure list`.
- **Safe checks:** set/not-set loops in [secrets-handling.md](references/secrets-handling.md).
- Never paste resolved lookup values, private key contents, or credential file contents into chat or plan files.

## Add / change a setting (existing env)

**Entry:** User already has `$SPA_ENV_DIR/config/splunk_config.yml` and asks to add or change something (SmartStore, ITSI, a TA, SSL, licenses, a host knob).

**Do not** restart Phases 0a–5. Skip greenfield SVA unless they also asked to change topology.

**Actions:**

1. `spa --json features search QUERY` (words from the request: `itsi`, `smartstore`, `apps`, `ssl`, `volumes`).
2. `spa --json features show ID` for the matching record; `show ID --keys` only when types, allowed values, or notes are needed.
3. Merge the record `snippet` into the existing config using the catalog `merge` field (`deep` vs `replace`). Honor `when_not_to_use`.
4. Do not invent YAML from leftover mixed example files. ITSI full lab: copy or merge `examples/single_node_itsi.yml` when they want the whole env, not only the snippet. For Splunkbase TAs and packs, follow [spa-apps](../spa-apps/SKILL.md): `spa --json apps search QUERY` then one `snippet`; merge the snippet (do not guess `app_id`).
5. `spa validate` (Phase 8). Do not auto-run provision/deploy.

Out of scope: writing `splunk_config.yml` via `spa config` (#76); single-app deploy (#68).

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
| Header template | [assets/config-header-template.md](assets/config-header-template.md) |
| Architecture plan | [assets/architecture-plan-template.md](assets/architecture-plan-template.md) |
| Secrets / env vars | [references/secrets-handling.md](references/secrets-handling.md) |

Repo keys: choose from concise `spa --json features list` / `search`, inspect with `show ID`, and request schema types/constraints plus catalog notes only when needed with `show ID --keys`. Types live in Pydantic (`spa validate`); [examples/catalog/features.yml](../../../examples/catalog/features.yml) is when-to-use and snippets. Pointer dump: [examples/configuration_description.yml](../../../examples/configuration_description.yml).

## Step 0 — Environment setup

**Entry:** User wants a deployment config or architecture plan.

**Actions:**

1. Confirm **project root** (contains `ansible.cfg`, `bin/`).
2. **Mode** — AskQuestion if available, otherwise ask in chat, unless user already stated intent:
   - **plan** — Phases 0a–6b + architecture plan; **no** `splunk_config.yml` write until user approves.
   - **write** — Full flow through Phase 7–9 (or continue after approved plan).
   Infer **plan** from phrases like “design”, “discuss”, “plan architecture”; infer **write** from “create config”, “write yaml”, “approve and write”.
3. Target path: default `config/splunk_config.yml` (for write mode or post-approval).
4. If file exists and **mode=write** (or approving plan): **merge vs overwrite** — AskQuestion if available, otherwise ask in chat, before destructive write. Skip in **plan** mode until Phase 7.
5. **AWS API probe** — `spa aws --check-auth --json` (needs `boto3`; no region required). Record result:
   - **Available** → Phase 4 uses API discovery; optional `--splunk-config-aws` at validate.
   - **Unavailable** → follow [aws-without-credentials.md](references/aws-without-credentials.md); do not block the workflow.
6. Read existing config if merging or revising an existing plan from prior config.
7. Optional inventory: `spa licenses --json` — note what exists in the shared Software directory ([Prepare Software](../../../docs/user-guide.md#prepare-software)).

**Exit:** **Mode recorded**; target path known; merge policy clear when applicable; **AWS API status recorded**; Software licenses noted if scanned.

## Phase 0a — Deployment intent

Ask: *What are you proving with this environment?*

| Intent | Behavior |
|--------|----------|
| Config / infra test | Minimal hosts; lab co-location OK; flag SVA gaps |
| Feature / app lab | Right tier sizes; Java 21 for ITSI; licenses |
| Production-like | SVA separation; multisite; document RTO/RPO |

See [architecture-requirements.md](references/architecture-requirements.md).

**Exit:** Intent recorded for header comment.

## Phase 0b — Architecture requirements

Gather workload, DR, data path, retention (light touch). Feed into SVA path; do not duplicate blindly.

Ask scale-out vs scale-up; default **scale out** for Splunk.

**Exit:** Short requirements summary for header.

## Phase 1 — Topology path

**Entry:** Requirements known or skipped for config-test.

| Path | Action |
|------|--------|
| User knows SVA code | Confirm code → [sva-topology-map.md](references/sva-topology-map.md) then `spa init --example TOPOLOGY --provider aws\|virtualbox ENV` |
| Needs help | [sva-questionnaire.md](references/sva-questionnaire.md) then catalog `spa --json features search` |
| Config test only | Minimal topology (`single_node` or `cm_2idxc_sh_uf`) |

**Exit:** SVA code or lab compromise; topology id from `spa init --list` (not a mixed `_aws` file).

## Phase 2 — Sizing tier

| Purpose | Default |
|---------|---------|
| Config test | `t3.medium`, 50 GB global `terraform.aws` |
| App lab | Larger SH if needed; ITSI Java 21 |
| Production-like | Document overrides |

**Exit:** Default instance type and volume size for global block.

## Phase 3 — Linux OS

Pick OS via `spa --json features search os` (`setting.os`, `setting.os.ubuntu`, `setting.ssh_username`). Write the snippet into `splunk_config.yml` yourself; do not pass OS through `spa init`.

**Recommended:** Amazon Linux 2023, RHEL 10, or Ubuntu 24.04 LTS (latest AMI in region).

Set global `os:` block, expected `ssh_username`, and **polkit** (`polkit` on AL/RHEL; `policykit-1` on Ubuntu — required for forwarders and all hosts unless `splunk_use_policykit: false`).

**Exit:** OS family chosen; `os:` template ready.

## Phase 4 — AWS settings

**With creds:** Run `spa aws` — see [aws-baseline.md](references/aws-baseline.md).

1. Region (`--list-regions` or confirm)
2. AMI — if unknown, `--latest-ami --os <rhel|ubuntu|amazon_linux|debian>` or `--survey` → user picks from `recommended_amis` (preference: RHEL first)
3. `ssh_username` (`--describe-ami`)
4. Instance type (`--list-instance-types --family t3`; suggest `t3.medium` for config tests)
5. Key pair (`--list-key-pairs`)
6. Security groups (`--list-security-groups`)
7. Local: `ssh_private_key_file`, tags, volume size
8. `--validate` before write

**Without creds:** [aws-without-credentials.md](references/aws-without-credentials.md) — static matrix, example AMIs, user-supplied key/SG names; **warn AMIs may be stale**; header note `AWS API: not available`. Do **not** run `--splunk-config-aws`.

Cap displayed API results (~10–15 AMIs, ~5 instance types).

**Exit:** All `terraform.aws` fields chosen (API-validated if creds available, else documented as unverified).

## Phase 5 — Topology counts

Determine roles and node counts (not host mapping yet):

- IDXC vs standalone indexers
- Multisite: `site`, RF/SF — [sva-topology-map.md](references/sva-topology-map.md) + [rf-sf-sizing.md](references/rf-sf-sizing.md) (Splunk doc formulas; ingest/users → performance table)
- Standalone SH vs SHC (min 3)
- MC, LM, DS, HF, UF needed?

Copy `splunk_idxclusters` / `splunk_shclusters` from closest example; apply RF/SF table from topology map when not copying verbatim.

**Exit:** Tier counts documented; RF/SF match peer counts per checklist.

## Phase 5b — Role placement

[role-placement.md](references/role-placement.md) — strategy: SVA-aligned, lab-minimal, hybrid, or user-defined.

Enforce SPA hard constraints (CM+idxcluster, deployer+shcluster, LM+license file, etc.).

Summarize hosts before YAML write.

**Exit:** Host ↔ role map; strategy for header.

## Phase 6 — Apps (optional)

[apps-questionnaire.md](references/apps-questionnaire.md). Skip entire `splunk_app_deployment` if no.

**Exit:** App block ready or explicitly skipped.

## Phase 6b — Licenses

[licenses.md](references/licenses.md). Run **after Phase 6** so ITSI detection is accurate.

```bash
spa licenses --config config/splunk_config.yml --json
```

1. Scan the Software directory for `*.lic` / `*.License` and inspect sanitized parsed
   metadata: `license_type`, `group_id`, `addons`, `capabilities`, `expires_at`,
   and `status`. Never expose raw license XML, signatures, or GUIDs.
2. If `proposed_splunk_license_file` is non-empty, ask (AskQuestion if available): add to `splunk_defaults`? (especially for lab / app lab intent).
3. **If user accepts license file** → add `license_manager` role on a host in Phase 5b (typical lab: co-locate on `cm` or dedicated `mc`).
4. **ITSI in config** → require parsed `enterprise` + `itsi` capabilities; ensure `license_manager` role (Phase 5b). Do not infer capability from filenames.
5. **Enterprise Security in config** (app ID `263` or exact ES name) → require parsed `enterprise` + `es` capabilities. `premium_app: es` is not supported by the deployment schema; do not add it.
6. **License manager role** → `splunk_license_file` is required (schema). **License file in config** → `license_manager` role is required (schema).
7. Reject configured files that are missing, invalid, expired, or do not collectively satisfy the selected premium apps. Warn for expiration within 30 days or an unknown expiration.
8. **Trial-only labs** → omit both `splunk_license_file` and `license_manager`; do not add license file from Software scan alone.
9. No usable files in Software → warn (trial only or add licenses before deploy).

Use `spa --json features show setting.license` (or the licenses JSON `yaml_snippet`) under `splunk_defaults` in Phase 7.

**Exit:** License list decided or explicitly skipped; LM + ITSI/ES warnings addressed.

## Phase 6c — Architecture plan (plan mode)

**Entry:** `mode=plan` OR user has not yet approved writing config.

**Actions:**

1. Fill [architecture-plan-template.md](assets/architecture-plan-template.md) from phase exits (0a–6b).
2. Present the plan in chat. Offer optional file: `docs/plans/<short-name>-architecture-plan.md`.
3. End with: *Revise anything, or say **approve and write config** to continue to Phase 7.*

**Revision loop:** User changes (“add multisite”, “drop HF”) → update affected phases mentally, refresh plan; do **not** write YAML.

**Exit:** Plan delivered; status **draft** until user approves.

**Do not run Phase 7–9** until user explicitly approves (treat approval as `mode=write` for remainder of session).

## Phase 7 — Write config

**Entry:** `mode=write` OR user said **approve and write config** (or equivalent).

**Do not enter** while plan mode is active and plan is still draft.

1. Scaffold with `spa init --example TOPOLOGY --provider aws|virtualbox ENV` (topology + provider only). Do not invent `--addon` or OS flags on init.
2. Header from [assets/config-header-template.md](assets/config-header-template.md)
3. For OS, SSL, licenses, RF/SF, and other settings: choose with `spa --json features search QUERY`, inspect with `show ID`, and use `show ID --keys` only when per-key types, constraints, placeholders, or notes are needed. Merge each record's `snippet` into `$SPA_ENV_DIR/config/splunk_config.yml` yourself. Do not pass those through init. For **apps**, load [spa-apps](../spa-apps/SKILL.md): `spa --json apps search QUERY` then `spa --json apps snippet APP_ID`; merge that snippet. ITSI is app_id 1841, not 5403.
4. Global `terraform.aws` already comes from `--provider aws`; add **`ssh_username`** / AMI from catalog + discovery.
5. Matching global `os:` from `setting.os` (not from the topology file).
6. `splunk_defaults` (include `splunk_license_file` from Phase 6b when chosen).
7. Cross-check snippets against `spa --json features show`; [configuration_description.yml](../../../examples/configuration_description.yml) is a pointer only.

**Exit:** File written at target path.

## Phase 8 — Validate (quality gate)

```bash
spa validate config/splunk_config.yml
```

This always runs schema validation, inventory load, **license file ↔ license_manager pairing**, and playbook syntax-check. Fix any failure before handoff.

**Without AWS credentials:** default validate above is enough for handoff. **Do not** use `--splunk-config-aws` (it will fail). Note in header; user re-validates with API before provision — see [aws-without-credentials.md](references/aws-without-credentials.md).

With AWS creds:

```bash
spa validate --splunk-config-aws config/splunk_config.yml
```

Optional: verify license files exist, parse as valid XML, are not expired, and
provide the Enterprise / ITSI / ES capabilities required by the config:

```bash
spa validate --check-licenses config/splunk_config.yml
```

Optional: `./tests/run_schema_tests.sh -q`

Do not hand off until validation passes. See [validation.md](references/validation.md).

**Exit:** Scripts exit 0.

## Phase 9 — Handoff

User runs (skill does **not** auto-provision):

```bash
spa provision --yes && spa deploy --yes
```

Destroy: `spa destroy --yes`

Pause AWS compute while retaining Terraform state and EBS volumes:
`spa suspend --yes`. Resume and refresh changed inventory addresses:
`spa resume --yes`. Retained resources continue to incur charges.

Optional: distill app-scope tests via [spa-add-test-scenario](../spa-add-test-scenario/SKILL.md).

## Terminology

Use consistently: `cluster_manager`, `terraform.aws`, `splunk_hosts`, `plugin: splunk-platform-automator` (not "master").

## Skill quality checklist

- [ ] `name` matches folder `spa-create-config`
- [ ] Description third person with trigger terms
- [ ] SKILL.md under 500 lines; details in `references/`
- [ ] When to Use / When NOT to Use present
- [ ] Step 0 mode (`plan` vs `write`) recorded; plan mode skips YAML until approval
- [ ] Step 0 and phase exit criteria followed
- [ ] `bin/*` invoked from project root
- [ ] Secrets: Splunkbase and AWS credential env values never shown in chat or terminal output
- [ ] Incremental add uses `spa --json features search` / `show` / merge, or [spa-apps](../spa-apps/SKILL.md) for Splunkbase, then `spa validate` (does not restart SVA for a single setting)
