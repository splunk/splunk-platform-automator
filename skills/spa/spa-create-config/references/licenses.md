# License files questionnaire

Splunk license files live on the **Ansible controller** in `splunk_software_dir` (default `../Software` relative to the repo). The config references **basename only** — files are not copied by path from arbitrary locations.

See [README.md](README.md) Framework Installation — link or copy `Splunk_Enterprise.lic` into `Software`.

## Discover available licenses

From repo root:

```bash
spa licenses --json
spa licenses --config config/splunk_config.yml --json
```

Returns:

- `discovered_files` — sanitized metadata for all `*.lic` / `*.License`: type,
  group, normalized add-ons, creation/expiration dates, capabilities, and status
- `required_capabilities` — `enterprise`, plus `itsi` / `es` selected by config
- `selected_licenses` — newest usable files that collectively meet requirements
- `recommended_additions` — selected files not already in the config
- `unsatisfied_requirements` — capabilities no valid file provides
- `proposed_splunk_license_file` — content-based suggested list for `splunk_defaults`
- `yaml_snippet` — paste into `splunk_defaults`
- `itsi_in_config` / `es_in_config` — derived from installed app entries
- `license_validation` — errors for missing, invalid, expired, or wrong-entitlement
  configured files; warnings for expiry within 30 days or unknown expiration

The scanner does not trust filenames. It parses the license XML but never emits
the raw payload, signature, or GUID. A canonical filename is only a final
tie-breaker between otherwise equivalent licenses.

## When to ask the user

| Situation | Action |
|-----------|--------|
| Lab / app lab / production-like | Ask whether to add licenses when files exist in Software |
| `license_manager` role on any host | **Required** — `splunk_license_file` must be set (schema) |
| `splunk_license_file` in `splunk_defaults` | **Required** — `license_manager` role on a host (schema); co-locate on `cm` or `mc` for labs |
| ITSI in `splunk_app_deployment` | Require Enterprise + ITSI capabilities; require `license_manager` role |
| ES app ID `263` / exact Enterprise Security name | Require Enterprise + ES capabilities; warn if no `license_manager` role |
| Config / infra test, trial only | Omit both `splunk_license_file` and `license_manager` (Splunk trial applies) |
| Missing, invalid, or expired file | Do not propose it; fail `spa validate --check-licenses` if configured |

## License selection

Select by parsed capability, not by filename:

1. Exclude invalid and expired files.
2. Prefer a file that satisfies more required capabilities.
3. Prefer perpetual, then valid, then expiring, then unknown-expiration.
4. Among equivalent dated licenses, prefer the latest expiration.
5. Keep multiple files when they provide complementary capabilities.

Do not assume that the newest date makes multiple stackable licenses
interchangeable. The proposal chooses one best candidate per required
capability; review additional commercial stack entitlements with the user.

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

1. Run `spa licenses` after Phase 6 (apps) so ITSI detection is accurate.
2. If `proposed_splunk_license_file` is non-empty, ask the user (AskQuestion if available): add to config for lab?
3. **If adding `splunk_license_file`**, also add `license_manager` to a host in Phase 5b (co-locate on `cm` or `mc` per [role-placement.md](role-placement.md)). Do not write license file without LM role.
4. If ITSI or ES and no `license_manager`, prompt to add LM role (or co-locate per [role-placement.md](role-placement.md)).
5. **Trial-only labs** — omit both `splunk_license_file` and `license_manager`.
6. Include chosen licenses in Phase 7 write under `splunk_defaults`.

## Out of scope

- Downloading licenses or validating them against Splunk licensing services
- Splunkbase license acquisition
