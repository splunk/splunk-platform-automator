# Role placement on hosts

After topology **counts** (Phase 5), map **roles onto hosts**. SVAs favor tier separation; labs often co-locate management roles.

See [role-placement.md](role-placement.md) opening strategy question in SKILL.md workflow.

## SPA hard constraints (enforce)

| Rule | Why |
|------|-----|
| `cluster_manager` host needs `idxcluster:` | CM belongs to an indexer cluster |
| Multisite CM/indexers need `site:` | Multisite IDXC |
| `deployer` host needs `shcluster:` | Deployer pushes to a specific SHC |
| `license_manager` requires `splunk_license_file` in `splunk_defaults` | Schema validation |
| `splunk_license_file` requires `license_manager` on a host | Schema validation — omit file for trial-only labs |
| SHC members: `search_head` + `shcluster:` on SH nodes only | Not on CM/indexers |
| Indexer members: `indexer` + `idxcluster:` | No SHC on indexers in clustered topologies |

## SVA-aligned placement

| Host | Roles | Notes |
|------|-------|-------|
| `mc` | `monitoring_console`, `license_manager` | Central ops + licensing |
| `cm` | `cluster_manager` | `site: site0` for multisite; avoid CM built-in search in production |
| `ds` | `deployment_server`, `deployer` | Deployer sets `shcluster: shc1` |
| `idx*` | `indexer` | One role per host; `site` per multisite layout |
| `sh*` | `search_head` | Standalone or SHC members |
| `hf` / `uf` | forwarder roles | Optional |

Reference: `tests/configs/2site-idxc_shc_mc_ds_hf_uf.yml`

## Lab-minimal patterns

| Pattern | Example hosts | Co-located roles | SPA example | Flag |
|---------|---------------|------------------|-------------|------|
| Mgmt-minimal | `cm` only | `cluster_manager` | Minimal IDXC+SH | No MC, LM, DS |
| CM + MC | `cm` | `cluster_manager`, `monitoring_console` | `examples/ds_cm_2idxc1site_sh_hf_uf.yml` | LM/DS separate or omitted |
| CM + LM | `cm` | `cluster_manager`, `license_manager` | `configuration_description.yml` | Needs license file |
| MC + LM | `mc` | `monitoring_console`, `license_manager` | 2site test configs | CM stays dedicated |
| DS + deployer | `ds` | `deployment_server`, `deployer` | Most SHC examples | SVA-acceptable |
| Ultra-minimal SHC | `cm` | `cluster_manager`, `deployment_server`, `deployer` | `examples/cm_2idxc1site_3shc_uf.yml` | Small labs only |
| S1 all-in-one | `shidx` | `indexer`, `search_head`, `license_manager` | `examples/single_node.yml` | Not clustered |

## Placement questions (ask only if topology requires)

1. **Monitoring Console** — dedicated `mc`, on `cm`, or omit?
2. **License Manager** — dedicated, co-located, or omit (trial)?
3. **Deployment Server** — dedicated `ds`, co-located with deployer, on `cm`, or omit?
4. **Deployer** — required for SHC; on `ds` (typical); must set `shcluster:`
5. **Search tier** — standalone `sh` vs SHC nodes (no SH on indexers in clustered SVA)
6. **Per-site search (M2/M3)** — SH per site vs one shared SH (lab compromise)
7. **Forwarders** — dedicated `uf`/`hf` or omit

## Exit criteria

- Host list with roles summarized (e.g. `cm: cluster_manager | idx1-4: indexer | sh: search_head`)
- Placement strategy recorded for header comment
