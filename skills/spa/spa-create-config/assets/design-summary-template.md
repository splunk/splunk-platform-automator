# Design summary template

Use in **plan mode** after Phases 1–10. Present in chat; optionally write to `docs/plans/<short-name>-design-summary.md` when the user wants a file.

This is the skill's write-preview, not `spa architecture plan FILE`.

Replace `<...>` with phase outcomes. Delete unused sections.

```markdown
# Design summary — <short name>

**Status:** draft | approved  
**Target config:** `config/splunk_config.yml` (not written yet)

## Intent & requirements

- **Intent:** <config-test | app-lab | production-like>
- **Requirements:** ingest=<band>; users=<band>; use_case=<...>; DR=<...>
- **Scale strategy:** scale-out | scale-up

## Topology

- **SVA target:** <code> (lab compromises: <gaps vs SVA>)
- **Closest example:** `examples/<file>.yml`
- **Clusters:** IDXC <yes/no, multisite?>; SHC <yes/no>; sites <list>

## Tier counts & RF/SF

| Tier | Count | Notes |
|------|-------|-------|
| Indexers | | |
| Search (SH / SHC) | | |
| CM, deployer, MC, LM, DS, HF, UF | | |

- **RF/SF:** `idxc_rf`, `idxc_site_rf`, `idxc_site_sf` — rationale from [rf-sf-sizing.md](../references/rf-sf-sizing.md)

## Host ↔ role map

| Host | Roles | Site | instance override? |
|------|-------|------|--------------------|
| | | | |

- **Placement strategy:** <SVA-aligned | lab-minimal | hybrid | user-defined>

## Platform (AWS Linux)

Delete this section when CCM is in play.

- **OS:** <AL2023 | RHEL 10 | Ubuntu 24.04> — `ssh_username`, polkit/policykit-1
- **Region:** <region>
- **AMI:** <id or “from example, verify in console”>
- **Default instance / volume:** <type>, <GB>
- **Key pair / SG:** <names>
- **AWS API during plan:** available | not available
- **Tags:** include `SPADirName` when writing config

## Platform (CCM)

Use this section only when CCM is in play. Delete the AWS Linux section.

- **OS:** <live `operating_system` id from survey>
- **ssh_username:** splunker
- **Instance / disk:** <from `spa provider ccm survey`>
- **key_name / local private key file:** <names; never PEM>
- **CCM_TOKEN:** set | not set
- **TTL / operation hours:** <ttl_days>, <manual | business_hours>

## Apps & licenses

- **Apps:** <list or “none”>
- **Licenses:** <files from Software or trial-only>
- **License manager host:** <host or “none”>
- **Splunkbase creds:** <both set | username missing | password missing | both missing> — never paste values

## Open questions & risks

- <item>
- <SVA gaps, stale AMI, ITSI Java 21, etc.>

## Next step

- Revise in chat, then confirm the reconfirmation table to run Phase 12–14.
```
