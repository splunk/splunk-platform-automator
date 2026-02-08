# Verification Playbooks

This directory contains playbooks to verify the state of your Splunk deployment.

## Available Verification Playbooks

### 1. `verify_app_deployment.yml`

Verifies that Splunk apps are deployed correctly according to the configuration in `config/splunk_config.yml`.

**What it checks:**
- ✅ Apps that should be installed are present
- ✅ Apps that should be absent are not present
- ✅ Apps are in the correct directories:
  - `etc/deployment-apps/` (Deployment Server)
  - `etc/manager-apps/` (Cluster Manager)
  - `etc/shcluster/apps/` (Deployer)
  - `etc/apps/` (Direct deployment)
- ⚠️ Warns about unexpected apps (present but not in config)

**Usage:**

```bash
# Report mode (default): Shows mismatches but doesn't fail
ansible-playbook ansible/verification/verify_app_deployment.yml \
  -i config/splunk_config.yml

# Strict mode: Fails if any mismatches found (for CI/CD)
ansible-playbook ansible/verification/verify_app_deployment.yml \
  -i config/splunk_config.yml \
  -e fail_on_mismatch=true
```

**Example Output:**

```
DEPLOYMENT SERVER VERIFICATION: ds
=========================================
Expected apps: Splunk_TA_nix, Splunk_TA_windows
Found apps: Splunk_TA_nix, Splunk_TA_windows
Mismatches: 0
  ✓ All apps deployed correctly
=========================================
```

**With Mismatches:**

```
CLUSTER MANAGER VERIFICATION: cm
=========================================
Expected apps: Splunk_TA_nix
Found apps: Splunk_TA_windows
Mismatches: 2
Issues found:
  - Splunk_TA_nix: MISSING: App should be installed but not found
  - Splunk_TA_windows: UNEXPECTED: App should be absent but is installed
=========================================
```

### 2. `ping_hosts.yml`

Verifies basic connectivity to all hosts.

**Usage:**
```bash
ansible-playbook ansible/verification/ping_hosts.yml -i config/splunk_config.yml
```

### 3. `verify_data_flow.yml`

Verifies data is flowing into Splunk indexes.

**Usage:**
```bash
ansible-playbook ansible/verification/verify_data_flow.yml -i config/splunk_config.yml
```

### 4. `check_idxc_health.yml`

Checks Indexer Cluster health and replication status.

**Usage:**
```bash
ansible-playbook ansible/verification/check_idxc_health.yml -i config/splunk_config.yml
```

### 5. `check_shc_health.yml`

Checks Search Head Cluster health and member status.

**Usage:**
```bash
ansible-playbook ansible/verification/check_shc_health.yml -i config/splunk_config.yml
```

## Integration with Tests

The verification playbooks are integrated into the pytest suite in `tests/test_deployment.py`:

```python
# Runs after app deployment
def test_15_verify_app_deployment(self, config_file):
    result = self._run_playbook(
        "ansible/verification/verify_app_deployment.yml",
        ["-e", "fail_on_mismatch=true"]  # Strict mode for CI/CD
    )
    assert result.returncode == 0
```

## Configuration Variables

### `fail_on_mismatch`

Controls whether verification playbooks fail on mismatches.

- **Default:** `false` (report mode - shows issues but doesn't fail)
- **CI/CD:** `true` (strict mode - fails on any mismatch)

**Setting via command line:**
```bash
-e fail_on_mismatch=true
```

**Setting in playbook:**
```yaml
- hosts: all
  vars:
    fail_on_mismatch: true
  tasks:
    - include_role:
        name: apps_direct
        tasks_from: verify.yml
```

## Troubleshooting

### Verification shows "MISSING" apps

**Possible causes:**
1. App deployment failed (check deployment playbook output)
2. App was removed manually
3. Configuration changed after deployment

**Solution:**
```bash
# Re-run deployment
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
```

### Verification shows "UNEXPECTED" apps

**Possible causes:**
1. Apps were installed manually
2. Apps remain from previous configuration
3. Configuration removed app but it wasn't cleaned up

**Solution:**
```bash
# Option 1: Add app to config
# Edit config/splunk_config.yml to include the app

# Option 2: Remove app manually
# SSH to server and remove from appropriate directory

# Option 3: Set app state to 'absent' in config and redeploy
```

### Verification skipped for a role

If you see "Skipping verification on [host] (no apps expected)", this means:
- The host's role doesn't match any app's `target_roles`
- OR the deployment method doesn't apply to this host (e.g., clustered indexers get apps from cluster manager, not direct)

This is normal and expected behavior.

## Best Practices

1. **Run verification after every deployment:**
   ```bash
   ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
   ansible-playbook ansible/verification/verify_app_deployment.yml -i config/splunk_config.yml
   ```

2. **Use strict mode in CI/CD pipelines:**
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml \
     -i config/splunk_config.yml \
     -e fail_on_mismatch=true
   ```

3. **Run in report mode for manual checks:**
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml \
     -i config/splunk_config.yml
   ```

4. **Check specific hosts:**
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml \
     -i config/splunk_config.yml \
     --limit ds,cm
   ```

## Exit Codes

- **0:** Verification passed (or report mode with mismatches)
- **Non-zero:** Verification failed (strict mode with mismatches)
