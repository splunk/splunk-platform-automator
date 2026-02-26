# App deployment target filters – concept

## Goal

Introduce a **new**, unified filter model for **all apps** (normal and premium):

- **hosts_whitelist** / **hosts_blacklist** – restrict or remove specific hosts **in the relevant role only** (search heads for SH/SHC targeting). They do not filter license managers, indexers, or other roles.
- **shc_whitelist** / **shc_blacklist** – restrict or remove search heads by search head cluster (SHC name).
- **idxc_whitelist** / **idxc_blacklist** – restrict or remove indexers by indexer cluster (IDXC name).

Premium apps (e.g. ITSI) may use **hosts_whitelist** OR **shc_whitelist** for search head / SHC targeting (not both). **Blacklists are not allowed** on premium apps. When there is both an SHC and at least one standalone search head (or more than one standalone SH), the schema requires **shc_whitelist** or **hosts_whitelist** to be set for premium apps.

Deployment method (Deployment Server, Deployer, or direct) is unchanged: for **normal apps** it is derived from **target_roles** (mandatory), **deployment_target**, and inventory. **Premium apps** (e.g. ITSI) do **not** use `target_roles`; their deployment targets are determined internally by the premium role. The filters only **narrow or subtract** from the set of hosts that would otherwise receive the app for that method.

---

## Options (per app)

| Option | Type | Meaning |
|--------|------|---------|
| **hosts_whitelist** | list of host names | Keep only these hosts in the target set. Hosts not in this list are removed. |
| **hosts_blacklist** | list of host names | Remove these hosts from the target set. |
| **shc_whitelist** | list of SHC names | Keep only hosts that are members of one of these search head clusters. Must match `splunk_shclusters`. |
| **shc_blacklist** | list of SHC names | Remove hosts that are members of any of these SHCs. |
| **idxc_whitelist** | list of IDXC names | Keep only hosts that are members of one of these indexer clusters. Must match `splunk_idxclusters`. |
| **idxc_blacklist** | list of IDXC names | Remove hosts that are members of any of these IDXCs. |
| **am_whitelist** | list of patterns | **(Agent Management)** Explicit whitelist for serverclass: set to whatever patterns are valid in the serverclass whitelist specification (e.g. host names, **`*`** for all clients, or other patterns supported by Splunk serverclass). When set, replaces the computed filtered set for DS/AM; values are written as-is into the serverclass whitelist. AM is the new term for deployment server in Splunk public docs. |
| **am_blacklist** | list of host names | **(Agent Management)** Explicit blacklist for serverclass: these hosts are excluded from receiving this app from the deployment server. Applied after am_whitelist when both are set. |

- The six role/cluster filters above are **optional**.
- **am_whitelist** / **am_blacklist** are **optional** and apply only to apps distributed via the deployment server (Agent Management). They are used explicitly when configuring server classes. **am_whitelist** accepts whatever patterns are valid in the serverclass whitelist specification (e.g. host names, **`*`** for all clients, or other patterns supported by Splunk); the list is written as-is into the serverclass whitelist.
- **Whitelists** reduce the set to the given hosts or cluster members (intersection).
- **Blacklists** remove the given hosts or cluster members (set difference).
- Cluster names must exist in **splunk_shclusters** / **splunk_idxclusters** when used.
- **Normal apps:** **target_roles** is **mandatory**. **Premium apps:** do **not** define target_roles; targets are determined internally. **Premium apps** may use **hosts_whitelist** OR **shc_whitelist** (not both; no blacklists).
- **Cluster constraint:** You cannot exclude individual members of a search head cluster (SHC) or indexer cluster (IDXC). Cluster filters (**shc_whitelist**, **shc_blacklist**, **idxc_whitelist**, **idxc_blacklist**) apply at **cluster level only** (whole cluster in or out). Do not document or implement patterns that try to exclude a single host from within a cluster (e.g. shc_whitelist + hosts_blacklist for one SHC member); that is not technically possible.
- **Role-scoped hosts filters:** **hosts_whitelist** and **hosts_blacklist** are applied only to search heads (and SHC members in deployer context). License manager, indexer, and other roles are never removed by these filters.

---

## Single “filtered target host set”

For each app we define one **base set** and then apply filters in a fixed order to get the **filtered target host set**. That set is then used by DS, Deployer, and Direct to decide “does this host get this app?”.

### 1. Base set (per deployment context)

Base set = hosts that would receive this app **before** any of the new filters, using current logic:

