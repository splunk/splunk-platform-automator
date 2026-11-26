# Verification Playbooks

This directory contains playbooks to verify the state of your Splunk deployment.

**Inventory:** `spa run` uses the env inventory. Extra Ansible args go after `--`. Do not pass `-i` unless overriding that inventory.

## Available Verification Playbooks

### 1. `verify_app_deployment.yml`

Verifies that Splunk apps are deployed correctly according to the configuration in `config/splunk_config.yml`. Performs the same version checks as `splunk_apps_deploy.yml`.

**What it checks:**
- ✅ Apps that should be installed are present
- ✅ Apps that should be absent are not present
- ✅ Apps are in the correct directories:
  - `etc/deployment-apps/` (Deployment Server)
  - `etc/manager-apps/` (Cluster Manager)
  - `etc/shcluster/apps/` (Deployer)
  - `etc/apps/` (Direct deployment)
- ✅ Version drift detection (Splunkbase API and local source comparison)
- ✅ ITSI premium app: verifies role-specific on-disk folders (`SA-IndexCreation` on CM, license/access apps on LM, full ITSI bundle on deployer/SH)
- ✅ ITSI content packs on deployer: verifies configured `content_pack_apps` folders (same as direct)
- ⚠️ Warns about unexpected apps (present but not in config)

**Prerequisites for version checks:**
- Splunkbase apps require credentials (`SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD` env vars or configured in `splunk_config.yml`). If not set, version checks for Splunkbase apps are skipped with a warning.
- Local apps require the source directory to be available on the controller.

**Usage:**

```bash
# Report mode (default): Shows mismatches but doesn't fail
spa run verification/verify_app_deployment

# Strict mode: Fails if any mismatches found (for CI/CD)
spa run verification/verify_app_deployment -- -e fail_on_mismatch=true
```

**Example Combined Summary Output:**

```
==================================================
  APP DEPLOYMENT VERIFICATION SUMMARY
==================================================

Total issues: 2
  Presence errors (MISSING/UNEXPECTED): 0
  Version drift:                        2
  Other warnings:                       0

--- VERSION DRIFT (update would be applied by deploy) ---
  [Direct/itsi]  ITSI: VERSION DRIFT: installed='5.0.0', expected='5.0.1 (latest)'
  [Direct/uf]  Splunk_TA_nix: VERSION DRIFT: installed='10.3.2', expected='10.3.3'

==================================================
Run with -e fail_on_mismatch=true to fail on issues
==================================================
```

**All clear:**

```
==================================================
  APP DEPLOYMENT VERIFICATION SUMMARY
==================================================

Total issues: 0
  Presence errors (MISSING/UNEXPECTED): 0
  Version drift:                        0
  Other warnings:                       0

All apps deployed correctly and versions match.

==================================================
Run with -e fail_on_mismatch=true to fail on issues
==================================================
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
spa run verification/debug_app_scope

# Custom output path
spa run verification/debug_app_scope -- -e scope_output_path=./my_scope.json

# No SSH: run scope logic on the controller (hostnames like ds/sh/idx do not need to resolve)
spa run verification/debug_app_scope -- -e run_scope_locally=true

# Same + assert scope invariants (state=absent apps must have on_scope true so removal runs)
spa run verification/debug_app_scope -- -e assert_scope_invariants=true
```

**Using debug mode in the main deploy playbook:**

You can also run the full deploy with scope debugging (still no install/remove for the direct role when the flag is set):

```bash
spa run splunk_apps_deploy --yes -- -e debug_app_scope=true
```

This runs the direct role in “scope only” mode (`scope_debug_results` is set per host; no role debug dump—use `debug_app_scope.yml` or the JSON output file to inspect scope); deployer and other steps still run as usual.

**Regression testing after ITSI/content pack changes:**

1. Run scope debug and assert invariants:
   ```bash
   spa run verification/debug_app_scope -- -e assert_scope_invariants=true
   ```
2. Run full verification after a real deploy:
   ```bash
   spa run verification/verify_app_deployment -- -e fail_on_mismatch=true
   ```
3. Inspect `ansible/verification/output/scope_debug.json` to confirm normal apps and ITSI/content pack apps have the expected `on_scope`, `base_hosts`, and `filtered_hosts` per host.

**Scenario-based scope tests (no SSH):**

Multiple scenario configs under `tests/configs/app_scope/<name>/splunk_config.yml` exercise different topologies and app/filter combinations. Each scenario is run with `spa run verification/debug_app_scope -- -e run_scope_locally=true` against a temp env and the output is asserted in pytest.

- **Run all scope scenarios:** From project root, `./tests/run_app_scope_scenarios_tests.sh` (or `pytest tests/test_app_scope_scenarios.py -v`).
- **Add a scenario:** Create `tests/configs/app_scope/<scenario_name>/splunk_config.yml` with a full splunk_config (plugin, splunk_hosts, splunk_app_deployment, and optionally splunk_shclusters/splunk_idxclusters). Add scenario-specific assertions in `tests/test_app_scope_scenarios.py` in `test_scenario_scope_assertions`.
- **Output:** Scope JSON per scenario is written to `tests/configs/app_scope/output/<scenario_name>_scope.json` when tests run.

