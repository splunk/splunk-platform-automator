# License files questionnaire

Splunk license files live on the **Ansible controller** in `splunk_software_dir` (default `../Software` relative to the repo). The config references **basename only** — files are not copied by path from arbitrary locations.

See [README.md](README.md) Framework Installation — link or copy `Splunk_Enterprise.lic` into `Software`.

## Discover available licenses

From repo root:

```bash
python3 bin/splunk_config_licenses.py --json
python3 bin/splunk_config_licenses.py --config config/splunk_config.yml --json
```

Returns:

- `discovered_files` — all `*.lic` / `*.License` in Software
- `proposed_splunk_license_file` — suggested list for `splunk_defaults`
- `yaml_snippet` — paste into `splunk_defaults`
- `itsi_in_config` — derived from `splunk_app_deployment` when `--config` is set
- `warnings` — e.g. ITSI without `license_manager` or missing ITSI license file

## When to ask the user

| Situation | Action |
|-----------|--------|
| Lab / app lab / production-like | Ask whether to add licenses when files exist in Software |
| `license_manager` role on any host | **Required** — `splunk_license_file` must be set (schema) |
| ITSI in `splunk_app_deployment` | Propose `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` if present; require `license_manager` role |
| Config / infra test, no LM | Enterprise license optional (trial may suffice); still recommend if file exists |
| No files in Software | Warn; user may use trial or add licenses before deploy |

## Canonical filenames (SPA examples)

| File | When to include |
|------|-----------------|
| `Splunk_Enterprise.lic` | Almost all lab/production configs when file exists |
| `Splunk_ITSI.lic` | When ITSI app (`premium_app: itsi` or app_id `1841`) is in config |

Other `*.lic` names in Software are listed in `discovered_files`; only add to config if the user explicitly needs them.

## YAML examples

Single enterprise license:

```yaml
splunk_defaults:
  splunk_license_file: Splunk_Enterprise.lic
```

ITSI (requires `license_manager` role on a host):

```yaml
splunk_defaults:
  splunk_license_file:
    - Splunk_Enterprise.lic
    - Splunk_ITSI.lic
```

## Skill workflow

1. Run `splunk_config_licenses.py` after Phase 6 (apps) so ITSI detection is accurate.
2. If `proposed_splunk_license_file` is non-empty, AskQuestion: add to config for lab?
3. If ITSI and no `license_manager`, prompt to add LM role (or co-locate per [role-placement.md](role-placement.md)).
4. Include chosen licenses in Phase 7 write under `splunk_defaults`.

## Out of scope

- Downloading or validating license entitlements
- Splunkbase license acquisition
