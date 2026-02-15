# App Deployment – Removing Apps

**Playbook**: `ansible/remove_splunk_apps.yml`  
**Purpose**: Safely remove Splunk apps from your environment

## Overview

The remove apps playbook processes apps marked with `state: absent` in your configuration file:
- Reads configuration from `config/splunk_config.yml`
- Finds apps with `state: absent`
- Automatic backup before deletion
- Removes app directories
- Restarts Splunk to apply changes

## Usage

### Basic Usage

1. **Mark apps for removal** in `config/splunk_config.yml`:

```yaml
splunk_app_deployment:
  apps:
    - name: "app_to_remove"
      source: splunkbase
      app_id: 123
      state: absent  # Mark for removal
      target_roles:
        - search_head
        - indexer
```

2. **Run the removal playbook**:

```bash
ansible-playbook ansible/remove_splunk_apps.yml \
  -i config/splunk_config.yml
```

The playbook will:
- Find all apps with `state: absent`
- Show which apps will be removed
- Process each app according to its `target_roles`
- Backup each app before removal
- Remove app directories
- Restart Splunk

### Example: Remove Single App

**Configuration** (`config/splunk_config.yml`):
```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      state: absent  # Remove this app
      target_roles:
        - indexer
```

**Run removal**:
```bash
$ ansible-playbook ansible/remove_splunk_apps.yml -i config/splunk_config.yml

PLAY [Remove Splunk Apps from Environment] ***********************

TASK [Filter apps with state=absent] ****************************
ok: [indexer1]

TASK [Display apps marked for removal] **************************
ok: [indexer1] => {
    "msg": "Found 1 app(s) marked for removal (state: absent):\n- Splunk_TA_nix (target_roles: indexer)\n"
}

TASK [apps_cluster_manager : Remove Splunk_TA_nix] *************
changed: [cm1]

TASK [Restart Splunk] *******************************************
changed: [indexer1]

PLAY RECAP ******************************************************
cm1                        : ok=4    changed=2
```

### Example: Remove Multiple Apps

**Configuration**:
```yaml
splunk_app_deployment:
  apps:
    - name: "old_app_v1"
      source: local
      path: "old_app_v1"
      state: absent
      target_roles:
        - search_head
    
    - name: "deprecated_ta"
      source: splunkbase
      app_id: 999
      state: absent
      target_roles:
        - indexer
    
    - name: "test_app"
      source: local
      path: "test_app"
      state: absent
      target_roles:
        - search_head
        - indexer
```

**Run removal**:
```bash
ansible-playbook ansible/remove_splunk_apps.yml -i config/splunk_config.yml
```

All three apps will be removed in a single run.

## What the Playbook Does

### 1. Configuration Discovery

**Finds apps marked for removal**:
- Reads `splunk_app_deployment` section from config
- Filters apps where `state: absent`
- Shows list of apps to be removed

Example output:
```
Found 3 app(s) marked for removal (state: absent):
- old_app_v1 (target_roles: search_head)
- deprecated_ta (target_roles: indexer)
- test_app (target_roles: search_head, indexer)
```

### 2. Role-Based Processing

**Processes apps by target_roles**:
- Only removes app on hosts matching `target_roles`
- Calculates correct target location (cluster-aware)
- Same logic as installation (cluster manager, deployer, etc.)

### 3. Backup

**Creates backup before removal**:
```
Source: /opt/splunk/etc/apps/Splunk_TA_nix/
Destination: /opt/splunk/var/backup/apps/Splunk_TA_nix_2025-02-03_removed/
```

**Backup naming**:
- `{app_name}_{YYYY-MM-DD}_removed`
- Timestamp is date (YYYY-MM-DD)
- Marked with `_removed` suffix

### 4. Removal

**Removes app directory**:
```
rm -rf /opt/splunk/etc/apps/Splunk_TA_nix
```

Uses Ansible's `file` module with `state: absent` for safe deletion.

### 5. Restart

**Restarts Splunk**:
- Applies the app removal
- Clears app from Splunk's app registry
- Only runs if `use_systemctl == true`

## Target Locations

The playbook automatically calculates target locations based on your Splunk topology:

### Standard Apps (`etc/apps`)
```
App location: Standalone instances, search heads, indexers
Target location: etc/apps
Distribution: Installed locally on each host
```

