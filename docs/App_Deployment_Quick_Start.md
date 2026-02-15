# App Deployment – Quick Start Guide

## TL;DR - Get Started in 5 Minutes

### Step 1: Add Configuration to `splunk_config.yml`

Add this section to your `config/splunk_config.yml`:

```yaml
splunk_app_deployment:
  splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
  splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
  local_app_repo_path: "../app_repo"
  
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles:
        - search_head
      # target_path / deployment target automatically calculated based on environment
```

### Step 2: Set Your Splunkbase Credentials

```bash
export SPLUNKBASE_USERNAME='your_email@example.com'
export SPLUNKBASE_PASSWORD='your_password'
```

### Step 3: Run the Playbook

```bash
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    config/splunk_config.yml                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ splunk_app_deployment:                                 │  │
│  │   apps:                                                │  │
│  │     - name: App1 (source: splunkbase)                  │  │
│  │     - name: App2 (source: local)                       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│          ansible/deploy_splunk_apps.yml (Playbook)           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  apps_deployment_server, apps_cluster_manager,              │
│  apps_deployer, apps_direct (roles)                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Splunkbase    │  │  Local Repo    │  │    Deploy    │  │
│  │   Download     │  │     Copy       │  │   & Install  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Target Splunk Servers                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Search   │  │ Indexer  │  │ Cluster  │  │ Deployer │   │
│  │  Heads   │  │          │  │ Manager  │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Intelligent Target Location

### Automatic Location Calculation

The role **automatically determines** where to deploy apps based on your environment:

| Your Setup | Target Role | Automatic Deployment |
|------------|-------------|---------------------|
| Indexer Cluster exists | `indexer` | → Cluster Manager `etc/manager-apps` |
| Search Head Cluster exists | `search_head` | → Deployer `etc/shcluster/apps` |
| Deployment Server exists | `universal_forwarder` | → Deployment Server `etc/deployment-apps` |
| Standalone | any role | → Direct to host `etc/apps` |

**Benefits**:
- ✅ No need to specify `target_path` for most cases
- ✅ Apps automatically go to the right distribution point
- ✅ Follows Splunk best practices
- ✅ Less configuration, fewer errors

**Example**:
```yaml
# OLD WAY (manual):
- name: "Splunk_TA_nix"
  target_roles: [indexer]
  target_path: "etc/manager-apps"  # Had to specify manually
  
# NEW WAY (automatic):
- name: "Splunk_TA_nix"
  target_roles: [indexer]
  # target_path automatically calculated from deployment method!
  # Goes to cluster_manager if cluster exists, or direct if standalone
```

**Manual Override** (if needed):
```yaml
- name: "test_app"
  target_roles: [indexer]
  target_path: "etc/apps"      # Optional: override install path
  deployment_target: "direct"   # Bypass cluster manager
```

**Learn More**: See `docs/App_Deployment_Target_Logic.md` for detailed decision tree.

---

## Common Use Cases

### Use Case 1: Deploy Technology Add-on (TA) to All Systems

**Scenario**: Install Splunk Add-on for Unix & Linux across all systems

```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles:
        - search_head
        - indexer
        - heavy_forwarder
      # target_path: auto (automatically calculated from deployment method)
      # - If indexer cluster exists: goes to cluster_manager etc/manager-apps
      # - If search head cluster exists: goes to deployer etc/shcluster/apps
      # - Otherwise: direct to host etc/apps
```

### Use Case 2: Deploy Custom App from Git Repository

**Scenario**: Deploy your custom app that's version controlled in Git

```yaml
# 1. Clone your app repo to app_repo directory
# git clone https://github.com/yourorg/my_custom_app.git app_repo/my_custom_app

# 2. Configure in splunk_config.yml
splunk_app_deployment:
  local_app_repo_path: "../app_repo"
  apps:
    - name: "my_custom_app"
      source: local
      path: "my_custom_app"
      target_roles:
        - search_head
      target_path: "etc/apps"
```

### Use Case 3: Deploy to Search Head Cluster (Automatic)

**Scenario**: Deploy apps to all SHC members (automatically via Deployer)

```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_ML_Toolkit"
      source: splunkbase
      app_id: 2890
      version: "5.4.2"
      target_roles:
        - search_head  # Automatically goes to deployer if SHC exists!
      # target_path: auto (calculated as etc/shcluster/apps)
```

**What Happens**:
1. Role detects Search Head Cluster configuration
2. Automatically deploys to deployer at `etc/shcluster/apps`
3. No need to manually specify deployer!

**Note**: After deployment, you'll need to push the bundle:
```bash
ansible-playbook ansible/run_splunk_command.yml \
  -i config/splunk_config.yml \
  --limit role_deployer \
  -e "splunk_command='apply shcluster-bundle'"
