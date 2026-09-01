# SVA topology map

SVA codes describe **topology**, not sizing. Lab configs may diverge from full SVA DR (flag gaps in header).

| SVA code | SPA example | Pattern |
|----------|-------------|---------|
| S1 | `examples/single_node.yml` | Single host: indexer + search_head (+ optional LM) |
| D1 | `examples/idx_sh_uf.yml` | Standalone indexers + SH |
| C1 / C11 | `examples/cm_2idxc_sh_uf.yml` | CM + indexers + standalone SH |
| C3 / C13 | `examples/cm_2idxc1site_3shc_uf.yml` | CM + indexers + SHC + deployer |
| M2 / M12 | `examples/4idxc2site_sh.yml` | Multisite IDXC + SH (standalone) |
| M3 / M13 | `examples/cm_4idxc2site_3shc_ds_uf.yml` | Multisite IDXC + SHC per site |
| M4 / M14 | SVA documentation | Stretched SHC — escalate to SVA + PS |

## Multisite IDXC defaults (lab)

Typical from `examples/4idxc2site_sh.yml`:

```yaml
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: splunkidxc
    idxc_replication_port: 9887
    idxc_site_rf: 'origin:2, total:3'
    idxc_site_sf: 'origin:1, total:2'
```

CM at `site0`; indexers per site; search tier per role-placement choice.

## Replication and search factors (RF / SF)

SVA topology codes (M2, M3, …) imply **multisite IDXC** and site-aware factors. For **how to calculate** RF/SF, peer counts, and storage hints, see [rf-sf-sizing.md](rf-sf-sizing.md). Lab defaults below — copy from examples unless user states explicit failure/DR targets.

### Single-site IDXC (`idxc_rf` / `idxc_sf`)

Use integer factors on `splunk_idxclusters` (not `idxc_site_*`).

| SVA code | Lab RF | Lab SF | Min indexer peers | Copy from |
|----------|--------|--------|-------------------|-----------|
| C1 / C11 | `2` | `2` | **2** (`idxc_rf` ≤ peer count) | `examples/cm_2idxc_sh_uf.yml` |
| C3 / C13 | `2` | `2` | **2** (add SHC separately) | `examples/cm_2idxc1site_3shc_uf.yml` |

```yaml
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: splunkidxc
    idxc_replication_port: 9887
    idxc_rf: 2
    idxc_sf: 2
```

### Multisite IDXC (`idxc_site_rf` / `idxc_site_sf`)

Use string factors: `'origin:N, total:M'` (comma-separated pairs).

| Component | Meaning (lab shorthand) |
|-----------|-------------------------|
| **origin** | Copies tied to the site where data originated |
| **total** | Total copies across the whole cluster |

| SVA code | Lab site RF | Lab site SF | Min indexers per data site | Min sites with indexers | Copy from |
|----------|-------------|-------------|----------------------------|-------------------------|-----------|
| M2 / M12 | `origin:2, total:3` | `origin:1, total:2` | **2** per site (supports `origin:2`) | **2** (typical lab) | `examples/4idxc2site_sh.yml` |
| M3 / M13 | `origin:2, total:3` | `origin:1, total:2` | **2** per site | **2** (+ SHC per site in full SVA) | `examples/cm_4idxc2site_3shc_ds_uf.yml` |
| M4 / M14 | Escalate | Escalate | Stretched SHC — not a lab copy-paste | SVA + PS | — |

```yaml
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: splunkidxc
    idxc_replication_port: 9887
    idxc_site_rf: 'origin:2, total:3'
    idxc_site_sf: 'origin:1, total:2'
```

**SPA multisite layout:** cluster manager on `site0` (no indexer data); indexers on `site1`, `site2`, …

### RF / SF checklist (before Phase 7 write)

Use during **Phase 5** after SVA code and indexer counts are chosen:

1. **Pick factors from the table** (or copy verbatim from the example row) — do not invent strings unless you understand multisite factor rules.
2. **Single-site:** indexer host count ≥ `idxc_rf` (Splunk cluster peer count must support replication factor).
3. **Multisite:** count indexer peers **per site** (roles `indexer` + `idxcluster`, excluding CM-only `site0`):
   - Each data site should have enough peers for the **origin** RF you set (lab default `origin:2` → **2 indexers on that site**).
   - Cluster-wide peer count must support the **total** component (lab `total:3` with 2 sites × 2 indexers = 4 peers is a common SPA lab pattern).
4. **Search factor:** `idxc_site_sf` / `idxc_sf` must be achievable with the same peer layout (lab defaults above match the example host counts).
5. **Multisite lab with 2 peers/site:** add `idxc_rf: 2` when `total` is 2–3 (avoids manager default `replication_factor: 3` startup errors) — see [rf-sf-sizing.md](rf-sf-sizing.md).
6. **Intent:** config-test labs may use minimal peers; **production-like** or strict RTO/RPO → use [rf-sf-sizing.md](rf-sf-sizing.md) + SVA; confirm with PS for production.
7. **Record in header** if lab compromises differ from SVA (e.g. single shared SH on multisite IDXC, fewer sites than DR target).

### Not covered (standalone indexers)

| SVA code | RF / SF | Notes |
|----------|---------|-------|
| S1 | N/A | Single node — no IDXC block |
| D1 | N/A | Standalone indexers — no `splunk_idxclusters` |

## Lab compromises (document in header)

| Compromise | SVA gap |
|------------|---------|
| Single shared SH on multisite IDXC | Per-site search affinity / DR behavior |
| No MC / LM / DS | Management tier not SVA-aligned |
| CM co-located with DS + deployer | Acceptable for small labs only |
