# SVA topology map

SVA codes describe **topology**, not sizing. Lab configs may diverge from full SVA DR (flag gaps in header).

| SVA code | SPA topology | Pattern |
|----------|-------------|---------|
| S1 | `examples/topologies/single_node.yml` | Single host: indexer + search_head (+ optional LM) |
| D1 | `examples/topologies/2idx_sh.yml` | Standalone indexers + SH |
| D11 | `examples/topologies/2idx_sh_es.yml` | D1 plus a dedicated ES search head |
| C1 | `examples/topologies/cm_2idxc_sh.yml` | CM + indexers + standalone SH. Compose: `spa init --example cm_2idxc_sh --provider aws\|virtualbox` |
| C11 | `examples/topologies/cm_2idxc_sh_es.yml` | C1 plus a dedicated ES search head |
| C3 | `examples/topologies/cm_2idxc_3shc_ds.yml` | CM + indexers + SHC + deployer |
| C13 | `examples/topologies/cm_2idxc_2x3shc_ds.yml` | C3 plus a dedicated ES search head cluster |
| M2 | `examples/topologies/4idxc2site_2sh.yml` | Multisite IDXC + one search head per site |
| M12 | `examples/topologies/4idxc2site_2sh_es.yml` | M2 plus a dedicated ES search head on each site |
| M3 | `examples/topologies/cm_4idxc2site_2x3shc_ds.yml` | Multisite IDXC + SHC per site |
| M13 | `examples/topologies/cm_4idxc2site_4x3shc_ds.yml` | M3 plus a dedicated ES search head cluster on each site |
| M4 | SVA documentation | Stretched SHC without a dedicated ES tier — escalate to SVA + PS |
| M14 | `examples/topologies/cm_4idxc2site_stretched_2x3shc_ds.yml` | Stretched SHCs plus a dedicated ES search tier |

## Multisite IDXC defaults (lab)

Typical from `examples/topologies/4idxc2site_2sh.yml`:

```yaml
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"
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
| C1 | `2` | `2` | **2** (`idxc_rf` ≤ peer count) | `examples/topologies/cm_2idxc_sh.yml` |
| C11 | `2` | `2` | **2** (`idxc_rf` ≤ peer count) | `examples/topologies/cm_2idxc_sh_es.yml` |
| C3 | `2` | `2` | **2** (integer `idxc_rf` / `idxc_sf`, plus one SHC) | `examples/topologies/cm_2idxc_3shc_ds.yml` |
| C13 | `2` | `2` | **2** (integer `idxc_rf` / `idxc_sf`, plus the ES SHC) | `examples/topologies/cm_2idxc_2x3shc_ds.yml` |

```yaml
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"
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
| M2 | `origin:2, total:3` | `origin:1, total:2` | **2** per site (supports `origin:2`) | **2** (typical lab) | `examples/topologies/4idxc2site_2sh.yml` |
| M12 | `origin:2, total:3` | `origin:1, total:2` | **2** per site (supports `origin:2`) | **2** (typical lab) | `examples/topologies/4idxc2site_2sh_es.yml` |
| M3 | `origin:2, total:3` | `origin:1, total:2` | **2** per site | **2** (+ SHC per site) | `examples/topologies/cm_4idxc2site_2x3shc_ds.yml` |
| M13 | `origin:2, total:3` | `origin:1, total:2` | **2** per site | **2** (+ ES SHC per site) | `examples/topologies/cm_4idxc2site_4x3shc_ds.yml` |
| M4 | Escalate | Escalate | Stretched SHC without a dedicated ES tier | SVA + PS | — |
| M14 | `origin:2, total:3` | `origin:1, total:2` | **2** per site | **2** (stretched SHC, `shc_site: site0`) | `examples/topologies/cm_4idxc2site_stretched_2x3shc_ds.yml` |

```yaml
splunk_idxclusters:
  - idxc_name: idxc1
    idxc_password: "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"
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
7. **Record in header** if lab compromises differ from SVA (e.g. fewer sites than the DR target). SVA M2 is one search head per site.

### Not covered (standalone indexers)

| SVA code | RF / SF | Notes |
|----------|---------|-------|
| S1 | N/A | Single node — no IDXC block |
| D1 | N/A | Standalone indexers — no `splunk_idxclusters` |
| D11 | N/A | D1 plus a dedicated ES search head — no `splunk_idxclusters` |

## Lab compromises (document in header)

| Compromise | SVA gap |
|------------|---------|
| Single shared SH on multisite IDXC | Removed. SVA M2 is one search head per site (`4idxc2site_2sh.yml`) |
| No MC / LM / DS | Management tier not SVA-aligned |
| CM co-located with DS + deployer | Acceptable for small labs only |
