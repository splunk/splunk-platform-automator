# Splunk App Deployment – Target Logic

## Overview

This document describes how the app deployment system decides **where** each app is deployed (Deployment Server, Cluster Manager, Deployer, or directly to a host). For configuration syntax and playbook usage, see [Splunk_App_Deployment_Guide.md](Splunk_App_Deployment_Guide.md) and [Splunk_App_Deployment_Quick_Start.md](Splunk_App_Deployment_Quick_Start.md).

## Deployment Routing Summary

| Condition | Deployment target | Path (relative to `splunk_home`) |
|-----------|-------------------|----------------------------------|
| `deployment_target: "direct"` | Direct to host | `etc/apps` (or `target_path` override) |
| Indexer Cluster + role `indexer` | Cluster Manager | `etc/manager-apps` |
| Search Head Cluster + role `search_head` | Deployer | `etc/shcluster/apps` |
| Deployment Server + role UF/HF | Deployment Server | `etc/deployment-apps` |
| Default (standalone, etc.) | Direct to host | `etc/apps` |

Use **`target_path`** in app config to override the path for that app (e.g. `etc/apps` or a custom subdir). Use **`deployment_target: "direct"`** to force direct deployment and bypass DS/CM/Deployer.

## Decision Flow

```
For each app and each host that matches target_roles:

  ├─ Is app marked deployment_target: "direct"?
  │  └─ YES → Deploy directly to host (etc/apps or target_path)
  │
  ├─ Is host in an Indexer Cluster AND target_roles includes "indexer"?
  │  └─ YES → Deploy to Cluster Manager's manager-apps
  │
  ├─ Is host in a Search Head Cluster AND target_roles includes "search_head"?
  │  └─ YES → Deploy to Deployer's shcluster/apps
  │
  ├─ Is host a deployment client (UF/HF) AND Deployment Server exists?
  │  └─ YES → Deploy to Deployment Server's deployment-apps
  │
  └─ DEFAULT → Deploy directly to host (etc/apps or target_path)
```

## Role-Based Routing

### 1. Deployment Server distribution

- **When:** Host is a deployment client (Universal Forwarder or Heavy Forwarder) and the app’s `target_roles` includes `universal_forwarder` or `heavy_forwarder`, and `deployment_target` is not `"direct"`.
- **Where:** Deployment Server → `etc/deployment-apps/`.
- **Distribution:** Via `serverclass.conf` and deploy-server.

### 2. Indexer Cluster Manager distribution

- **When:** Host is in an Indexer Cluster and the app’s `target_roles` includes `indexer`, and `deployment_target` is not `"direct"`.
- **Where:** Cluster Manager → `etc/manager-apps/`.
- **Distribution:** Via `splunk apply cluster-bundle`.

### 3. Search Head Cluster Deployer distribution

- **When:** Host is in a Search Head Cluster and the app’s `target_roles` includes `search_head`, and `deployment_target` is not `"direct"`.
- **Where:** Deployer → `etc/shcluster/apps/`.
- **Distribution:** Via `splunk apply shcluster-bundle`.

### 4. Direct deployment

- **When:**
  - App has `deployment_target: "direct"`, or
  - Host matches `target_roles` but is standalone (not in IDXC/SHC, or not a DS client for that app), or
  - Fallback when no DS/CM/Deployer path applies.
- **Where:** On the host → `etc/apps/` (or `target_path` if set).

## Examples

### Deployment Server (forwarders)

```yaml
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  target_roles:
    - universal_forwarder
    - heavy_forwarder
```

**Result:**
- App deployed to: Deployment Server → `etc/deployment-apps/Splunk_TA_nix/`
- Distribution: serverclass whitelist (forwarders only)
- Benefit: Centralized forwarder app management

### Indexer Cluster Manager

```yaml
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  target_roles:
    - indexer
```

**Result:**
- App deployed to: Cluster Manager → `etc/manager-apps/Splunk_TA_nix/`
- Distribution: `splunk apply cluster-bundle` to indexer cluster
- Benefit: Single place to manage indexer apps

### Search Head Cluster Deployer

```yaml
- name: "custom_dashboard"
  source: local
  path: "/opt/splunk_apps/custom_dashboard"
  target_roles:
    - search_head
```

**Result:**
- App deployed to: Deployer → `etc/shcluster/apps/custom_dashboard/`
- Distribution: `splunk apply shcluster-bundle` to search head cluster
- Benefit: Single place to manage SHC apps

### Direct deployment (override)

```yaml
- name: "test_app"
  source: local
  path: "/opt/splunk_apps/test_app"
  target_roles:
    - indexer
  target_path: "etc/apps"   # Optional: override install path
  deployment_target: "direct"   # Force direct deployment
```

