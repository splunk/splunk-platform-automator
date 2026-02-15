# App Deployment – Complete Guide

## Overview

This guide covers the complete Splunk app deployment system, including:
- Deployment Server distribution
- Indexer Cluster Manager app distribution
- Search Head Cluster Deployer app distribution
- Direct deployment
- App state management (install/remove)
- Multi-role deployments

## Table of Contents

1. [Deployment Methods](#deployment-methods)
2. [App Configuration](#app-configuration)
3. [State Management](#state-management)
4. [Clustered Environments](#clustered-environments)
5. [Deployment Server Setup](#deployment-server-setup)
6. [Troubleshooting](#troubleshooting)


## Deployment Methods

The system automatically determines the best deployment method for each app based on the target host's role and cluster membership:

### 1. Deployment Server Distribution
**When:** Universal Forwarders, Heavy Forwarders (non-clustered)
**Location:** `/opt/splunk/etc/deployment-apps/` on Deployment Server
**Distribution:** Via `serverclass.conf` whitelist
**Best for:** Forwarders that need centralized app management

### 2. Indexer Cluster Manager Distribution
**When:** Indexers that are part of an Indexer Cluster
**Location:** `/opt/splunk/etc/manager-apps/` on Cluster Manager
**Distribution:** Via `splunk apply cluster-bundle`
**Best for:** Indexer cluster members (automatically detected)

### 3. Search Head Cluster Deployer Distribution
**When:** Search Heads that are part of a Search Head Cluster
**Location:** `/opt/splunk/etc/shcluster/apps/` on Deployer
**Distribution:** Via `splunk apply shcluster-bundle`
**Best for:** Search Head cluster members (automatically detected)

### 4. Direct Deployment
**When:** 
- Standalone indexers/search heads (not in clusters)
- Apps with `deployment_target: "direct"`
- Deployment clients not yet configured (fallback)
**Location:** `/opt/splunk/etc/apps/` on target host
**Distribution:** Direct file synchronization
**Best for:** Standalone instances, cluster managers/deployers themselves

### Deployment Decision Logic

```
For each host with target_role:
  ├─ Is app marked deployment_target: "direct"?
  │  └─ YES → Deploy directly to etc/apps
  │
  ├─ Is host in an Indexer Cluster AND target_role includes "indexer"?
  │  └─ YES → Deploy to Cluster Manager's manager-apps
  │
  ├─ Is host in a Search Head Cluster AND target_role includes "search_head"?
  │  └─ YES → Deploy to Deployer's shcluster/apps
  │
  ├─ Is host a deployment client (UF/HF)?
  │  └─ YES → Deploy to Deployment Server's deployment-apps
  │
  └─ DEFAULT → Deploy directly to etc/apps
```

## App Configuration

### Top-level download option: target_download

Under `splunk_app_deployment` you can set:

```yaml
splunk_app_deployment:
  target_download: false   # default: when true, each target downloads from Splunkbase
```

- **`target_download: false`** (default): The Ansible controller downloads each Splunkbase app once, then copies and extracts it to each target. Best when the controller has good bandwidth to Splunkbase and to the targets.
- **`target_download: true`**: Each target host downloads the app from Splunkbase. Use this when upload speed from the Ansible host to targets is slow (e.g. large apps); each target only needs outbound access to Splunkbase and uses its own download.

### Basic App Definition

```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      target_roles:
        - universal_forwarder
        - heavy_forwarder
        - indexer
```

### Configuration Options

```yaml
- name: "app_name"                    # Required: App name (must match app folder name)
  source: splunkbase|local            # Required: App source
  
  # For Splunkbase apps:
  app_id: 833                         # Required for splunkbase
  version: "3.0.0"                    # Optional: Specific version (default: latest)
  
  # For Local apps:
  path: "/path/to/app"                # Required for local apps
  
  # State Management:
  state: installed|absent             # Optional: App state (default: installed)
  
  # Deployment Targeting:
  target_roles:                       # Required: List of roles to deploy to
    - universal_forwarder
    - heavy_forwarder
    - indexer
    - search_head
    - cluster_manager
    - deployer
  
  # Advanced Options:
  deployment_target: auto|direct      # Optional: Force direct deployment (default: auto)
  deployment_whitelist: ["host1", "host2"]  # Optional: Manual whitelist (default: auto-calculated)
  serverclass: "custom_class"         # Optional: Custom serverclass name (default: app_<appname>)
```

### Splunkbase apps: name must match archive folder

For apps from **Splunkbase** (`source: splunkbase`), the **`name`** in your config must be exactly the same as the **top-level folder name** inside the app archive downloaded from Splunkbase.

- The playbook downloads the app by `app_id` and checks that the archive’s top-level folder matches `name`.
- If they differ (for example you used the wrong `app_id` for another app), the playbook **removes the extracted directory** and **fails** with a clear message asking you to check `app_id`.
- Use the app’s official internal name: e.g. `Splunk_TA_nix`, `Splunk_TA_snow`, `Splunk_SA_CIM`. You can confirm the folder name from the Splunkbase app page or by inspecting the downloaded `.tgz`.

## State Management

### Installing Apps

Apps default to `state: installed` if not specified:

```yaml
# These are equivalent:
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  target_roles:
    - universal_forwarder

- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  state: installed  # Explicit
  target_roles:
    - universal_forwarder
```

### Removing Apps

Set `state: absent` to remove an app:

```yaml
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  state: absent  # Will be removed
  target_roles:
    - universal_forwarder
```

**Removal behavior:**
- **Deployment Server:** Removes app from `deployment-apps/` and updates serverclass to exclude hosts
- **Cluster Manager:** Removes app from `manager-apps/` and pushes cluster bundle
- **Deployer:** Removes app from `shcluster/apps/` and pushes shcluster bundle
- **Direct:** Removes app from `etc/apps/` on target host

### Multiple Entries for Same App

**Use Case:** Install app on some roles, remove from others

```yaml
splunk_app_deployment:
  apps:
    # Install on forwarders and indexers
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      target_roles:
        - universal_forwarder
        - heavy_forwarder
        - indexer
    
    # Remove from search heads
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      state: absent
      target_roles:
        - search_head
```

**Important:** Each app entry is processed independently. The system ensures each host only processes the relevant entries for its roles.

### Direct Deployment Override

Force direct deployment (bypass Deployment Server/Cluster distribution):

```yaml
- name: "special_app"
  source: local
  path: "/opt/apps/special_app"
  deployment_target: "direct"  # Always deploy directly to etc/apps
  target_roles:
    - universal_forwarder  # Even deployment clients get direct deployment
```

**Use cases:**
- Apps that must not go through deployment server
- Apps requiring immediate deployment without DS phone-home
- Testing/debugging specific apps

## Clustered Environments

### Automatic Cluster Detection

The system automatically detects cluster membership via Ansible inventory groups:

```yaml
# Inventory structure (from dynamic inventory plugin):
groups:
  role_indexer: [idx1, idx2, idx3]
  role_search_head: [sh1, sh2, sh3]
  idxcluster_idxc1: [idx1, idx2, idx3]       # Indexer cluster members
  shcluster_shc1: [sh1, sh2, sh3]            # Search head cluster members
  role_cluster_manager: [cm]
  role_deployer: [deployer]
```

### Indexer Cluster Apps

**Targeting indexers in a cluster:**

```yaml
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  target_roles:
    - indexer  # Will deploy to Cluster Manager, not individual indexers
```

**What happens:**
1. System detects idx1, idx2, idx3 have role `indexer`
2. System detects they are in `idxcluster_idxc1` group
3. System finds `cm` (cluster_manager in same cluster)
4. App deployed to `cm:/opt/splunk/etc/manager-apps/Splunk_TA_nix/`
5. Handler notifies: `Apply indexer cluster bundle`
6. CM pushes bundle to all cluster members

**Handler behavior:**
- Only runs if app files actually changed
- Automatically finds correct CM for the cluster
- Uses `splunk apply cluster-bundle --answer-yes`

### Search Head Cluster Apps

**Targeting search heads in a cluster:**

```yaml
- name: "search_app"
  source: local
  path: "/opt/apps/search_app"
  target_roles:
    - search_head  # Will deploy to Deployer, not individual SHs
```

**What happens:**
1. System detects sh1, sh2, sh3 have role `search_head`
2. System detects they are in `shcluster_shc1` group
3. System finds `deployer` (deployer in same cluster)
4. App deployed to `deployer:/opt/splunk/etc/shcluster/apps/search_app/`
5. Handler notifies: `Push shcluster bundle`
6. Deployer pushes bundle to all cluster members

### Cluster Exclusion from Deployment Server

**Important:** Clustered hosts are automatically excluded from deployment server whitelists:

```yaml
- name: "Splunk_TA_nix"
  target_roles:
    - universal_forwarder  # uf → Deployment Server
    - indexer              # idx1,idx2,idx3 (clustered) → Cluster Manager
    - search_head          # sh1,sh2,sh3 (clustered) → Deployer
```

**Serverclass whitelist will include:**
- `uf` (deployment client)

**Serverclass whitelist will NOT include:**
- `idx1`, `idx2`, `idx3` (get apps via CM)
- `sh1`, `sh2`, `sh3` (get apps via Deployer)

This prevents conflicts where apps are pushed via both DS and cluster distribution.

### Mixed Environment Example

```yaml
splunk_app_deployment:
  apps:
    # Indexer app - distributed via cluster
    - name: "indexer_tech_addon"
      source: splunkbase
      app_id: 833
      target_roles:
        - indexer  # Goes to CM → cluster members
    
    # Forwarder app - distributed via DS
    - name: "forwarder_addon"
      source: splunkbase
      app_id: 742
      target_roles:
        - universal_forwarder  # Goes to DS → deployment clients
        - heavy_forwarder
    
    # Search app - distributed via deployer
    - name: "search_dashboard"
      source: local
      path: "/opt/apps/search_dashboard"
      target_roles:
        - search_head  # Goes to Deployer → SHC members
    
    # Management app - direct deployment
    - name: "cluster_manager_app"
      source: local
      path: "/opt/apps/cm_app"
      target_roles:
        - cluster_manager  # Direct to CM itself
```

## Deployment Server Setup


### Prerequisites

For Deployment Server distribution to work, forwarders must be configured as deployment clients.

### Option 1: Configure Deployment Client First (Recommended)

**Step 1: Add deployment server to splunk_defaults**

```yaml
# In config/splunk_config.yml under splunk_defaults:
splunk_defaults:
  # ... existing settings ...
  
  # Deployment Server Configuration
  splunk_deployment_server:
    - ds  # Hostname of your deployment server
```

**Step 2: Ensure org_all_deploymentclient is deployed**

The universal_forwarder role should automatically apply `org_all_deploymentclient` which creates:

```ini
# /opt/splunkforwarder/etc/apps/org_all_deploymentclient/local/deploymentclient.conf
[target-broker:deploymentServer]
targetUri = ds:8089
```

**Step 3: Deploy the baseconfig first**

```bash
# Deploy the environment (includes deployment client config)
ansible-playbook ansible/site.yml -i config/splunk_config.yml
```

**Step 4: Then deploy apps**

```bash
# Now app deployment will use DS
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
```

### Option 2: Force Direct Deployment

Use `deployment_target: "direct"` to bypass deployment server:

```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      target_roles:
        - universal_forwarder
      deployment_target: "direct"  # Deploy directly to UF, bypass DS
```

**Use case:**
- Deployment client not configured yet
- Need immediate deployment without DS phone-home
- Testing specific apps

### Option 3: Manual Deployment Client Configuration

If `org_all_deploymentclient` isn't working, manually configure:

```bash
# On the UF host
cat > /opt/splunkforwarder/etc/system/local/deploymentclient.conf << 'EOF'
[deployment-client]

[target-broker:deploymentServer]
targetUri = ds:8089
EOF

# Restart UF
/opt/splunkforwarder/bin/splunk restart
```

Then redeploy the app.

### Serverclass Configuration

The system automatically creates and manages `serverclass.conf` on the deployment server:

**Auto-calculated whitelist:**
```yaml
- name: "Splunk_TA_nix"
  target_roles:
    - universal_forwarder
    - heavy_forwarder
```

**Generated serverclass.conf:**
```ini
[serverClass:app_Splunk_TA_nix]
whitelist.0 = uf
whitelist.1 = hf1
whitelist.2 = hf2

[serverClass:app_Splunk_TA_nix:app:Splunk_TA_nix]
restartSplunkd = true
stateOnClient = enabled
```

**Manual whitelist:**
```yaml
- name: "Splunk_TA_nix"
  deployment_whitelist:
    - uf
    - hf1
  # Ignores target_roles for whitelist calculation
```

**Smart Updates:**
The system compares the current serverclass whitelist with the desired state and only updates if different, preventing unnecessary DS reloads.

### Verification

### Check Deployment Server

```bash
# Check serverclass configuration
cat /opt/splunk/etc/system/local/serverclass.conf

# List deployment clients
/opt/splunk/bin/splunk list deploy-clients -auth admin:password

# Check app deployment status
/opt/splunk/bin/splunk list deploy-server -auth admin:password
```

### Check Indexer Cluster

```bash
# On Cluster Manager - check manager-apps
ls -la /opt/splunk/etc/manager-apps/

# Check cluster bundle status
/opt/splunk/bin/splunk show cluster-bundle-status -auth admin:password

# On Indexer - check if app is present
ls -la /opt/splunk/etc/apps/
```

### Check Search Head Cluster

```bash
# On Deployer - check shcluster apps
ls -la /opt/splunk/etc/shcluster/apps/

# Check deployer status
/opt/splunk/bin/splunk show shcluster-status -auth admin:password

# On Search Head - check if app is present
ls -la /opt/splunk/etc/apps/
```

## Troubleshooting

### Debug Output

Run with verbose output to see deployment decisions:

```bash
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml -v
```

**Key debug messages:**
- `DEPLOYMENT DECISION FOR: <app_name>` - Shows calculated target and deployment reason
- `Calculate whitelist hosts for <app_name>` - Shows DS whitelist calculation
- `Serverclass configuration for <serverclass>` - Shows DS configuration updates
- `Debug removal check for <app_name>` - Shows app removal status

### Common Issues

#### Issue: App deploys to wrong location

**Symptom:** App goes to DS instead of Cluster Manager

**Cause:** Host's cluster membership not detected correctly

**Check:**
```bash
# Verify Ansible inventory groups
ansible-inventory -i config/splunk_config.yml --graph

# Should show cluster groups like:
#   |--@idxcluster_idxc1:
#   |  |--idx1
#   |  |--idx2
```

**Fix:** Ensure inventory plugin correctly populates cluster groups

#### Issue: App installed when it should be removed

**Symptom:** `state: absent` but app still gets installed

**Cause:** Multiple app entries with same name, state persisting across entries

**Check:** Look for duplicate app entries in `splunk_config.yml`

**Solution:** Each app entry is processed independently per host. Ensure:
- First entry: roles where app should be installed
- Second entry: roles where app should be removed with `state: absent`

```yaml
# Correct:
- name: "Splunk_TA_nix"
  target_roles: [indexer]  # Install on indexers

- name: "Splunk_TA_nix"
  state: absent
  target_roles: [search_head]  # Remove from search heads
```

#### Issue: Cluster bundle not pushing

**Symptom:** App appears on CM/Deployer but not on cluster members

**Cause:** Handler not triggered (no actual change detected)

**Check:**
```bash
# Check if handler ran
# Look for: "RUNNING HANDLER [splunk_common : Apply indexer cluster bundle]"
```

**Solution:** Handlers only run when files actually change. To force:
```bash
# Manually push bundle
/opt/splunk/bin/splunk apply cluster-bundle -auth admin:password --answer-yes
```

#### Issue: Serverclass not updating

**Symptom:** Old hosts still in serverclass whitelist

**Cause:** Smart update logic detects no difference

**Check:**
```bash
# Compare current vs desired
cat /opt/splunk/etc/system/local/serverclass.conf
```

**Solution:** The system compares current and desired whitelists. If they match (after sorting), no update occurs. This is intentional to avoid unnecessary DS reloads.

#### Issue: Direct deployment not working

**Symptom:** `deployment_target: "direct"` but still goes through DS/Cluster

**Cause:** Cluster detection overriding direct deployment

**Check:** Verify `deployment_target` is set correctly:

```yaml
- name: "app_name"
  deployment_target: "direct"  # Must be exactly "direct"
  target_roles:
    - universal_forwarder
```

#### Issue: Whitelist includes clustered hosts

**Symptom:** Indexers/SHs appear in DS serverclass whitelist

**Cause:** Host group membership not excluding clusters

**This should not happen.** The whitelist calculation automatically excludes:
- Hosts in `idxcluster_*` groups (when deployed as indexers)
- Hosts in `shcluster_*` groups (when deployed as search heads)

**Check inventory:**
```bash
ansible-inventory -i config/splunk_config.yml --list
```

### Expected Behavior Summary

| Host Type | Target Role | Deployment Method | Location |
|-----------|-------------|-------------------|----------|
| UF (deployment client) | universal_forwarder | Deployment Server | `/opt/splunkforwarder/etc/apps/` (pushed by DS) |
| HF (deployment client) | heavy_forwarder | Deployment Server | `/opt/splunk/etc/apps/` (pushed by DS) |
| Indexer (clustered) | indexer | Cluster Manager | `/opt/splunk/etc/apps/` (pushed by CM) |
| Indexer (standalone) | indexer | Direct | `/opt/splunk/etc/apps/` (direct sync) |
| Search Head (clustered) | search_head | Deployer | `/opt/splunk/etc/apps/` (pushed by Deployer) |
| Search Head (standalone) | search_head | Direct | `/opt/splunk/etc/apps/` (direct sync) |
| Cluster Manager | cluster_manager | Direct | `/opt/splunk/etc/apps/` (direct sync) |
| Deployer | deployer | Direct | `/opt/splunk/etc/apps/` (direct sync) |
| Any role with `deployment_target: "direct"` | any | Direct | `/opt/splunk/etc/apps/` (direct sync) |

## Expected Flow


### Deployment Flow Examples

#### Example 1: Mixed Environment with Clusters

**Configuration:**
```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      target_roles:
        - universal_forwarder
        - indexer
        - search_head
```

**Execution:**
```
1. Playbook runs across all hosts:
   uf  → Role: universal_forwarder → Calculate target: Deployment Server
   idx1 → Role: indexer, in idxcluster_idxc1 → Calculate target: Cluster Manager (cm)
   idx2 → Role: indexer, in idxcluster_idxc1 → Calculate target: Cluster Manager (cm)
   sh1 → Role: search_head, in shcluster_shc1 → Calculate target: Deployer
   sh2 → Role: search_head, in shcluster_shc1 → Calculate target: Deployer

2. Deduplication logic ensures one deployment per target:
   uf (first) → Deploys to DS (others skipped for same target)
   idx1 (first) → Deploys to CM (idx2 skipped for same target)
   sh1 (first) → Deploys to Deployer (sh2 skipped for same target)

3. Serverclass created on DS:
   Whitelist: [uf]  ← Only deployment clients, excludes clustered hosts

4. Handlers triggered (if files changed):
   DS → Reload deploy-server
   CM → Apply indexer cluster bundle
   Deployer → Push shcluster bundle

5. Distribution:
   uf ← Receives app from DS on next phone-home
   idx1, idx2 ← Receive app from CM bundle push
   sh1, sh2 ← Receive app from Deployer bundle push
```

#### Example 2: App Removal from Search Heads

**Configuration:**
```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      target_roles:
        - universal_forwarder
        - indexer

    - name: "Splunk_TA_nix"
      state: absent  # Remove from search heads
      target_roles:
        - search_head
```

**Execution:**
```
1. Entry 1 processes:
   uf → state: installed → Deploy to DS
   idx1,idx2 → state: installed → Deploy to CM
   sh1,sh2 → Don't match target_roles → Skip

2. Entry 2 processes:
   uf → Don't match target_roles → Skip
   idx1,idx2 → Don't match target_roles → Skip
   sh1,sh2 → state: absent, match search_head → Remove from Deployer

3. Serverclass for Entry 1:
   Whitelist: [uf]

4. Removal for Entry 2:
   Deployer: Remove Splunk_TA_nix from shcluster/apps/
   Handler: Push shcluster bundle
   Result: App removed from sh1, sh2
```

#### Example 3: Direct Deployment Override

**Configuration:**
```yaml
splunk_app_deployment:
  apps:
    - name: "test_app"
      source: local
      path: "/opt/apps/test_app"
      deployment_target: "direct"
      target_roles:
        - universal_forwarder  # Usually goes via DS, but "direct" overrides
```

**Execution:**
```
1. All UFs calculate target:
   uf → deployment_target: "direct" override
   → Deploy directly to uf:/opt/splunkforwarder/etc/apps/

2. Bypasses:
   - Deployment Server
   - Serverclass configuration
   - Cluster distribution

3. Result:
   App appears immediately on uf without DS phone-home
```

## Configuration Reference


### Global Configuration

```yaml
# In config/splunk_config.yml
splunk_defaults:
  # Deployment Server (required for DS distribution)
  splunk_deployment_server:
    - ds  # Hostname of deployment server
  
  # Admin credentials (required for cluster operations)
  splunk_admin_password: "your_password"
```

### App Configuration Schema

```yaml
splunk_app_deployment:
  apps:
    - name: string                       # Required: App folder name
      source: splunkbase|local           # Required: Source type
      
      # Splunkbase specific:
      app_id: integer                    # Required for splunkbase
      version: string                    # Optional: default "latest"
      
      # Local app specific:
      path: string                       # Required for local: Absolute path to app folder
      
      # State management:
      state: installed|absent            # Optional: default "installed"
      
      # Targeting:
      target_roles: [string]             # Required: List of roles
                                         # Valid roles: universal_forwarder, heavy_forwarder,
                                         #              indexer, search_head, cluster_manager,
                                         #              deployer, deployment_server
      
      # Deployment control:
      deployment_target: auto|direct     # Optional: default "auto"
                                         # "direct" = force direct deployment, bypass DS/cluster
      
      # Deployment Server specific:
      deployment_whitelist: [string]|string  # Optional: Manual DS whitelist
                                             # Overrides auto-calculation from target_roles
      serverclass: string                    # Optional: Custom serverclass name
                                             # Default: "app_<app_name>"
```

### Complete Example

```yaml
# config/splunk_config.yml
splunk_defaults:
  splunk_deployment_server:
    - ds
  splunk_admin_password: "changeme"

splunk_app_deployment:
  apps:
    # Forwarder app - via Deployment Server
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "3.0.0"
      target_roles:
        - universal_forwarder
        - heavy_forwarder
    
    # Indexer app - via Cluster Manager
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      target_roles:
        - indexer
    
    # Remove from search heads
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      state: absent
      target_roles:
        - search_head
    
    # Windows app - via Deployment Server
    - name: "Splunk_TA_windows"
      source: splunkbase
      app_id: 742
      target_roles:
        - universal_forwarder
        - heavy_forwarder
    
    # Local app - via Cluster Manager
    - name: "custom_indexer_app"
      source: local
      path: "/opt/splunk_apps/custom_indexer_app"
      target_roles:
        - indexer
    
    # Search app - via Deployer
    - name: "custom_dashboard"
      source: local
      path: "/opt/splunk_apps/custom_dashboard"
      target_roles:
        - search_head
    
    # Direct deployment example
    - name: "test_app"
      source: local
      path: "/opt/splunk_apps/test_app"
      deployment_target: "direct"
      target_roles:
        - universal_forwarder
    
    # Manual whitelist example
    - name: "selective_app"
      source: local
      path: "/opt/splunk_apps/selective_app"
      deployment_whitelist:
        - uf1
        - uf2
      target_roles:
        - universal_forwarder  # Ignored for whitelist, only used for DS detection
```

## Best Practices

### 1. Use State Management for App Lifecycle

Instead of commenting out apps:

```yaml
# ❌ Bad: Commented out
#- name: "Splunk_TA_nix"
#  target_roles: [search_head]

# ✅ Good: Explicit removal
- name: "Splunk_TA_nix"
  state: absent
  target_roles: [search_head]
```

### 2. Separate Apps by Deployment Method

Group apps by their deployment pattern:

```yaml
apps:
  # Deployment Server apps
  - name: "forwarder_app_1"
    target_roles: [universal_forwarder]
  - name: "forwarder_app_2"
    target_roles: [universal_forwarder]
  
  # Indexer Cluster apps
  - name: "indexer_app_1"
    target_roles: [indexer]
  - name: "indexer_app_2"
    target_roles: [indexer]
  
  # Search Head Cluster apps
  - name: "search_app_1"
    target_roles: [search_head]
```

### 3. Use Multiple Entries for Role-Specific State

When an app has different states for different roles:

```yaml
# Install on forwarders and indexers
- name: "Splunk_TA_nix"
  target_roles:
    - universal_forwarder
    - indexer

# Remove from search heads
- name: "Splunk_TA_nix"
  state: absent
  target_roles:
    - search_head
```

### 4. Test with Direct Deployment First

When testing new apps:

```yaml
- name: "new_test_app"
  source: local
  path: "/opt/apps/new_test_app"
  deployment_target: "direct"  # Test directly first
  target_roles:
    - search_head
```

Then switch to automatic:

```yaml
- name: "new_test_app"
  source: local
  path: "/opt/apps/new_test_app"
  deployment_target: "auto"  # Or remove this line entirely
  target_roles:
    - search_head
```

### 5. Version Pin Production Apps

```yaml
# ❌ Risky: Always get latest
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833

# ✅ Safe: Pin to tested version
- name: "Splunk_TA_nix"
  source: splunkbase
  app_id: 833
  version: "3.0.0"
```

## Handler Reference

### Automatic Handler Triggering

Handlers are automatically triggered when app files change:

| Deployment Method | Handler | When Triggered |
|-------------------|---------|----------------|
| Deployment Server | `Reload deploy-server` | App added/removed from `deployment-apps/` |
| Indexer Cluster | `Apply indexer cluster bundle` | App added/removed from `manager-apps/` |
| Search Head Cluster | `Push shcluster bundle` | App added/removed from `shcluster/apps/` |
| Direct | `Restart Splunk` | App added/removed from `etc/apps/` |

### Handler Behavior

**Smart Notifications:**
- Only run if actual file changes detected
- Automatically delegate to correct host (CM/Deployer/DS)
- Use correct paths and credentials from inventory

**Cluster Bundle Handlers:**
```yaml
# Indexer Cluster - runs on Cluster Manager
Apply indexer cluster bundle:
  command: splunk apply cluster-bundle --answer-yes
  delegate_to: <cluster_manager_for_this_cluster>

# Search Head Cluster - runs on Deployer
Push shcluster bundle:
  command: splunk apply shcluster-bundle
  delegate_to: <deployer_for_this_cluster>
```

**Manual Handler Execution:**
```bash
# Force cluster bundle push
ansible-playbook ansible/deploy_splunk_apps.yml --tags splunk_apps --flush-handlers

# Or manually:
ssh cm
/opt/splunk/bin/splunk apply cluster-bundle -auth admin:password --answer-yes
```

## Recommendations


### For New Deployments

1. ✅ Configure inventory with proper cluster groups
2. ✅ Set `splunk_deployment_server` in `splunk_defaults`
3. ✅ Run full environment deployment (`site.yml`) to configure deployment clients
4. ✅ Define apps in `splunk_config.yml` with appropriate `target_roles`
5. ✅ Deploy apps with `deploy_splunk_apps.yml`

### For Clustered Environments

1. ✅ Ensure inventory plugin correctly populates cluster groups:
   - `idxcluster_<name>` for indexer clusters
   - `shcluster_<name>` for search head clusters
   - `role_cluster_manager` and `role_deployer`
2. ✅ Use `target_roles` to specify which role types get the app
3. ✅ System automatically routes to CM/Deployer for clustered hosts
4. ✅ Verify bundle pushes complete successfully

### For App Updates

1. ✅ Update `version` in config (for Splunkbase apps)
2. ✅ Run playbook - system detects version change
3. ✅ Handlers automatically triggered for changed apps only
4. ✅ Verify apps updated on endpoints

### For App Removal

1. ✅ Add entry with `state: absent` and `target_roles`
2. ✅ Run playbook
3. ✅ System removes from CM/Deployer/DS as appropriate
4. ✅ Handlers push removal to cluster members or DS clients
5. ✅ Verify apps removed from endpoints

## Quick Reference Commands

```bash
# Deploy all apps
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml

# Deploy specific app (use tags if implemented)
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml --limit <target_host>

# Verbose output for troubleshooting
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml -v

# Check inventory structure
ansible-inventory -i config/splunk_config.yml --graph

# List all hosts in a role
ansible-inventory -i config/splunk_config.yml --list | grep -A5 role_indexer

# Verify app on target
ansible <host> -i config/splunk_config.yml -m shell -a "ls -la /opt/splunk/etc/apps/"

# Check serverclass
ansible ds -i config/splunk_config.yml -m shell -a "cat /opt/splunk/etc/system/local/serverclass.conf"

# Check cluster bundle
ansible cm -i config/splunk_config.yml -m shell -a "/opt/splunk/bin/splunk show cluster-bundle-status -auth admin:password"

# Check SHC bundle
ansible deployer -i config/splunk_config.yml -m shell -a "/opt/splunk/bin/splunk show shcluster-status -auth admin:password"
```

## Advanced Topics

### Custom Serverclass Names

```yaml
- name: "Splunk_TA_nix"
  serverclass: "production_forwarders"  # Custom name
  target_roles:
    - universal_forwarder
```

**Generated serverclass:**
```ini
[serverClass:production_forwarders]
whitelist.0 = uf

[serverClass:production_forwarders:app:Splunk_TA_nix]
restartSplunkd = true
stateOnClient = enabled
```

### Multiple Clusters

The system supports multiple clusters automatically:

```yaml
# Inventory structure:
groups:
  idxcluster_prod: [prod-idx1, prod-idx2]
  idxcluster_dev: [dev-idx1, dev-idx2]
  role_cluster_manager: [prod-cm, dev-cm]
```

**App deployment:**
```yaml
- name: "Splunk_TA_nix"
  target_roles:
    - indexer  # Deploys to both prod-cm and dev-cm
```

**How it works:**
- `prod-idx1` calculates target → finds `prod-cm` (in `idxcluster_prod` + `role_cluster_manager`)
- `dev-idx1` calculates target → finds `dev-cm` (in `idxcluster_dev` + `role_cluster_manager`)
- Deduplication ensures one deployment per cluster manager

### Selective App Distribution

**Manual control over which deployment clients get apps:**

```yaml
- name: "special_app"
  source: local
  path: "/opt/apps/special_app"
  deployment_whitelist:
    - uf1
    - uf2
    - hf1
  target_roles:
    - universal_forwarder  # Only used to identify this as DS distribution
    - heavy_forwarder
```

**Result:**
- App deployed to DS
- Serverclass whitelist: `[uf1, uf2, hf1]` only
- Other UFs/HFs don't receive the app

### Combining States and Roles

**Complex example:**

```yaml
apps:
  # Production forwarders - specific version
  - name: "Splunk_TA_nix"
    source: splunkbase
    app_id: 833
    version: "3.0.0"
    deployment_whitelist: [prod-uf1, prod-uf2]
    target_roles: [universal_forwarder]
  
  # Dev forwarders - latest version
  - name: "Splunk_TA_nix"
    source: splunkbase
    app_id: 833
    deployment_whitelist: [dev-uf1, dev-uf2]
    target_roles: [universal_forwarder]
  
  # Indexers - install
  - name: "Splunk_TA_nix"
    source: splunkbase
    app_id: 833
    target_roles: [indexer]
  
  # Search heads - remove
  - name: "Splunk_TA_nix"
    source: splunkbase
    app_id: 833
    state: absent
    target_roles: [search_head]
```

## Migration Guide

### From Direct Deployment to Deployment Server

**Before (direct):**
```yaml
- name: "Splunk_TA_nix"
  deployment_target: "direct"
  target_roles: [universal_forwarder]
```

**After (via DS):**

1. Configure deployment clients on forwarders
2. Update config:
```yaml
- name: "Splunk_TA_nix"
  deployment_target: "auto"  # Or remove this line
  target_roles: [universal_forwarder]
```

3. Remove old app from forwarders:
```bash
# On each UF
rm -rf /opt/splunkforwarder/etc/apps/Splunk_TA_nix
```

4. Deploy via DS - app will be pushed to clients

### From Standalone to Clustered

**Before (standalone indexers):**
```yaml
- name: "indexer_app"
  target_roles: [indexer]
  # Deployed directly to each indexer
```

**After (clustered):**

1. Create indexer cluster (outside scope of this doc)
2. Ensure inventory plugin populates `idxcluster_*` groups
3. Same config works automatically:
```yaml
- name: "indexer_app"
  target_roles: [indexer]
  # Now automatically routed to Cluster Manager
```

4. Old apps on indexers will be overwritten by cluster bundle

## Summary

This deployment system provides:

✅ **Automatic routing** based on host roles and cluster membership
✅ **Smart state management** with explicit install/remove
✅ **Multi-cluster support** with automatic cluster detection
✅ **Flexible targeting** via roles or manual whitelists
✅ **Change detection** with conditional handler triggering
✅ **Comprehensive debugging** with verbose output options

**Key takeaways:**
- Define apps once with `target_roles`
- System automatically determines deployment method
- Clustered hosts automatically use CM/Deployer
- Non-clustered deployment clients use DS
- Direct deployment available as override
- Multiple entries support complex state requirements
