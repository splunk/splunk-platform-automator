# RF / SF and sizing — calculation guide

Rules below come from **Splunk Enterprise product documentation** and **SVA** guidance. The `spa-create-config` skill uses them for **recommendations and checklists** — not full production capacity planning. For large or regulated deployments, use PS and the [Deployment Capacity Manual](https://help.splunk.com/en/splunk-enterprise/get-started/deployment-capacity-manual).

See also: [sva-topology-map.md](sva-topology-map.md) (SVA code → lab defaults), [architecture-requirements.md](architecture-requirements.md) (ingest/users/DR questions).

## Authoritative links

| Topic | Link |
|-------|------|
| Replication factor (single-site) | [Replication factor](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/10.4/how-indexer-clusters-work/replication-factor) |
| Site replication factor | [Configure the site replication factor](https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/10.4/deploy-and-configure-a-multisite-indexer-cluster/configure-the-site-replication-factor) |
| Site search factor | [Configure the site search factor](https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/10.4/deploy-and-configure-a-multisite-indexer-cluster/configure-the-site-search-factor) |
| Multisite cluster architecture | [Multisite indexer cluster architecture](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/10.4/overview-of-indexer-clusters-and-index-replication/multisite-indexer-cluster-architecture) |
| Cluster deployment sizing | [System requirements for indexer clusters](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/10.4/deploy-the-indexer-cluster/system-requirements-and-other-deployment-considerations-for-indexer-clusters) |
| SVA M2 / M12 multisite | [Distributed Clustered Deployment - Multisite (M2 / M12)](https://help.splunk.com/en/data-management/splunk-validated-architectures/splunk-platform-indexing-and-search/distributed-clustered-deployment---multisite-m2--m12) |
| Storage estimate | [Estimate your storage requirements](https://help.splunk.com/en/splunk-enterprise/get-started/deployment-capacity-manual/10.2/hardware-capacity-planning/estimate-your-storage-requirements) |
| Performance bands (users × ingest) | [Summary of performance recommendations](https://help.splunk.com/en/splunk-enterprise/get-started/deployment-capacity-manual/10.2/performance-reference/summary-of-performance-recommendations) |
| DR planning (RTO/RPO) | [Developing a disaster recovery plan](https://lantern.splunk.com/Splunk_Success_Framework/Mitigate_Risk/Establishing_disaster_recovery_and_business_continuity/Developing_a_disaster_recovery_plan) (Lantern) |

## Single-site IDXC — calculate RF and SF

SPA keys: `idxc_rf`, `idxc_sf` on `splunk_idxclusters`.

### Failure tolerance (RF)

| Goal | Set `idxc_rf` |
|------|----------------|
| Tolerate **1** peer failure | `2` |
| Tolerate **2** concurrent peer failures | `3` (Splunk default) |
| Tolerate **N** failures | `N + 1` |

Rule: cluster tolerates **(RF − 1)** peer failures ([replication factor](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/10.4/how-indexer-clusters-work/replication-factor)).

### Search availability (SF)

| Goal | Set `idxc_sf` |
|------|----------------|
| Continue searches after **1** peer down | `2` (Splunk default) |
| Minimal extra storage | `1` (reduced search resilience) |

Rule: **SF ≤ RF** always. Splunk recommends default SF `2` for most cases.

### Minimum peer count

| Rule | Formula |
|------|---------|
| Minimum indexer **peers** before cluster indexes | **≥ `idxc_rf`** |
| Minimum **Splunk instances** in cluster | **RF + 2** (peers + cluster manager + at least one search head) |

Horizontal scale: you may run **more** peers than RF for ingest capacity; RF still caps failure tolerance.

### Lab vs production defaults

| Intent | Typical RF | Typical SF | Peers (minimum) |
|--------|------------|------------|-----------------|
| Config / infra test | `2` | `2` | `2` |
| Production-like | `3` | `2` | `3` (or more for ingest) |

SPA examples: `examples/cm_2idxc_sh_uf.yml` (RF/SF `2`).

## Multisite IDXC — calculate site RF / SF

SPA keys: `idxc_site_rf`, `idxc_site_sf` as strings, e.g. `'origin:2, total:3'`.

Optional: `idxc_rf` — sets legacy `replication_factor` on the manager. **Required for labs** when any site has **&lt; 3 peers** and `total` is `2` or `3`, because manager default `replication_factor` is `3` ([site replication factor doc](https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/10.4/deploy-and-configure-a-multisite-indexer-cluster/configure-the-site-replication-factor)). SPA adjusts `replication_factor` upward to match `total` when needed (`org_multisite_manager_base.yml`).

### Components

| Key | Meaning |
|-----|---------|
| `origin:N` | When a site is the **origin** of a bucket, it keeps **N** copies |
| `site1:M`, … | Explicit per-site minimum copies (optional) |
| `total:T` | **T** copies of each bucket **cluster-wide** |

### Minimum `total` (calculation)

**If any site is non-explicit** (only `origin` + some explicit sites, typical SPA lab):

```
total ≥ sum(origin + each explicit site value)
```

Example: `origin:2, site1:1, site2:2` → `total ≥ 5`.

**If all data sites are explicit** (`site1`, `site2`, …):

1. Find the **smallest** explicit site value.
2. Replace that site’s value with the **origin** value.
3. Sum all site values (with substitution) → minimum `total`.

Example: `origin:3, site1:1, site2:2, site3:3` → min site is `1` → substitute origin `3` → `3+2+3 = 8` minimum `total`.

SPA lab pattern `origin:2, total:3` with **two data sites** and **no explicit site keys** is valid when peer layout supports it (see `examples/4idxc2site_sh.yml`).

### Minimum peers per site

Each site must have at least:

```
peers_on_site ≥ max(origin value, that site's explicit site value if set)
```

Lab: `origin:2` → **2 indexer peers per data site** (CM on `site0` does not count toward site peer data copies).

### Site search factor

- Every site SF component **≤** corresponding RF component.
- Minimum `total` for site SF uses the **same rules** as site RF.
- **Search affinity**: need at least one **searchable** copy on each site where searches must run locally ([site search factor](https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/10.4/deploy-and-configure-a-multisite-indexer-cluster/configure-the-site-search-factor)).

### DR intent (SVA M2 / M12)

SVA multisite topology uses site RF/SF to spread copies across **failure domains** ([M2 / M12](https://help.splunk.com/en/data-management/splunk-validated-architectures/splunk-platform-indexing-and-search/distributed-clustered-deployment---multisite-m2--m12)). There is **no single RF string** for a given RPO — you derive:

1. **Sites** with indexers (≥ 2 for cross-site DR).
2. **RF/SF** so a **site loss** still leaves searchable copies on surviving sites (often `total` &gt; max per-site requirement, copies on multiple sites).
3. **Network latency** between sites within Splunk limits (Capacity Manual).

RTO/RPO → multisite + factors is **qualitative** in the skill; confirm with SVA + DR runbooks.

## Sizing beyond RF/SF (ingest, users, disk)

Not RF formulas — use for **Phase 2** tier hints only.

### Indexer count (performance table)

From [Summary of performance recommendations](https://help.splunk.com/en/splunk-enterprise/get-started/deployment-capacity-manual/10.2/performance-reference/summary-of-performance-recommendations) — **guideline only**:

- Reference indexer: up to **~300 GB/day** ingest with search load (reference hardware).
- Table maps **daily ingest band** × **concurrent users** → count of search heads and indexers.
- Premium apps (ES, heavy ITSI): use app-specific references; often **more indexers** than base table.

Skill action: if user states ingest + user band, **point to the table** and closest SVA example; do not auto-fill host counts without user confirmation.

### Storage (lab rough estimate)

Non-clustered per indexer ([storage estimate](https://help.splunk.com/en/splunk-enterprise/get-started/deployment-capacity-manual/10.2/hardware-capacity-planning/estimate-your-storage-requirements)):

```
indexed_GB ≈ (GB_per_day × retention_days) / 2    # ~50% compression
per_indexer_disk ≈ indexed_GB / indexer_count
```

Clustered ([cluster system requirements](https://help.splunk.com/en/splunk-enterprise/administer/manage-indexers-and-indexer-clusters/10.4/deploy-the-indexer-cluster/system-requirements-and-other-deployment-considerations-for-indexer-clusters)):

- Total cluster storage scales with RF/SF but **not linearly** at full RF: non-searchable replicas are smaller than searchable copies.
- Rule of thumb when RF=3 and SF=2: need **more than 2×, less than 3×** standalone storage **cluster-wide**; per-peer distribution is uneven (local ingest + replicas from peers).

Use `splunk_defaults.splunk_volume_defaults` / per-host `terraform.aws.root_volume_size` — skill suggests **50 GB lab**, larger when user states retention × ingest.

## Skill workflow — when to calculate vs copy

| Phase | Action |
|-------|--------|
| Phase 0b / 1 | Record ingest band, users, DR intent |
| Phase 5 | Pick SVA code → use tables in [sva-topology-map.md](sva-topology-map.md) |
| Phase 5 | If user states failure tolerance **N** → set RF = N+1 (single-site) or adjust `origin`/`total` (multisite) |
| Phase 5 | Run **peer count checklist** (this doc + topology map) |
| Phase 5 | If ingest/users band known → cite performance table; suggest indexer/SH **count** (not instance type) |
| Phase 7 | Write `splunk_idxclusters`; for multisite lab with 2 peers/site add `idxc_rf: 2` when `total ≤ 3` |

## Out of scope

- Automated RF/SF solver for arbitrary site explicit lists (use Splunk docs + PS).
- ES / ITSI full capacity models.
- SmartStore RF=SF constraint (see SmartStore examples; separate path).