**Result:**
- App deployed to: indexer host(s) directly → `etc/apps/test_app/` (or `target_path` if different)
- Distribution: None (direct only)
- Benefit: Testing or special cases

---

## Implementation Logic

### Python-Style Pseudocode

The following pseudocode describes how deployment target and path are determined for a given app and host. In practice, the playbook runs **per-role** (DS, CM, Deployer, Direct), and each role filters apps; the logic below is the conceptual union of those filters.

```python
def get_deployment_target(app, host):
    """Determine where an app is deployed for a given host."""
    roles = host.roles  # e.g. from group_names (role_*)
    target_roles = app.get("target_roles", [])
    deployment_target = app.get("deployment_target", "auto")

    # Host must match at least one target_role for the app
    if not (set(roles) & set(target_roles)):
        return None  # App not applicable to this host

    def path_for(default_relative):
        """Use app.target_path if set, else default for the deployment method."""
        return app.get("target_path") or f"{host.splunk_home}/{default_relative}/{app['name']}"

    # 1. Explicit direct override
    if deployment_target == "direct":
        return ("direct", host, path_for("etc/apps"))

    # 2. Indexer cluster: deploy to Cluster Manager
    if "indexer" in target_roles and host_in_indexer_cluster(host):
        return ("cluster_manager", cluster_manager_host, path_for("etc/manager-apps"))

    # 3. Search head cluster: deploy to Deployer
    if "search_head" in target_roles and host_in_search_head_cluster(host):
        return ("deployer", deployer_host, path_for("etc/shcluster/apps"))

    # 4. Forwarders: deploy to Deployment Server
    if set(target_roles) & {"universal_forwarder", "heavy_forwarder"} and roles_include_forwarder(roles):
        return ("deployment_server", deployment_server_host, path_for("etc/deployment-apps"))

    # 5. Default: direct to host (standalone indexer/search_head, or other roles)
    return ("direct", host, path_for("etc/apps"))
```

### Ansible Implementation

The playbook uses four roles that run on different host subsets. Each role **filters** `splunk_app_deployment.apps` and only processes apps that belong to that deployment method.

| Role | Runs on | Filter condition (app included when) |
|------|---------|-------------------------------------|
| **apps_deployment_server** | Deployment Server hosts | `target_roles` ∩ {universal_forwarder, heavy_forwarder} ≠ ∅ and `deployment_target` ≠ `"direct"` |
| **apps_cluster_manager** | Cluster Manager hosts | `indexer` ∈ `target_roles` and `deployment_target` ≠ `"direct"` |
| **apps_deployer** | Deployer hosts | `search_head` ∈ `target_roles` and `deployment_target` ≠ `"direct"` |
| **apps_direct** | All other hosts (per-host) | Host roles ∩ `target_roles` ≠ ∅ **and** ( `deployment_target` == `"direct"` **or** host is standalone: not DS/CM/Deployer, not UF/HF, and if indexer then not in IDXC, if search_head then not in SHC ) |

**Direct-app filter (simplified):** An app is in `direct_apps` on a host when the host has at least one matching `target_role` and either the app forces direct (`deployment_target: "direct"`) or the host is a standalone instance (no DS/CM/Deployer role, not a forwarder, and if indexer/search_head then not in that cluster).

### Path Calculation

Each role’s `install_app.yml` sets the install path for the app:

- **`app_target_path`** = `app_item.target_path` if set, otherwise the role-specific default:
  - **Deployment Server:** `{{ splunk_home }}/etc/deployment-apps/{{ app_item.name }}`
  - **Cluster Manager:** `{{ splunk_home }}/etc/manager-apps/{{ app_item.name }}`
  - **Deployer:** `{{ splunk_home }}/etc/shcluster/apps/{{ app_item.name }}`
  - **Direct:** `{{ splunk_home }}/etc/apps/{{ app_item.name }}`

So **`target_path`** is an override for the install directory (or full path) for that app; when not set, the path is derived from the deployment method.

### Execution Order

The playbook typically runs roles in order so that distribution points are populated before or in line with direct deployments:

1. **apps_deployment_server** (on DS hosts)
2. **apps_cluster_manager** (on CM hosts)
3. **apps_deployer** (on Deployer hosts)
4. **apps_direct** (on all other hosts)

Handlers (e.g. “Reload deploy-server”, “Apply indexer cluster bundle”, “Push shcluster bundle”) run after their respective role’s tasks, so distribution is triggered after apps are installed on DS/CM/Deployer.