```

### Use Case 4: Deploy to Indexer Cluster (Automatic)

**Scenario**: Deploy apps to all indexers (automatically via Cluster Manager)

```yaml
splunk_app_deployment:
  apps:
    - name: "org_cluster_indexer_base"
      source: local
      path: "org_cluster_indexer_base"
      target_roles:
        - indexer  # Automatically goes to cluster_manager if cluster exists!
      # target_path: auto (calculated as etc/manager-apps)
```

**What Happens**:
1. Role detects Indexer Cluster configuration
2. Automatically deploys to cluster_manager at `etc/manager-apps`
3. Cluster Manager automatically distributes to all indexers
4. No manual intervention needed!

**Note**: The cluster manager will automatically distribute to indexers.

### Use Case 5: Deploy Multiple Apps at Once

**Scenario**: Initial environment setup with multiple apps (all with automatic location)

```yaml
splunk_app_deployment:
  splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
  splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
  local_app_repo_path: "../app_repo"
  
  apps:
    # Splunkbase apps - auto-deployed to optimal location
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles: [search_head, indexer]
      # Auto: cluster_manager if idxc, deployer if shc, or direct
    
    - name: "Splunk_TA_aws"
      source: splunkbase
      app_id: 1876
      version: "7.2.0"
      target_roles: [search_head, heavy_forwarder]
      # Auto: deployer if shc, or direct
    
    # Local apps - also auto-calculated
    - name: "org_all_search_base"
      source: local
      path: "org_all_search_base"
      target_roles: [universal_forwarder]
      # Auto: deployment_server if exists, or direct
    
    - name: "org_all_indexes"
      source: local
      path: "org_all_indexes"
      target_roles: [indexer]
      # Auto: cluster_manager if idxc exists
```

---

## Finding Splunkbase App IDs

### Method 1: From Splunkbase URL

Visit the app on Splunkbase and look at the URL:

```
https://splunkbase.splunk.com/app/833/
                                    ^^^
                                    App ID
```

### Method 2: Common Apps Quick Reference

| App Name                        | App ID | Description                    |
|---------------------------------|--------|--------------------------------|
| Splunk Add-on for Unix & Linux  | 833    | Unix/Linux data collection     |
| Splunk Add-on for Windows       | 742    | Windows data collection        |
| Splunk Add-on for AWS           | 1876   | AWS data collection            |
| Splunk DB Connect               | 2686   | Database connectivity          |
| Splunk Machine Learning Toolkit | 2890   | ML algorithms and tools        |
| Splunk Security Essentials      | 3435   | Security use cases showcase    |
| Splunk Enterprise Security      | 263    | SIEM solution (premium)        |
| Python for Scientific Computing | 2882   | Python libraries for ML        |

---

## Directory Structure

### Where Apps Get Deployed

```
Splunk Server
└── /opt/splunk/  (or your SPLUNK_HOME)
    ├── etc/
    │   ├── apps/                    ← Standard apps
    │   │   ├── Splunk_TA_nix/
    │   │   └── my_custom_app/
    │   │
    │   ├── deployment-apps/         ← Deployment Server
    │   │   └── org_all_search_base/
    │   │
    │   ├── shcluster/               ← Search Head Cluster (Deployer)
    │   │   └── apps/
    │   │       └── Splunk_ML_Toolkit/
    │   │
    │   └── manager-apps/            ← Indexer Cluster (Cluster Manager)
    │       └── org_cluster_indexer_base/
```

### Your Local Repository Structure

```
spa_apps/
├── app_repo/                        ← Your local apps
│   ├── my_custom_app/
│   │   ├── default/
│   │   │   └── app.conf
│   │   ├── local/
│   │   └── metadata/
│   │
│   ├── org_all_search_base/
│   └── org_cluster_indexer_base/
│
└── config/
    └── splunk_config.yml            ← Configuration file
```

---

## Deployment Workflows

### Workflow 1: Deploy from Splunkbase

```
1. User defines app in splunk_config.yml
   ↓
2. Ansible queries Splunkbase API for app info
   ↓
3. Ansible authenticates with Splunkbase credentials
   ↓
4. Download app package (.tgz) to Ansible host
   ↓
5. Upload app to target Splunk server
   ↓
6. Extract to target location (etc/apps)
   ↓
7. Set ownership (splunk:splunk) and permissions
   ↓
8. Restart Splunk (if required)
```

### Workflow 2: Deploy from Local Repository

```
1. User places app in app_repo/ directory
   ↓
