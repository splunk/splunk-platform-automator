# App deployment target filters

This document describes how to restrict which hosts receive an app when using Splunk Platform Automator app deployment. You can limit deployment by host name, by search head cluster (SHC), or by indexer cluster (IDXC).

## Overview

For each app you can optionally set **filters** that narrow or subtract from the set of hosts that would otherwise receive the app:

- **hosts_whitelist** / **hosts_blacklist** – Include or exclude specific hosts. These filters apply only to **search heads** (standalone and SHC members in deployer context). They do not filter license managers, indexers, or other roles.
- **shc_whitelist** / **shc_blacklist** – Include or exclude search heads by search head cluster name.
- **idxc_whitelist** / **idxc_blacklist** – Include or exclude indexers by indexer cluster name.
- **sc_whitelist** / **sc_blacklist** – (Agent Management / Deployment Server only) Control which clients get the app via the deployment server serverclass.

**Normal apps** must set **target_roles** (e.g. `[search_head]`, `[indexer]`). The schema also requires that **target_roles** includes every role that hosts in **hosts_whitelist** or **hosts_blacklist** have. **Premium apps** (e.g. ITSI) do not use `target_roles`; their targets are determined by the premium role. Premium apps may use **hosts_whitelist** OR **shc_whitelist** (not both) and may not use blacklists.

Cluster names in **shc_whitelist** / **shc_blacklist** must exist in **splunk_shclusters**; names in **idxc_whitelist** / **idxc_blacklist** must exist in **splunk_idxclusters**. Host names in **hosts_whitelist** / **hosts_blacklist** must exist in **splunk_hosts** and must not be cluster members (use SHC/IDXC filters for clusters).

---

## Filter options (per app)

| Option | Type | Description |
|--------|------|-------------|
| **hosts_whitelist** | list of host names | Keep only these hosts in the target set. Hosts not in this list are excluded. Applies only to search heads. |
| **hosts_blacklist** | list of host names | Exclude these hosts from the target set. Applies only to search heads. |
| **shc_whitelist** | list of SHC names | Keep only hosts that are members of one of these search head clusters. Names must match **splunk_shclusters**. |
| **shc_blacklist** | list of SHC names | Exclude hosts that are members of any of these SHCs. |
| **idxc_whitelist** | list of IDXC names | Keep only hosts that are members of one of these indexer clusters. Names must match **splunk_idxclusters**. |
| **idxc_blacklist** | list of IDXC names | Exclude hosts that are members of any of these indexer clusters. |
| **sc_whitelist** | list of patterns | **(Deployment Server / Agent Management)** Set the serverclass whitelist to these patterns (e.g. host names, `*` for all clients). When set, this replaces the computed target set for the serverclass. |
| **sc_blacklist** | list of host names | **(Deployment Server / Agent Management)** Exclude these hosts from receiving this app. Written in serverclass as `blacklist.0`, `blacklist.1`, … (indexed like whitelist). Applied after whitelist when both are set. |

- All of these filters are **optional**.
- **Deployment Server (serverclass) behaviour:**
  - **If sc_whitelist is defined:** It is always used directly for the serverclass whitelist (and **sc_blacklist** for the serverclass blacklist). No whitelist calculation is performed; sc_* overwrites calculation.
  - **If sc_whitelist is not defined:** The serverclass whitelist is **calculated** from **target_roles** and the hosts_*/idxc_*/shc_* filters, but only for hosts that are deployment server clients. **sc_blacklist** can still be set on the serverclass when defined.
- **hosts_whitelist** / **hosts_blacklist** (and idxc_*, shc_*) are used only to **calculate** the serverclass whitelist when sc_whitelist is not set; they apply to DS clients only.
- **sc_whitelist** accepts any pattern valid in the Splunk serverclass whitelist (e.g. host names or `*`). **sc_blacklist** is written as `blacklist.0`, `blacklist.1`, etc., same syntax as whitelist.
- **Whitelists** restrict the set to the given hosts or cluster members. **Blacklists** remove the given hosts or cluster members.
- **Premium apps** may use only **hosts_whitelist** OR **shc_whitelist** (not both) and may not use blacklists or idxc_*/sc_* filters.
- **hosts_whitelist** and **hosts_blacklist** cannot contain cluster members (SHC or IDXC); use **shc_whitelist** / **shc_blacklist** or **idxc_whitelist** / **idxc_blacklist** for cluster-level targeting.

---

## How filters are applied

For each app, the playbooks compute a **base set** of hosts (from **target_roles** and deployment method for normal apps, or from the premium role for premium apps). Filters are then applied in this **fixed order** to produce the final target set:

1. **shc_whitelist** – Keep only hosts in one of the listed SHCs.
2. **shc_blacklist** – Remove hosts in any of the listed SHCs.
3. **idxc_whitelist** – Keep only hosts in one of the listed indexer clusters.
4. **idxc_blacklist** – Remove hosts in any of the listed indexer clusters.
5. **hosts_whitelist** – Keep only hosts in this list.
6. **hosts_blacklist** – Remove hosts in this list.

That final set is used to decide which hosts get the app for Deployment Server (serverclass), Deployer (bundle), or direct deployment. **For serverclass only:** if **sc_whitelist** is set, it is used directly (no calculation); otherwise the serverclass whitelist is the calculated set above (applied only to deployment server clients). **sc_blacklist** is written as `blacklist.0`, `blacklist.1`, etc., and Splunk excludes those hosts from the whitelist.

---

## Examples

**Deploy only to a single search head:**

```yaml
target_roles: [search_head]
hosts_whitelist: [standalone_sh]
```

**Deploy only to one search head cluster:**

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

**Deploy to all search heads except one SHC:**

```yaml
target_roles: [search_head]
shc_blacklist: [shc_legacy]
```

**Deploy to indexers in two clusters only:**

```yaml
target_roles: [indexer]
idxc_whitelist: [idxc1, idxc2]
```

**Deploy to all universal forwarders except specific hosts:**

```yaml
target_roles: [universal_forwarder]
hosts_blacklist: [uf_old_1, uf_old_2]
```

**Deployment Server: only these hosts get this app (serverclass whitelist):**

```yaml
target_roles: [universal_forwarder]
sc_whitelist: [uf1, uf2, uf3]
```

**Deployment Server: all clients (serverclass whitelist):**

```yaml
target_roles: [universal_forwarder]
sc_whitelist: ['*']
```

**Deployment Server: exclude specific host from computed set:**

```yaml
target_roles: [search_head]
sc_blacklist: [sh_legacy]
```

---

## Empty target set

If after applying all filters the target set is **empty**:

- **Deployment Server:** The app is not added to the serverclass (or the whitelist is empty). If **sc_whitelist** was set, that list is still used.
- **Deployer:** The app is not included in the deployer bundle for that context.
- **Direct:** The app is not added to any host.

No error is raised; the app is simply not deployed.

---

## Related documentation

- [App Deployment Guide](App_Deployment_Guide.md) – Configuration and deployment methods
- [App Deployment Customizations](App_Deployment_Customizations.md) – Per-app customizations (remove, local_configs, run_playbook, etc.)
