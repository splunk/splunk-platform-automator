# SVA topology questionnaire

Use when the user does not already know their target topology. Map answers to codes in [sva-topology-map.md](sva-topology-map.md).

Cross-check [architecture-requirements.md](architecture-requirements.md) first — many answers may already be known.

## Core questions (SVA-aligned)

1. **Daily ingest band** — &lt;2 GB, 2–300 GB, 300+ GB, unknown/lab
2. **Search completeness** — Must all data be searchable from any SH? (yes → clustering)
3. **Use case** — Operations, security/threat, audit, dev/test
4. **Availability** — Single site OK, or multi-site / DR required?
5. **RTO/RPO** — Targets or "not testing DR"
6. **Concurrent searches / users** — Rough band (&lt;4 … 48+)
7. **HA search** — Standalone SH OK vs SHC required (min 3 for SHC)
8. **Premium apps** — None, ITSI, ES, other (+10 topology for ES)
9. **Data residency / zones** — Any constraints? (often custom)

## Decision shortcuts

| If user says… | Likely code |
|---------------|-------------|
| Single box, minimal | S1 |
| Few indexers, no cluster | D1 |
| IDXC single site, standalone SH | C1 |
| IDXC single site, SHC | C3 |
| IDXC two+ sites, standalone SH | M2 |
| IDXC two+ sites, SHC per site | M3 |
| SHC across sites | M4 — escalate |

## Config-test only path

If intent is **playbook/inventory validation only**:

- Minimal hosts (e.g. CM + 2 indexers + SH)
- Lab role co-location OK
- Record `Intent: config-test` in header
- Do not promise DR or production capacity

## Exit criteria

- SVA code (or explicit lab compromise) chosen
- RF/SF and min indexer counts checked ([sva-topology-map.md](sva-topology-map.md) checklist)
- Closest `examples/*.yml` identified for copy baseline
- Known SVA gaps listed for header comment