2. User defines app in splunk_config.yml
   ↓
3. Ansible locates app in local repository
   ↓
4. Sync/copy app to target Splunk server
   ↓
5. Set ownership and permissions
   ↓
6. Restart Splunk (if required)
```

---

## Security Best Practices

### ✅ DO THIS

```yaml
# Use environment variables for BOTH username and password
splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"

# Or use Ansible Vault for both
splunkbase_username: "{{ vault_splunkbase_username }}"
splunkbase_password: "{{ vault_splunkbase_password }}"
```

```bash
# Export both credentials before running playbook
export SPLUNKBASE_USERNAME='your_email@example.com'
export SPLUNKBASE_PASSWORD='your_password'

# Or use Ansible Vault
ansible-vault create secrets.yml
# Add: 
#   vault_splunkbase_username: your_email@example.com
#   vault_splunkbase_password: your_password
```

### ❌ DON'T DO THIS

```yaml
# NEVER hardcode credentials!
splunkbase_username: "user@example.com"  # ❌ BAD!
splunkbase_password: "MyP@ssw0rd123"      # ❌ BAD!
```

---

## Troubleshooting

### Problem: "Authentication failed" with Splunkbase

**Solution**: 
1. Verify your Splunkbase credentials
2. Ensure password is exported: `echo $SPLUNKBASE_PASSWORD`
3. Check if your account has access to download apps
4. Some premium apps require special permissions

### Problem: App not appearing after deployment

**Solution**:
1. Check if Splunk was restarted: `./splunk restart`
2. Verify app ownership: `ls -la $SPLUNK_HOME/etc/apps/`
3. Check Splunk logs: `$SPLUNK_HOME/var/log/splunk/splunkd.log`
4. Verify app structure is valid: `./splunk btool check`

### Problem: "App already exists" error

**Solution**:
1. The role should handle this automatically
2. If you want to force reinstall, manually remove the app first
3. Or use the `backup_before_update: true` option

### Problem: Download timeout

**Solution**:
1. Check network connectivity to Splunkbase
2. Increase timeout in role defaults
3. Large apps may take longer to download

---

## Advanced Configuration

### Pin Specific Versions

```yaml
apps:
  - name: "Splunk_ML_Toolkit"
    source: splunkbase
    app_id: 2890
    version: "5.4.2"  # Specific version, not "latest"
```

### Disable Restart After Deployment

```yaml
splunk_app_deployment:
  apps:
    - name: "my_app"
    source: local
    path: "my_app"
    target_roles: [search_head]
    target_path: "etc/apps"
    # restart_required: false  # if supported
```

### Deploy to Specific Hosts Only

Use `--limit` to target specific hosts:
```bash
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml --limit sh1
```

Or define apps with `target_roles` so they only apply to hosts in those roles; use `deployment_target: "direct"` and `target_path: "etc/apps"` for direct deployment.

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Deploy Splunk Apps

on:
  push:
    branches: [main]
    paths:
      - 'app_repo/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Ansible
        run: pip install ansible
      
      - name: Deploy Apps
        env:
          SPLUNKBASE_PASSWORD: ${{ secrets.SPLUNKBASE_PASSWORD }}
        run: |
          ansible-playbook ansible/deploy_splunk_apps.yml \
            -i config/splunk_config.yml
```

---

## Command Reference

```bash
# Deploy all apps to all targets
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml

# Deploy only to search heads
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml \
  --limit role_search_head

# Deploy only to specific host
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml \
  --limit sh1

# Dry run (check what would be deployed)
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml \
  --check

# Deploy with extra verbosity (for debugging)
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml \
  -vvv

# Deploy only Splunkbase apps (using tags)
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml \
  --tags splunkbase

# Deploy only local apps (using tags)
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml \
  --tags local_apps
```

---

## Next Steps

1. **Review the full guide**: See `docs/App_Deployment_Guide.md`
2. **Check Example Config**: See `examples/splunk_apps_config_example.yml`
3. **Start with Phase 1**: Implement Splunkbase integration first
4. **Test in Non-Production**: Always test in a dev environment first
5. **Expand Gradually**: Add more apps and features as needed

---

## Support & Documentation

- **Full Guide**: `docs/App_Deployment_Guide.md`
- **Example Config**: `examples/splunk_apps_config_example.yml`
- **Splunkbase API**: https://dev.splunk.com/enterprise/docs/releaseapps/splunkbase/
- **Ansible Docs**: https://docs.ansible.com/

---

## License & Contributing

This follows the same license and contribution guidelines as the main Splunk Platform Automator project.