- **Normal apps:** **target_roles** is mandatory. Base set is derived from `target_roles` (via `role_*` groups), **deployment_target**, and inventory (e.g. excluding SHC/IDXC members for DS).
- **Premium apps (e.g. ITSI):** Do **not** use `target_roles`; the premium role determines deployment targets internally (CM, LM, Deployer, search heads, etc.). Base set is that internal set per context.

Then, per context:

- **Deployment Server / Agent Management (AM):**  
  For normal apps: hosts in any of `target_roles` (via `role_*` groups), **excluding** members of any `idxcluster_*` and `shcluster_*` (AM does not push to clustered members today). For premium apps: whatever the premium role defines as “receives this app from AM”.

- **Deployer:**  
  Hosts that are **search_head** and members of **some** SHC. For premium apps: SHC members in scope per the premium role.

- **Direct:**  
  Hosts that get the app via direct deployment (standalone SH, standalone indexer, UF, HF, etc.). For premium apps: per premium role logic.

So we have three “base” sets depending on where we are (DS/AM, Deployer, or Direct). Filters are applied **to that base set** for that context.

### 2. Filter order (same in all contexts)

Apply in this order so behavior is predictable:

1. **shc_whitelist** (if set)  
   Keep only hosts that are in `groups['shcluster_X']` for some `X` in `shc_whitelist`.

2. **shc_blacklist** (if set)  
   Remove hosts that are in `groups['shcluster_X']` for any `X` in `shc_blacklist`.

3. **idxc_whitelist** (if set)  
   Keep only hosts that are in `groups['idxcluster_X']` for some `X` in `idxc_whitelist`.

4. **idxc_blacklist** (if set)  
   Remove hosts that are in `groups['idxcluster_X']` for any `X` in `idxc_blacklist`.

5. **hosts_whitelist** (if set)  
   Keep only hosts that appear in `hosts_whitelist`.

6. **hosts_blacklist** (if set)  
   Remove hosts that appear in `hosts_blacklist`.

Result = **filtered target host set** for that app in that context (DS, Deployer, or Direct).

### 3. Use of the filtered set

- **Deployment Server / Agent Management (AM):**  
  If **am_whitelist** is set, the serverclass whitelist is set to that value (a list of patterns valid per serverclass specification: host names, **`*`**, or other supported patterns; written as-is). If **am_blacklist** is set (and am_whitelist not set), start from the filtered target host set and remove hosts in am_blacklist. If both am_whitelist and am_blacklist are set, am_whitelist defines the set and am_blacklist is applied (remove those hosts). If neither is set, `app_whitelist_hosts` = filtered target host set (for the AM base set).

- **Deployer:**  
  Include this app on the deployer run if the filtered set (for the Deployer base set) is non-empty **and** contains at least one host that belongs to an SHC this deployer serves.

- **Direct:**  
  Include this app on a host if that host is in the filtered set (for the Direct base set).

Deployment method (DS/AM vs Deployer vs direct) is still determined by roles (for normal apps) or internal premium logic; we only restrict **which** hosts in that method get the app.

---

## Examples

**Only to a single search head:**

```yaml
target_roles: [search_head]
hosts_whitelist: [standalone_sh]
```

**Only to one SHC:**

```yaml
target_roles: [search_head]
shc_whitelist: [shc1]
```

**Premium app (ITSI) only to one SHC:**

```yaml
- name: "Splunk IT Service Intelligence"
  source: splunkbase
  app_id: 1841
  premium_app: itsi
  shc_whitelist: [shc1]
```

**To all search heads except one SHC:**

```yaml
target_roles: [search_head]
shc_blacklist: [shc_legacy]
```

**To indexers in two clusters only:**

```yaml
target_roles: [indexer]
idxc_whitelist: [idxc1, idxc2]
```

**To all UFs except a few hosts:**

```yaml
target_roles: [universal_forwarder]
hosts_blacklist: [uf_old_1, uf_old_2]
```

**Explicit serverclass list (Agent Management) – replaces computed whitelist:**

```yaml
target_roles: [universal_forwarder]
am_whitelist: [uf1, uf2, uf3]   # Only these hosts get this app from AM
```

**Serverclass whitelist “all clients” or other patterns:**

```yaml
target_roles: [universal_forwarder]
am_whitelist: ['*']   # Or any pattern valid in serverclass whitelist (per Splunk serverclass specs)
```

**Exclude specific hosts from AM delivery:**

```yaml
target_roles: [search_head]
am_blacklist: [sh_legacy]   # Computed set minus this host for serverclass
```