### Cluster Manager Apps (`etc/manager-apps`)
```
App location: Indexer Cluster Manager
Target location: etc/manager-apps
Distribution: Pushed to indexers via cluster bundle
Note: After removal, push bundle to apply to indexers
```

### Search Head Cluster Apps (`etc/shcluster/apps`)
```
App location: Search Head Deployer
Target location: etc/shcluster/apps
Distribution: Deployed to search head cluster members
Note: After removal, push bundle to apply to SHC
```

### Deployment Server Apps (`etc/deployment-apps`)
```
App location: Deployment Server
Target location: etc/deployment-apps
Distribution: Deployed to deployment clients
Note: After removal, clients will update on next check-in
```

## Safety Features

### 1. Configuration-Based
- Apps explicitly marked with `state: absent`
- No accidental removals from typos in prompts
- Full audit trail in Git when using version control

### 2. Existence Check
- Verifies app exists before attempting removal
- Skips gracefully if app not found (idempotent)
- Won't fail entire run if one app missing

### 3. Automatic Backup
- Always backs up app before deletion
- Stored in `/var/backup/apps/`
- Can be restored if removal was mistake

### 4. Timestamped Backups
- Date-based timestamp (YYYY-MM-DD)
- Can identify when app was removed
- Helpful for auditing and troubleshooting

### 5. Role-Based Removal
- Only removes from hosts with matching `target_roles`
- Respects cluster topology (cluster manager, deployer, etc.)
- Same intelligent routing as installation

## Important Notes

### Cluster Environments

**Indexer Clusters**:
After removing app from Cluster Manager (`etc/manager-apps`), you must push the cluster bundle:

```bash
# On Cluster Manager
/opt/splunk/bin/splunk apply cluster-bundle --answer-yes

# Or via API
curl -k -u admin:password https://cm:8089/services/cluster/master/control/default/apply \
  -d bundle_id=<bundle_id>
```

**Search Head Clusters**:
After removing app from Deployer (`etc/shcluster/apps`), you must deploy to SHC:

```bash
# On Deployer
/opt/splunk/bin/splunk apply shcluster-bundle \
  -target https://shc-member:8089 \
  -auth admin:password

# Or use Deployer playbook
ansible-playbook ansible/shcluster_deployer.yml -i config/splunk_config.yml
```

**Deployment Server**:
After removing app from Deployment Server (`etc/deployment-apps`), clients will update on their next check-in (default 60 seconds).

### Premium apps (ITSI)

