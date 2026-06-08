# Verification Playbooks

This directory contains playbooks to verify the state of your Splunk deployment.

**Inventory:** Playbooks use the inventory configured in the framework (`ansible.cfg`). Run from the project root; do not pass `-i` unless overriding the default inventory.

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
ansible-playbook ansible/verification/verify_app_deployment.yml

# Strict mode: Fails if any mismatches found (for CI/CD)
ansible-playbook ansible/verification/verify_app_deployment.yml -e fail_on_mismatch=true
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

### 2. `debug_app_scope.yml` – Debug and test app/ITSI scope (no install/remove)

Computes **direct deployment scope only** (no install or remove) and dumps per-host, per-app results so you can see why an app is or isn’t in scope. Use this to debug ITSI/content pack vs normal app behavior and to avoid breaking normal apps when changing ITSI logic.

**What it does:**
- Runs the same eligibility and filter logic as real deployment
- For each host and each app, records: `app`, `state`, `in_base`, `in_filtered`, `on_scope`, `base_hosts`, `filtered_hosts`
- Writes results to `ansible/verification/output/scope_debug.json` (or `scope_output_path` if set)
- **Does not** install or remove anything

**Usage:**

```bash
# Dump scope to default file (ansible/verification/output/scope_debug.json)
ansible-playbook ansible/verification/debug_app_scope.yml

# Custom output path
ansible-playbook ansible/verification/debug_app_scope.yml \
  -e scope_output_path=./my_scope.json

# No SSH: run scope logic on the controller (hostnames like ds/sh/idx do not need to resolve)
ansible-playbook ansible/verification/debug_app_scope.yml \
  -e run_scope_locally=true

# Same + assert scope invariants (state=absent apps must have on_scope true so removal runs)
ansible-playbook ansible/verification/debug_app_scope.yml \
  -e assert_scope_invariants=true
```

**Using debug mode in the main deploy playbook:**

You can also run the full deploy with scope debugging (still no install/remove for the direct role when the flag is set):

```bash
ansible-playbook ansible/deploy_splunk_apps.yml -e debug_app_scope=true
```

This runs the direct role in “scope only” mode (`scope_debug_results` is set per host; no role debug dump—use `debug_app_scope.yml` or the JSON output file to inspect scope); deployer and other steps still run as usual.

**Regression testing after ITSI/content pack changes:**

1. Run scope debug and assert invariants:
   ```bash
   ansible-playbook ansible/verification/debug_app_scope.yml \
     -e assert_scope_invariants=true
   ```
2. Run full verification after a real deploy:
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml -e fail_on_mismatch=true
   ```
3. Inspect `ansible/verification/output/scope_debug.json` to confirm normal apps and ITSI/content pack apps have the expected `on_scope`, `base_hosts`, and `filtered_hosts` per host.

**Scenario-based scope tests (no SSH):**

Multiple scenario configs under `tests/configs/app_scope/<name>/splunk_config.yml` exercise different topologies and app/filter combinations. Each scenario is run with `debug_app_scope.yml -i <scenario_config> -e run_scope_locally=true` and the output is asserted in pytest.

- **Run all scope scenarios:** From project root, `pytest tests/test_app_scope_scenarios.py -v` (requires `ansible-playbook` on PATH and project defaults for inventory).
- **Add a scenario:** Create `tests/configs/app_scope/<scenario_name>/splunk_config.yml` with a full splunk_config (plugin, splunk_hosts, splunk_app_deployment, and optionally splunk_shclusters/splunk_idxclusters). Add scenario-specific assertions in `tests/test_app_scope_scenarios.py` in `test_scenario_scope_assertions`.
- **Output:** Scope JSON per scenario is written to `tests/configs/app_scope/output/<scenario_name>_scope.json` when tests run.

### 3. `ping_hosts.yml`

Verifies basic connectivity to all hosts.

**Usage:**
```bash
ansible-playbook ansible/verification/ping_hosts.yml
```

### 4. `verify_data_flow.yml`

Verifies data is flowing into Splunk indexes.

**Usage:**
```bash
ansible-playbook ansible/verification/verify_data_flow.yml
```

### 5. `check_idxc_health.yml`

Checks Indexer Cluster health and replication status.

**Usage:**
```bash
ansible-playbook ansible/verification/check_idxc_health.yml
```

### 6. `check_shc_health.yml`

Checks Search Head Cluster health and member status.

**Usage:**
```bash
ansible-playbook ansible/verification/check_shc_health.yml
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

### "Could not resolve hostname ds" (or sh, idx, etc.)

`verify_app_deployment.yml` (and other verification playbooks that run tasks on remote hosts) need SSH. Inventory hostnames like `ds`, `sh`, `idx` must resolve and be reachable.

- **From your machine:** Add those hostnames to `/etc/hosts` or your DNS so they point to the real hosts (Vagrant IPs, EC2 IPs, etc.), or run Ansible from an environment where they already resolve (e.g. bastion, Vagrant shell).
- **Scope-only check without SSH:** To test app/ITSI scope logic without any SSH, use the scope debug playbook in local mode:
  ```bash
  ansible-playbook ansible/verification/debug_app_scope.yml -e run_scope_locally=true -e assert_scope_invariants=true
  ```
  This runs all scope computation on the controller and writes the report (and optionally asserts invariants); no hostname resolution or SSH is required.

### Verification shows "MISSING" apps

**Possible causes:**
1. App deployment failed (check deployment playbook output)
2. App was removed manually
3. Configuration changed after deployment

**Solution:**
```bash
# Re-run deployment
ansible-playbook ansible/deploy_splunk_apps.yml
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
   ansible-playbook ansible/deploy_splunk_apps.yml
   ansible-playbook ansible/verification/verify_app_deployment.yml
   ```

2. **Use strict mode in CI/CD pipelines:**
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml -e fail_on_mismatch=true
   ```

3. **Run in report mode for manual checks:**
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml
   ```

4. **Check specific hosts:**
   ```bash
   ansible-playbook ansible/verification/verify_app_deployment.yml --limit ds,cm
   ```

## Exit Codes

- **0:** Verification passed (or report mode with mismatches)
- **Non-zero:** Verification failed (strict mode with mismatches)
