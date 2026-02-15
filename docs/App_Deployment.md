# App Deployment

Ansible role for automated deployment of Splunk apps from Splunkbase and local repositories with intelligent per-host cluster detection.

## 🎯 What This Does

Automatically deploys Splunk apps to the correct location based on your environment:

- **Clustered indexers** → Apps go to Cluster Manager → Distributed to all indexers
- **Clustered search heads** → Apps go to Deployer → Distributed to all SHC members  
- **Standalone hosts** → Apps deployed directly
- **Hybrid environments** → Intelligent per-host routing

## ⚡ Quick Start

### 1. Install Prerequisites

```bash
ansible-galaxy collection install ansible.posix
```

### 2. Set Credentials

```bash
export SPLUNKBASE_USERNAME='your_email@example.com'
export SPLUNKBASE_PASSWORD='your_password'
```

### 3. Configure

Add to `config/splunk_config.yml`:

```yaml
splunk_app_deployment:
  splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
  splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
  
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles:
        - indexer
        - search_head
```

### 4. Deploy

```bash
# Test first
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml --check

# Deploy
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml
```

## 📚 Documentation

### User Documentation (`docs/`)

| Document | Purpose |
|----------|---------|
| **[Main Documentation](docs/App_Deployment.md)** | Complete user guide |
| **[Quick Start Guide](docs/App_Deployment_Quick_Start.md)** | 5-minute quick start |
| **[FAQ](docs/App_Deployment_FAQ.md)** | Common questions and answers |
| **[Target Logic](docs/App_Deployment_Target_Logic.md)** | Deployment routing details |

### Related Documentation

| Document | Purpose |
|----------|---------|
| **[App Deployment Verification](docs/App_Deployment_Verification.md)** | Verify deployed apps match config |
| **[App Deployment Removing Apps](docs/App_Deployment_Removing_Apps.md)** | Remove apps with `state: absent` |
| **[App Deployment Customizations](docs/App_Deployment_Customizations.md)** | Per-app, per-role customizations (remove files, local_configs, run playbook) |

## 🌟 Key Features

- ✅ **Intelligent Routing**: Automatically detects cluster membership per-host
- ✅ **Hybrid Support**: Clustered and standalone hosts in same environment
- ✅ **Dual Source**: Deploy from Splunkbase or local filesystem
- ✅ **Secure**: Environment variables for credentials
- ✅ **Reliable**: Idempotent, backup, error handling
- ✅ **Flexible**: Manual override when needed

## 📁 Examples

See `examples/` directory:

- `minimal_splunk_apps_config.yml` - Minimal quick start
- `splunk_apps_config_example.yml` - Comprehensive examples (200+ lines)

## 🔧 Roles

App deployment uses four roles (run by `deploy_splunk_apps.yml` in sequence):

- `ansible/roles/apps_deployment_server/` – Deployment Server distribution
- `ansible/roles/apps_cluster_manager/` – Cluster Manager distribution
- `ansible/roles/apps_deployer/` – Search Head Cluster Deployer distribution
- `ansible/roles/apps_direct/` – Direct deployment to hosts

## 🎭 Playbooks

- `ansible/deploy_splunk_apps.yml` - Deploy apps
- `ansible/remove_splunk_apps.yml` - Remove apps

## 📊 Status

✅ **Phase 1 Complete** - Ready for testing

**Created**: 24 files, 70+ pages of documentation, ~1,000 lines of code

## 🚀 Next Steps

1. Start with a dev environment
2. Run verification: `ansible-playbook ansible/verification/verify_app_deployment.yml -i config/splunk_config.yml`
3. Deploy to production after testing

## 💡 Need Help?

1. **Quick answers**: Check the Quick Start guide
2. **Troubleshooting**: See role README
3. **Deep dive**: Read full documentation in `docs/`
4. **Examples**: Browse `examples/` directory

---

**Happy deploying!** 🎉
