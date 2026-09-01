---
name: spa-create-config
description: >-
  Guides interactive design and creation of config/splunk_config.yml for Splunk
  Platform Automator on AWS Linux. Covers deployment intent, Lantern/SF
  requirements, SVA topology, role placement, scale-out guidance, OS/SSH,
  splunk_config_aws.py discovery, license files in ../Software, basic apps, and
  pre-deploy validation. Invoke in Cursor with /spa-create-config. Use
  when creating or updating splunk_config.yml, designing Splunk Enterprise lab
  topology, multisite IDXC, SHC layout, architecture plan before config, or
  AWS Terraform block for SPA.
paths:
  - "config/splunk_config.yml"
  - "examples/**/*.yml"
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

- App-scope test distillation → [spa-add-test-scenario](.cursor/skills/spa-add-test-scenario/SKILL.md)
- Flat deployment test configs under `tests/configs/*.yml` only
- Splunkbase catalog search (user supplies `app_id` manually)
- Production sizing / PS engagement (guidance only; no auto-sizing)
- Auto-running provision/deploy (user runs playbooks after validation)

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

Repo keys: [examples/configuration_description.yml](examples/configuration_description.yml), [examples/aws_lab_baseline.yml](examples/aws_lab_baseline.yml).

## Step 0 — Environment setup

**Entry:** User wants a deployment config or architecture plan.

**Actions:**

1. Confirm **project root** (contains `ansible.cfg`, `bin/`).
2. **Mode** — AskQuestion unless user already stated intent:
   - **plan** — Phases 0a–6b + architecture plan; **no** `splunk_config.yml` write until user approves.
   - **write** — Full flow through Phase 7–9 (or continue after approved plan).
   Infer **plan** from phrases like “design”, “discuss”, “plan architecture”; infer **write** from “create config”, “write yaml”, “approve and write”.
3. Target path: default `config/splunk_config.yml` (for write mode or post-approval).
4. If file exists and **mode=write** (or approving plan): **merge vs overwrite** — AskQuestion before destructive write. Skip in **plan** mode until Phase 7.
5. **AWS API probe** — `python3 bin/splunk_config_aws.py --check-auth --json` (needs `boto3`; no region required). Record result:
   - **Available** → Phase 4 uses API discovery; optional `--splunk-config-aws` at validate.
   - **Unavailable** → follow [aws-without-credentials.md](references/aws-without-credentials.md); do not block the workflow.
6. Read existing config if merging or revising an existing plan from prior config.
7. Optional inventory: `python3 bin/splunk_config_licenses.py --json` — note what exists in `../Software`.

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
| User knows SVA code | Confirm code → [sva-topology-map.md](references/sva-topology-map.md) |
| Needs help | [sva-questionnaire.md](references/sva-questionnaire.md) |
| Config test only | Minimal topology (e.g. CM + 2 idx + SH) |

**Exit:** SVA code or lab compromise; closest `examples/*.yml` chosen.

## Phase 2 — Sizing tier

| Purpose | Default |
|---------|---------|
| Config test | `t3.medium`, 50 GB global `terraform.aws` |
| App lab | Larger SH if needed; ITSI Java 21 |
| Production-like | Document overrides |

**Exit:** Default instance type and volume size for global block.

## Phase 3 — Linux OS

Pick OS → [aws-os-matrix.md](references/aws-os-matrix.md).

**Recommended:** Amazon Linux 2023, RHEL 10, or Ubuntu 24.04 LTS (latest AMI in region).

Set global `os:` block, expected `ssh_username`, and **polkit** (`polkit` on AL/RHEL; `policykit-1` on Ubuntu — required for forwarders and all hosts unless `splunk_use_policykit: false`).

**Exit:** OS family chosen; `os:` template ready.

## Phase 4 — AWS settings

**With creds:** Run `bin/splunk_config_aws.py` — see [aws-baseline.md](references/aws-baseline.md).

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
python3 bin/splunk_config_licenses.py --config config/splunk_config.yml --json
```

1. Scan `../Software` for `*.lic` / `*.License` (SPA `splunk_software_dir`).
2. If `proposed_splunk_license_file` is non-empty, AskQuestion: add to `splunk_defaults`? (especially for lab / app lab intent).
3. **If user accepts license file** → add `license_manager` role on a host in Phase 5b (typical lab: co-locate on `cm` or dedicated `mc`).
4. **ITSI in config** → propose `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` when files exist; ensure `license_manager` role (Phase 5b).
5. **License manager role** → `splunk_license_file` is required (schema). **License file in config** → `license_manager` role is required (schema).
6. **Trial-only labs** → omit both `splunk_license_file` and `license_manager`; do not add license file from Software scan alone.
7. No files in Software → warn (trial only or add licenses before deploy).

Use `yaml_snippet` from JSON under `splunk_defaults` in Phase 7.

**Exit:** License list decided or explicitly skipped; LM + ITSI warnings addressed.

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

1. `plugin: splunk-platform-automator`
2. Header from [assets/config-header-template.md](assets/config-header-template.md)
3. Global `terraform.aws` with **`ssh_username`** and AMI comment
4. Matching global `os:` block
5. `splunk_defaults` (include `splunk_license_file` from Phase 6b when chosen), clusters, `splunk_hosts` from closest example
6. Cross-check [configuration_description.yml](examples/configuration_description.yml)

**Exit:** File written at target path.

## Phase 8 — Validate (quality gate)

```bash
./bin/validate_splunk_config.sh config/splunk_config.yml
```

This always runs schema validation, inventory load, **license file ↔ license_manager pairing**, and playbook syntax-check. Fix any failure before handoff.

**Without AWS credentials:** default validate above is enough for handoff. **Do not** use `--splunk-config-aws` (it will fail). Note in header; user re-validates with API before provision — see [aws-without-credentials.md](references/aws-without-credentials.md).

With AWS creds:

```bash
./bin/validate_splunk_config.sh --splunk-config-aws config/splunk_config.yml
```

Optional: verify license files exist in `../Software`:

```bash
./bin/validate_splunk_config.sh --check-licenses config/splunk_config.yml
```

Optional: `./tests/run_schema_tests.sh -q`

Do not hand off until validation passes. See [validation.md](references/validation.md).

**Exit:** Scripts exit 0.

## Phase 9 — Handoff

User runs (skill does **not** auto-provision):

```bash
ap ansible/provision_terraform_aws.yml -e auto_approve=true
ap ansible/deploy_site.yml
```

Destroy: `ap ansible/destroy_terraform_aws.yml -e auto_approve=true`

Optional: distill app-scope tests via [spa-add-test-scenario](.cursor/skills/spa-add-test-scenario/SKILL.md).

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
- [ ] Validation passed before handoff
