# Architecture input (generator output)

`/spa-create-config` reads the architecture file that the SVA skill writes. The file has schema `0.3.0`. Its contract matches `splunk-validated-architectures/references/spa-handover.md`, section 5. The M4 example is `examples/topologies/cm_4idxc2site_stretched_3shc_ds.yml`.

Check the file, then get the hosts and cluster entries:

```bash
spa --agent architecture plan ARCHITECTURE.json
```

The plan is read-only. It never writes `splunk_config.yml`. Use `--write-fragment PATH` to write the merge input for `spa config merge --file`.

## Shape

```json
{
  "metadata": {"source_skill": "splunk-validated-architectures", "version": "0.3.0", "sva_code": "M4"},
  "environment": {"name": "test-m4-lab"},
  "phase_1": {"topology": "topology.m4", "sva": "M4", "sites": ["site1", "site2"], "confirmed": false},
  "phase_5": {
    "org_prefix": "test",
    "total_host_count": 10,
    "indexer_cluster": {
      "name": "idxc1", "sites": ["site1", "site2"],
      "site_rf": "origin:2, total:3", "site_sf": "origin:1, total:2",
      "peers": 4, "peers_by_site": {"site1": 2, "site2": 2}, "replication_port": 9887
    },
    "shcluster": {
      "name": "shc1", "members": 3, "members_by_site": {"site1": 2, "site2": 1},
      "shc_site": "site0", "replication_port": 9887
    },
    "optional_roles": [{"name": "lm", "role": "license_manager"}],
    "env_lookups": {"admin": "SPLUNK_ADMIN_PASSWORD", "idxc": "SPLUNK_IDXC_PASSWORD", "shc": "SPLUNK_SHC_PASSWORD"},
    "_extensions": [],
    "confirmed": false
  },
  "phase_5b": {"roles": ["cluster_manager", "indexer", "search_head", "deployer"], "confirmed": false}
}
```

## Fields the plan reads

| Field | Meaning |
| --- | --- |
| `phase_1.topology` | SPA catalog id, for example `topology.m4`. Required. |
| `phase_1.sva` | SVA code. Must match the topology in the catalog. |
| `phase_5.org_prefix` | Optional. Written as `splunk_env_name`. |
| `phase_5.indexer_cluster` | `name`, `sites`, `site_rf` and `site_sf` (text `origin:N, total:M`), `peers` (total), `peers_by_site` (one count per site). Multisite only. |
| `phase_5.shcluster` | `name`, `members` (total, at least 3), `members_by_site`, `replication_port`. `shc_site` is not read; the plan sets `site0`. |
| `phase_5.optional_roles` | List of `{name, role}`. Roles: `license_manager`, `deployment_server`, `monitoring_console`, `universal_forwarder`, `heavy_forwarder`. A `deployment_server` named `ds` merges into the deployer host. |
| `phase_5.env_lookups` | Keys `admin`, `idxc`, `shc`. Each value is an environment variable NAME such as `SPLUNK_ADMIN_PASSWORD`. Never a value. |
| `phase_5._extensions` | List of settings the schema does not know. Listed for mapping and never written to the config. |
| `phase_6b.license_file` | Resolved in the apply step. The contract requires it when `optional_roles` has a `license_manager`. The plan warns when it is missing, since this file never holds phase 6b; the spa skill collects it. `spa validate` checks it after the merge. |

The plan ignores `phase_5.apps_by_role` and warns. SPA decides the apps for each role.

`phase_5b.roles` and `phase_5.total_host_count` are informational. The plan builds its own hosts from `phase_5`.

## Phases not in this file

The SVA skill writes only phases 1 and 5. Every phase has a `"confirmed"` flag, which stays `false` until the user confirms the plan in chat. These phases are not written by the SVA skill: `"phase_0a"`, `"phase_0b"`, `"phase_2"`, `"phase_3"`, `"phase_4"`, `"phase_6"`, and `"phase_6b"`. `/spa-create-config` and the spa skill ask for them. The plan reads `phase_4.provider` and `phase_6b.license_file` only when they are present. Phases 6 and 6b are still asked by `/spa-create-config` even when `confirmed` is true.

## Rules

- Only multisite clusters are supported. Other SVA codes are not generated yet.
- Host names are set by the plan: `cm`, `ds`, `idx1`..`idxN`, `sh1`..`shN`, and each optional role name.
- Secrets are environment variable names. A secret value in place of a name is rejected, and the value is never shown.
- A key that looks like a credential (`password`, `secret`, `token`, `key`, `credential`) with a value is rejected.

## Plan output

- `data.hosts`: each host with its SPA roles and site.
- `data.secrets`: each env var name with `set` or `not set`. No values.
- `data.extensions`: each unmapped setting with its suggested placement.
- `data.fragment`: the `splunk_defaults`, `splunk_idxclusters`, `splunk_shclusters`, and `splunk_hosts` entries.
- `data.apply`: the steps to merge the fragment, remove the base host, and validate.

Show the hosts, the secrets as set or not set, and the extensions to the operator before any write. Apply only after the operator says yes.
