# Architecture plan template

Use in **plan mode** after Phases 0a–6b. Present in chat; optionally write to `docs/plans/<short-name>-architecture-plan.md` when the user wants a file.

Replace `<...>` with phase outcomes. Delete unused sections.

```markdown
# Architecture plan — <short name>

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

- **OS:** <AL2023 | RHEL 10 | Ubuntu 24.04> — `ssh_username`, polkit/policykit-1
- **Region:** <region>
- **AMI:** <id or “from example, verify in console”>
- **Default instance / volume:** <type>, <GB>
- **Key pair / SG:** <names>
- **AWS API during plan:** available | not available
- **Tags:** include `SPADirName` when writing config

## Apps & licenses

- **Apps:** <list or “none”>
- **Licenses:** <files from ../Software or trial-only>
- **License manager host:** <host or “none”>
- **Splunkbase creds:** <both set | username missing | password missing | both missing> — never paste values

## Open questions & risks

- <item>
- <SVA gaps, stale AMI, ITSI Java 21, etc.>

## Next step

- Revise plan in chat, or say **approve and write config** to run Phase 7–9.
```
