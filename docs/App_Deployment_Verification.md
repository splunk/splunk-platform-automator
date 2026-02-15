# App Deployment Verification

## Overview

The verification system ensures that Splunk apps defined in `config/splunk_config.yml` are actually deployed correctly to the appropriate servers and directories.

## Architecture

### Verification Playbook
**Location:** `ansible/verification/verify_app_deployment.yml`

Orchestrates verification across all deployment methods:
1. Deployment Server (`etc/deployment-apps/`)
2. Cluster Manager (`etc/manager-apps/`)
3. Deployer (`etc/shcluster/apps/`)
4. Direct Deployment (`etc/apps/`)

### Role-Specific Verification Tasks

Each `apps_*` role includes verification logic:

| Role | Verification Task | Target Directory |
|------|------------------|------------------|
| `apps_deployment_server` | `tasks/verify.yml` | `etc/deployment-apps/` |
| `apps_cluster_manager` | `tasks/verify.yml` | `etc/manager-apps/` |
| `apps_deployer` | `tasks/verify.yml` | `etc/shcluster/apps/` |
| `apps_direct` | `tasks/verify.yml` | `etc/apps/` |

## What Gets Verified

### ✅ Apps Presence/Absence

For each app in `splunk_app_deployment.apps`:
- **If `state: installed` (default):** Verifies app directory exists
- **If `state: absent`:** Verifies app directory does NOT exist

### ✅ Correct Deployment Location

Apps are verified in the correct directory based on:
- **Universal Forwarders / Heavy Forwarders:** `deployment-apps/` on Deployment Server
- **Clustered Indexers:** `manager-apps/` on Cluster Manager
- **Clustered Search Heads:** `shcluster/apps/` on Deployer
- **Standalone Indexers/Search Heads:** `apps/` on the host itself
- **Explicit `deployment_target: "direct"`:** `apps/` on target hosts

### ⚠️ Unexpected Apps

Warns about apps present on disk but not defined in configuration.

## Usage

### Report Mode (Default)

Shows mismatches but **does not fail** the playbook:

```bash
ansible-playbook ansible/verification/verify_app_deployment.yml \
  -i config/splunk_config.yml
```

**Use case:** Manual verification, troubleshooting

### Strict Mode (Fail on Mismatch)

**Fails** the playbook if any mismatches are found:

```bash
ansible-playbook ansible/verification/verify_app_deployment.yml \
  -i config/splunk_config.yml \
  -e fail_on_mismatch=true
```

**Use case:** CI/CD pipelines, automated testing

## Example Output

### ✅ All Apps Correct

```
TASK [Display verification results]
ok: [ds] => {
    "msg": [
        "=========================================",
        "DEPLOYMENT SERVER VERIFICATION: ds",
        "=========================================",
        "Expected apps: Splunk_TA_nix, Splunk_TA_windows",
        "Found apps: Splunk_TA_nix, Splunk_TA_windows",
        "Mismatches: 0",
        "  ✓ All apps deployed correctly",
        "========================================="
    ]
}
```

### ❌ Mismatches Found

```
TASK [Display verification results]
ok: [cm] => {
    "msg": [
        "=========================================",
        "CLUSTER MANAGER VERIFICATION: cm",
        "=========================================",
        "Expected apps: Splunk_TA_nix",
        "Found apps: Splunk_TA_windows",
        "Mismatches: 2",
        "Issues found:",
        "  - Splunk_TA_nix: MISSING: App should be installed but not found",
        "  - Splunk_TA_windows: UNEXPECTED: App should be absent but is installed",
        "========================================="
    ]
}

TASK [Fail if mismatches found and fail_on_mismatch is true]
fatal: [cm]: FAILED! => {
    "msg": "Cluster manager app verification failed: 2 mismatch(es) found"
}
```

## Integration with PyTest

The verification is integrated into `tests/test_deployment.py`:

```python
def test_14_deploy_splunk_apps(self, config_file):
    """Deploy Splunk apps according to configuration."""
    result = self._run_playbook("ansible/deploy_splunk_apps.yml")
    assert result.returncode == 0
    self.manager.is_apps_deployed = True

def test_15_verify_app_deployment(self, config_file):
    """Verify apps are deployed correctly with strict mode."""
    result = self._run_playbook(
        "ansible/verification/verify_app_deployment.yml",
        ["-e", "fail_on_mismatch=true"]
    )
    assert result.returncode == 0
```

**Running tests:**