Removal of **Splunk IT Service Intelligence (ITSI)** is done per role (Cluster Manager, License Manager, Deployer, Search Head). The list of app directories to remove is **built from the archive** (the playbook lists the archive contents). The archive must be present and listable (e.g. `tar tzf`); if it cannot be obtained, removal fails. There is no fallback app list. See the [App Deployment Guide](App_Deployment_Guide.md#premium-packs-splunk-it-service-intelligence-itsi) for ITSI config options and `itsi_sh_name` / `itsi_shc_name` targeting.

### App Dependencies

**Check for dependencies** before removing:
- Other apps may depend on the app being removed
- Especially common with Technology Add-ons (TAs)
- Example: Enterprise Security depends on many TAs

**Common dependent apps**:
- Splunk Enterprise Security (depends on many TAs)
- ITSI (depends on SA-ITOA, etc.)
- Premium apps (depend on supporting TAs)

### Configuration Files

**App removal includes**:
- All app files and directories
- Saved searches, dashboards, views
- Local configuration files
- Lookup files

**Not removed**:
- Index data (remains in indexes)
- Indexed data referencing the app
- User permissions related to the app (may need manual cleanup)

## Backup Restoration

If you need to restore a removed app:

### 1. Find the Backup

```bash
ls -la /opt/splunk/var/backup/apps/*_removed/

# Example output:
drwxr-xr-x  5 splunk splunk  160 Feb  3 14:23 Splunk_TA_nix_1738598400_removed/
```

### 2. Restore from Backup

```bash
# Copy backup back to apps directory
cp -r /opt/splunk/var/backup/apps/Splunk_TA_nix_2025-02-03_removed \
      /opt/splunk/etc/apps/Splunk_TA_nix

# Fix ownership
chown -R splunk:splunk /opt/splunk/etc/apps/Splunk_TA_nix

# Restart Splunk
systemctl restart Splunkd
```

### 3. Verify Restoration

```bash
# Check app is visible
/opt/splunk/bin/splunk display app Splunk_TA_nix

# Check app status via REST API
curl -k -u admin:password https://localhost:8089/services/apps/local/Splunk_TA_nix
```

## Troubleshooting

### No Apps Marked for Removal

```
Error: No apps marked for removal (state: absent) found in configuration.
```

**Solution**:
Add apps with `state: absent` to your `config/splunk_config.yml`:

```yaml
splunk_app_deployment:
  apps:
    - name: "app_to_remove"
      source: splunkbase
      app_id: 123
      state: absent  # Mark for removal
      target_roles: [search_head]
```

### App Not Removed

**Check 1: State field set correctly**
```yaml
apps:
  - name: "app"
    state: absent  # Must be "absent" not "remove" or "deleted"
```

**Check 2: Target roles match host**
```yaml
apps:
  - name: "app"
    state: absent
    target_roles: [search_head]  # Host must have this role
```

**Check 3: App exists on calculated target host**
- App may be on cluster manager, not individual hosts
- Check playbook output for "Target Host: ..."

### App Not Found

```
Error: App Splunk_TA_nix not found at /opt/splunk/etc/apps/Splunk_TA_nix
```

**This is normal and expected** - the playbook is idempotent:
- If app doesn't exist, it's already in desired state (absent)
- Playbook will skip gracefully
- No error, just informational message

### Permission Denied

```
Error: Permission denied
```

**Solutions**:
1. Ensure playbook runs with `become: true` (it does by default)
2. Check SSH user has sudo access
3. Verify file permissions: `ls -la /opt/splunk/etc/apps/`

### Backup Failed

```
Error: Failed to create backup
```

**Solutions**:
1. Check disk space: `df -h /opt/splunk/var/backup/`
2. Ensure backup directory exists and is writable
3. Check ownership: `ls -la /opt/splunk/var/backup/apps/`

### Splunk Restart Failed

```
Error: Failed to restart Splunk
```

**Solutions**:
1. Check Splunk service status: `systemctl status Splunkd`
2. Review Splunk logs: `/opt/splunk/var/log/splunk/splunkd.log`
3. May need manual restart: `systemctl restart Splunkd`

## Best Practices

### 1. Review Before Removal ✅
- Verify app name and location
- Check for dependencies
- Review app's purpose and usage

### 2. Backup Verification ✅
- Verify backup was created successfully
- Check backup size matches original
- Test backup can be restored (in test environment)

### 3. Off-Hours Removal ✅
- Remove apps during maintenance windows
- Minimize impact on users
- Allow time for troubleshooting if needed

### 4. Documentation ✅
- Document why app was removed
- Note removal date and who performed it
- Update app inventory

### 5. Cluster Considerations ✅
- Remove from cluster manager/deployer, not individual nodes
- Push bundle after removal
- Verify removal on all cluster members

### 6. Test First ✅
- Test removal in dev/test environment
- Verify no functionality breaks
- Confirm app can be restored if needed

## Alternative: Use deploy_splunk_apps.yml

You can also use the main deployment playbook for removals:

```bash
# Mark apps with state: absent in config
# Then run the deployment playbook
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
```

**When to use each playbook**:

| Playbook | Use When |
|----------|----------|
| `remove_splunk_apps.yml` | Focus only on removals, see what will be removed |
| `deploy_splunk_apps.yml` | Mixed operations (install and remove together) |

Both playbooks:
- ✅ Read from same config file
- ✅ Use same removal logic
- ✅ Automatic backup before removal
- ✅ Idempotent operations
- ✅ Cluster-aware routing

## See Also

- **Deploy Apps**: `ansible/deploy_splunk_apps.yml`
- **App Deployment Guide**: [App_Deployment_Guide.md](App_Deployment_Guide.md)
- **Target Logic**: [App_Deployment_Target_Logic.md](App_Deployment_Target_Logic.md)

---

*Safe app removal with automatic backup; uses apps_deployment_server, apps_cluster_manager, apps_deployer, and apps_direct roles.*