### 3. `ping_hosts.yml`

Verifies basic connectivity to all hosts.

**Usage:**
```bash
spa run verification/ping_hosts
```

### 4. `verify_data_flow.yml`

Verifies data is flowing into Splunk indexes.

**Usage:**
```bash
spa run verification/verify_data_flow
```

### 5. `check_idxc_health.yml`

Checks Indexer Cluster health and replication status.

**Usage:**
```bash
spa run verification/check_idxc_health
```

### 6. `check_shc_health.yml`

Checks Search Head Cluster health and member status.

**Usage:**
```bash
spa run verification/check_shc_health
```

### 7. `verify_hec.yml`

Posts one unique event per enabled HEC token on the first host of each `hec:` identity and searches until that event is in the token's index. Mutating: requires `--yes`. When no inventory host has `hec:`, the playbook ends with exit 0.

**Usage:**
```bash
spa run verification/verify_hec --yes
```

### 8. `verify_es.yml`

Read-only health checks for an installed `premium_app: es` entry after install, on a running lab, and after upgrade (`spa run verification/verify_es`). Disk layout stays `verify_app_deployment.yml`; this playbook uses REST to confirm `| essinstall` actually worked. A `version: latest` row is compared to the **deployed** ES version (from `spa_es_indexes`, then the suite), not live Splunkbase latest.

When no installed ES app exists, it prints one info line and exits 0.

**What it checks:**
- Installer finished: `SplunkEnterpriseSecuritySuite` present, enabled, and at the expected version on the ES search head and every SHC member. `essinstaller2.log` is checked on the host that ran `| essinstall` (standalone search head, or the SHC deployer) for ERROR lines since SPA's last essinstall stamp; SHC members report `log=N/A (SHC member)`. Missing stamp or unparseable log timestamps fall back to the whole current file (`scope=whole_file`)
- Suite apps enabled: SA-* and DA-* apps from the ES archive exist under their installed folder names (not versioned nested `.spl` stems) and are not disabled, except `SA-UEBA` which Splunk ships disabled until UBA integration; SHC members report the same ES version
- KV store ready on the ES search head or members
- ES indexes (from `spa_es_indexes` stanza names) exist on every indexer search peer
- Splunk Web SSL matches the effective `ssl_enablement` (`strict` needs SSL on; `ignore` is expected in HTTP labs)
- ES license on the license manager: **present / absent** only (never prints license content)
- SHC upload limits: `max_content_length` on the deployer and every member is at least 5000000000 (members use `etc/system/local/server.conf` because a bundle-delivered `[httpServer]` setting does not take effect). Standalone (no SHC) reports N/A
- Enabled ES correlation-search count (informational; never a failure)
- `suite_configured`: `configured` is true on the standalone ES search head after essinstall. SHC members report `N/A (SHC member)`
- Index volume overlay on indexer **peers** (not the CM): `homePath` / `coldPath` for archive indexes that contained a `/` start with `es_index_home_path` / `es_index_cold_path` (default `volume:<splunk_volume_defaults.homePath|coldPath>`, fallback `volume:primary`)
- `/services/messages` titles that mention ES / essinstall / restart required (informational; never a failure)
- Splunkbase has a newer ES release than the deployed version when the row is `latest` (informational metadata lookup; never a failure)

**Usage:**

```bash
# Report mode (default): shows mismatches but does not fail
spa run verification/verify_es

# Strict mode: fails if checks 1-7, 9, 10 mismatch (8, 11, 12 stay informational)
spa run verification/verify_es -- -e fail_on_mismatch=true
```

Live pytest (`tests/test_verification.py` `test_08_verify_es`) skips when the lab config has no installed `premium_app: es`.

## Integration with Tests

The verification playbooks are integrated into the pytest suite in `tests/test_deployment.py`:

```python
# After data flow; playbook skips when no host has hec:
def test_09_verify_hec(self, topology_id):
    result = self._run_spa(["run", "verification/verify_hec", "--yes"])
    assert result.returncode == 0

# Runs after app deployment
def test_10_verify_app_deployment(self, topology_id):
    result = self._run_spa(
        ["run", "verification/verify_app_deployment"],
        extra=["-e", "fail_on_mismatch=true"],
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
  spa run verification/debug_app_scope -- -e run_scope_locally=true -e assert_scope_invariants=true
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
spa run splunk_apps_deploy --yes
```

### Verification shows "VERSION DRIFT"

**Meaning:** The app is installed but the version differs from what the source (Splunkbase or local repo) provides.

**Solution:**
```bash
# Re-run deployment to update apps
spa run splunk_apps_deploy --yes
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
   spa run splunk_apps_deploy --yes
   spa run verification/verify_app_deployment
   ```

2. **Use strict mode in CI/CD pipelines:**
   ```bash
   spa run verification/verify_app_deployment -- -e fail_on_mismatch=true
   ```

3. **Run in report mode for manual checks:**
   ```bash
   spa run verification/verify_app_deployment
   ```

4. **Check specific hosts:**
   ```bash
   spa run verification/verify_app_deployment -- --limit ds,cm
   ```

## Exit Codes

- **0:** Verification passed (or report mode with mismatches)
- **Non-zero:** Verification failed (strict mode with mismatches)
