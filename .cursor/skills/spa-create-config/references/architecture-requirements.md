# Architecture requirements (Lantern / Success Framework)

Gather **before** SVA topology selection. Answers narrow which SVA questions still matter and what to record in the config header comment.

Distilled from Lantern scalable architecture and related SF paths. See [reference-links.md](reference-links.md).

## Workload

| Question | Bands / options | Why it matters | SPA touchpoint |
|----------|-----------------|----------------|----------------|
| Daily ingest | &lt;2 GB, 2–300 GB, 300+ GB, unknown/lab | Indexer count; standalone vs distributed vs clustered | `splunk_hosts` indexer count; SVA S vs D vs C |
| Concurrent users / searches | &lt;4, 8, 16, 24, 48+ | SH count; SHC vs standalone | SHC if HA or high concurrent search load |
| Use case | ops metrics, security, audit, dev/test | Search completeness → clustering | RF/SF — see [sva-topology-map.md](sva-topology-map.md) |
| Premium apps | none, ITSI, ES, other | Extra nodes, licenses, Java on SH | `splunk_license_file`; ITSI Java 21 |

## Availability and DR

| Question | Why | Config touchpoint |
|----------|-----|-------------------|
| RTO / RPO | Multisite, replication | `idxc_site_rf`, `idxc_site_sf`; M2 vs M4 — lab defaults in [sva-topology-map.md](sva-topology-map.md) |
| Multi-site / multi-DC | Multisite IDXC, SH per site | `site:` on hosts |
| HA search tier | SHC minimum 3 nodes | `splunk_shclusters`, deployer |
| Cross-site KO sync | Stretched SHC (M4) | Complex SHC layout — escalate to SVA + PS |

## Data path

| Question | Why | Config touchpoint |
|----------|-----|-------------------|
| Data sources | UF only vs HF vs API | `uf`, `hf`, `ds` hosts |
| Forwarder scale | Few vs hundreds | Dedicated DS vs co-locate |
| Intermediate / heavy tier | Pipeline scaling | `heavy_forwarder` hosts |

## Data management (light touch)

| Question | Why | Config touchpoint |
|----------|-----|-------------------|
| Retention (days per index class) | Disk sizing | `splunk_defaults.splunk_indexes` |
| SmartStore | Object storage for indexes | See `examples/cm_4idxc2site_3shc_ds_uf_SmartStore.yml`; optional advanced path |

## Non-functional (document in header; do not over-build lab)

- Geographic / data residency (SVA Q9 → custom)
- Security zone / colocation restrictions (SVA Q10 → custom)

## Scale-out vs scale-up

After topology is chosen, ask: **more nodes (horizontal) or larger instances (vertical)?**

Default for Splunk + SPA lab work: **scale out** (more indexers/SH nodes). Use larger `instance_type` only when node count is fixed (e.g. single-node S1).

Performance table: use ingest × users band from [rf-sf-sizing.md](rf-sf-sizing.md) for indexer/SH **count hints** only.

## Requirements summary (header comment template)

Record in `config/splunk_config.yml` header:

```
# Requirements: ingest=<band>; users=<band>; use_case=<...>; DR=<none|multisite|...>
# Intent: config-test | app-lab | production-like
# SVA target: <code or lab compromise>
```