---

## Schema / validation

- **hosts_whitelist** / **hosts_blacklist:** list of strings (host names). No requirement that they exist in inventory (allows future hosts or typos; runtime may result in empty set).
- **shc_whitelist** / **shc_blacklist:** list of strings; each must match a **shc_name** in **splunk_shclusters**.
- **idxc_whitelist** / **idxc_blacklist:** list of strings; each must match an **idxc_name** in **splunk_idxclusters** (when that section exists).
- **am_whitelist** / **am_blacklist:** **am_whitelist** is a list of patterns valid for the serverclass whitelist (per Splunk serverclass specifications): e.g. host names, **`*`** for all clients, or other supported patterns. The list is written as-is into the serverclass whitelist. **am_blacklist** is a list of host names. Used only for serverclass (Agent Management) when the app is distributed via the deployment server. When **am_whitelist** is set, it replaces the computed filtered set for that app’s serverclass.
- Optional: forbid both a whitelist and blacklist for the same “dimension” (e.g. both **hosts_whitelist** and **hosts_blacklist**) if we want to keep configs simple; or allow both (whitelist then blacklist in the order above).

**Naming:** **am_whitelist** / **am_blacklist** replace the previous **deployment_whitelist** (and add an explicit blacklist). AM = Agent Management, the new term for deployment server in Splunk public documentation.

---

## Target filters (no app_sh_name / app_shc_name)

- **app_sh_name** and **app_shc_name** are **not used**. Use **hosts_whitelist** and **shc_whitelist** (and optional blacklists) instead.
- **Premium apps** (e.g. ITSI) use the same filter options as normal apps; they do **not** use **target_roles** (targets are determined internally).
- **hosts_whitelist: [hostname]** targets a single host (e.g. a standalone search head). **shc_whitelist: [shc_name]** targets an SHC.
- **deployment_whitelist** is **am_whitelist** (Agent Management). **am_blacklist** is the explicit blacklist for serverclass.

---

## Empty set after filtering

If after all filters the filtered target host set is **empty**:

- **DS / AM:** Do not add the app to the serverclass whitelist (or set whitelist to []). If **am_whitelist** was set, that list is still used (so the app is deployed to those hosts); only when using the computed set does “empty” mean no deployment.
- **Deployer:** Do not include this app in deployer_apps for that deployer.
- **Direct:** Do not add this app to direct_apps for any host.

No error; the app is simply not deployed anywhere.

---

## Open points

1. **am_whitelist / am_blacklist** – When **am_whitelist** is set, it overrides the computed filtered set for serverclass (current deployment_whitelist behavior). **am_blacklist** excludes hosts from that set. When both are set: apply am_whitelist first, then remove am_blacklist. **deployment_whitelist** is renamed to **am_whitelist**; **deployment_blacklist** is introduced as **am_blacklist**.
2. **Order of cluster vs host filters** – Current order (SHC → IDXC → hosts) is arbitrary; we could do hosts first. Document the chosen order and stick to it.
3. **Duplicate detection** – With the new model, deploy_key could include a hash or canonical form of the six filter options (and am_whitelist/am_blacklist if needed) so “same app, same filters” is one deployment and “same app, different filters” is allowed (different deploy_key).
4. **Performance** – Filtering is done in Ansible (set operations on host lists); for large inventories, consider caching the filtered set per app if needed.

---

## Summary

- **New feature:** Six optional filters for **normal apps**: **hosts_whitelist**, **hosts_blacklist**, **shc_whitelist**, **shc_blacklist**, **idxc_whitelist**, **idxc_blacklist**. Plus **am_whitelist** / **am_blacklist** (Agent Management). **Premium apps** may use **hosts_whitelist** OR **shc_whitelist** (not both; no blacklists, no idxc_*/am_*).
- **Normal apps:** **target_roles** is **mandatory**; deployment method is derived from target_roles, deployment_target, and inventory.
- **Premium apps:** Do **not** use target_roles; deployment targets are determined **internally** by the premium role; they may use **hosts_whitelist** OR **shc_whitelist** to narrow that set (not both; no blacklists).
- One consistent **filter order** applied to the **base set** per context (DS/AM, Deployer, Direct).
- **Filtered target host set** drives AM serverclass whitelist, deployer inclusion, and direct inclusion; **am_whitelist** overrides the computed set when set.
- **app_sh_name** / **app_shc_name** are not used; use **hosts_whitelist** and **shc_whitelist** (and optional blacklists for normal apps only).
