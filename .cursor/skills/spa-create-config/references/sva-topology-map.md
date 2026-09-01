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

## Lab compromises (document in header)

| Compromise | SVA gap |
|------------|---------|
| Single shared SH on multisite IDXC | Per-site search affinity / DR behavior |
| No MC / LM / DS | Management tier not SVA-aligned |
| CM co-located with DS + deployer | Acceptable for small labs only |