```bash
# Run all tests including app deployment verification
pytest tests/test_deployment.py --config tests/configs/test_config.yml

# Run only app deployment tests
pytest tests/test_deployment.py::TestSplunkDeployment::test_14_deploy_splunk_apps
pytest tests/test_deployment.py::TestSplunkDeployment::test_15_verify_app_deployment
```

## Configuration Example

```yaml
splunk_app_deployment:
  apps:
    # App should be installed on forwarders (via deployment server)
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      state: installed  # ← Verify app EXISTS
      target_roles:
        - universal_forwarder
        - heavy_forwarder

    # App should be removed from indexers
    - name: "Splunk_TA_windows"
      source: splunkbase
      app_id: 742
      state: absent  # ← Verify app DOES NOT EXIST
      target_roles:
        - indexer

    # App deployed directly (bypassing management servers)
    - name: "custom_app"
      source: local
      local_path: "/path/to/app"
      deployment_target: "direct"  # ← Verify in etc/apps on target hosts
      target_roles:
        - search_head
```

## Verification Logic by Role

### Deployment Server

```yaml
# Filters apps where:
- target_roles contains 'universal_forwarder' OR 'heavy_forwarder'
- deployment_target != 'direct'

# Checks directory:
{{ splunk_home }}/etc/deployment-apps/{{ app_name }}
```

### Cluster Manager

```yaml
# Filters apps where:
- target_roles contains 'indexer'
- deployment_target != 'direct'

# Checks directory:
{{ splunk_home }}/etc/manager-apps/{{ app_name }}
```

### Deployer

```yaml
# Filters apps where:
- target_roles contains 'search_head'
- deployment_target != 'direct'

# Checks directory:
{{ splunk_home }}/etc/shcluster/apps/{{ app_name }}
```

### Direct Deployment

```yaml
# Filters apps where:
- deployment_target == 'direct' (explicit)
  OR
- Host is standalone (not clustered) and not a management server

# Checks directory:
{{ splunk_home }}/etc/apps/{{ app_name }}
```

## File Structure

```
ansible/
├── verification/
│   ├── verify_app_deployment.yml          # Main verification playbook
│   └── README.md                          # Verification documentation
└── roles/
    ├── apps_deployment_server/tasks/
    │   ├── verify.yml                     # DS verification logic
    │   └── verify_single_app.yml          # Check single app
    ├── apps_cluster_manager/tasks/
    │   ├── verify.yml                     # CM verification logic
    │   └── verify_single_app.yml          # Check single app
    ├── apps_deployer/tasks/
    │   ├── verify.yml                     # Deployer verification logic
    │   └── verify_single_app.yml          # Check single app
    └── apps_direct/tasks/
        ├── verify.yml                     # Direct deployment verification
        └── verify_single_app.yml          # Check single app

tests/
└── test_deployment.py                     # PyTest integration
```

## Troubleshooting

### Verification Reports Mismatches

**1. Re-run deployment:**
```bash
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
ansible-playbook ansible/verification/verify_app_deployment.yml -i config/splunk_config.yml
```

**2. Check deployment logs:**
Look for errors during the deployment playbook run.

**3. Verify configuration:**
Ensure `target_roles` and `deployment_target` are correct in `config/splunk_config.yml`.

### Unexpected Apps Warning

Apps present on disk but not in configuration will show as warnings.

**Options:**
- Add them to `splunk_config.yml` if they should be managed
- Manually remove them if they're obsolete
- Set `state: absent` in config and redeploy

### Verification Skipped

If verification is skipped for a host, it means no apps are expected there based on the routing logic. This is normal.

## Best Practices

1. **Always verify after deployment:**
   ```bash
   ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml && \
   ansible-playbook ansible/verification/verify_app_deployment.yml -i config/splunk_config.yml
   ```

2. **Use strict mode in CI/CD:**
   ```bash
   -e fail_on_mismatch=true
   ```

3. **Verify specific hosts:**
   ```bash
   --limit ds,cm,deployer
   ```

4. **Check verification before changes:**
   Establish baseline before making configuration changes.

## Exit Codes

| Mode | Condition | Exit Code | Behavior |
|------|-----------|-----------|----------|
| Report | No mismatches | 0 | ✅ Pass |
| Report | Mismatches found | 0 | ⚠️ Pass with warnings |
| Strict | No mismatches | 0 | ✅ Pass |
| Strict | Mismatches found | Non-zero | ❌ Fail |

## See Also

- [App Deployment Guide](App_Deployment_Guide.md)
- [Deployment Server Setup](Deployment_Server_Setup.md)
- [Verification README](../ansible/verification/README.md)
