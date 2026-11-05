# License files questionnaire

Splunk license files live on the **Ansible controller** in the shared Software directory (`spa init --software-dir`; see [Prepare Software](../../../../docs/user-guide.md#prepare-software)). Default discovery is still `../Software` relative to the **env**, not the git clone. The config references **basename only**.

## Discover available licenses

Mandatory scan (from any directory; no relative `--config`):

```bash
spa --env NAME --agent licenses list
```

After every `apps add` / `licenses list`, follow `data.next` in order (AskQuestion using each `ask`, then run `command`). Do not invent follow-ups the envelope omitted. Never `ls` Software, never guess `Splunk_Enterprise.lic`, never set `trial`. Treat "ITSI license is not assigned" as "add the ITSI file", not "remove ITSI".

When a license file is chosen, ask MC+LM placement (dedicated `mc` vs co-locate on `cm`). Do not silently attach LM to `cm`. Pair the license list and LM host in one write using the exact basenames from `proposed_splunk_license_file`.

Returns:

- `discovered_files` — sanitized metadata for all `*.lic` / `*.License`: type,
  group, normalized add-ons, creation/expiration dates, capabilities, and status
- `required_capabilities` — `enterprise`, plus `itsi` / `es` selected by config
- `selected_licenses` — newest usable files that collectively meet requirements
- `recommended_additions` — selected files not already in the config
- `unsatisfied_requirements` — capabilities no valid file provides
- `proposed_splunk_license_file` — content-based suggested list for
  `splunk_defaults`; pass the selected list to
  `spa --agent config set splunk_defaults.splunk_license_file '<JSON_LIST>'`
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

1. Run `spa --env NAME --agent licenses list` after Phase 9 (apps) so ITSI detection is accurate.
2. Show `proposed_splunk_license_file`, `unsatisfied_requirements`, and `licenses` (basename + capabilities). Follow `data.next`.
3. **If adding `splunk_license_file`**, also add `license_manager` on a host (ask dedicated `mc` vs co-locate on `cm` per [role-placement.md](role-placement.md)). One transaction, for example:
   `spa --env NAME config add 'splunk_hosts[name=mc]' '{"roles":["monitoring_console","license_manager"]}' --resolve splunk_defaults.splunk_license_file '["Splunk_Enterprise.lic","Splunk_ITSI.lic"]' --yes`
4. If ITSI or ES and no `license_manager`, prompt to add LM role (or co-locate per [role-placement.md](role-placement.md)).
5. **Trial-only labs** — omit both `splunk_license_file` and `license_manager`.
6. Include chosen licenses in Phase 12 write under `splunk_defaults`.

## Out of scope

- Downloading licenses or validating them against Splunk licensing services
- Splunkbase license acquisition
