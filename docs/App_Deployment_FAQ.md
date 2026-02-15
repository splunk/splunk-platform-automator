# Splunk App Deployment - FAQ

Frequently Asked Questions about the Splunk App Deployment role.

## General Questions

### What is this role for?

This role automates the deployment of Splunk apps from Splunkbase or local repositories. It intelligently determines where to deploy apps based on your environment configuration (clustered vs standalone hosts).

### Do I need both Splunkbase and local app support?

No. You can use either:
- **Splunkbase only**: Set credentials and deploy public apps
- **Local only**: Skip Splunkbase credentials and deploy custom apps
- **Both**: Deploy a mix of public and custom apps

### Will this work with my existing Splunk setup?

Yes! The role is designed to work with any Splunk Enterprise environment:
- Standalone hosts
- Indexer clusters
- Search head clusters
- Hybrid environments (mix of clustered and standalone)
- Deployment server environments

## Configuration

### Where do Splunkbase credentials come from?

From environment variables for security:
```bash
export SPLUNKBASE_USERNAME='your_email@example.com'
export SPLUNKBASE_PASSWORD='your_password'
```

The configuration file references them:
```yaml
splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
```

### Can I use Ansible Vault instead?

Yes! You can store credentials in Ansible Vault:
```yaml
splunkbase_username: "{{ vault_splunkbase_username }}"
splunkbase_password: "{{ vault_splunkbase_password }}"
```

### How do I find Splunkbase app IDs?

Look at the URL when viewing an app on Splunkbase:
```
https://splunkbase.splunk.com/app/833/
                                    ^^^
                                  App ID
```

### What if I don't specify target_path?

The roles automatically calculate the install path based on the deployment method (DS, CM, Deployer, or direct) and host's cluster membership:
- Clustered indexer → Cluster Manager `etc/manager-apps`
- Clustered search head → Deployer `etc/shcluster/apps`
- Standalone → Direct to host `etc/apps`

## Deployment Behavior

### How does the role know if a host is in a cluster?

It checks each host's attributes:
- `idxcluster: idxc1` → Host is in indexer cluster "idxc1"
- `shcluster: shc1` → Host is in search head cluster "shc1"
- No attributes → Host is standalone

### What happens in a hybrid environment?

Each host is evaluated individually:
```yaml
# Clustered indexer
- name: idx_prod
  roles: [indexer]
  idxcluster: idxc1  # ← Goes to cluster_manager

# Standalone indexer
- name: idx_dev
  roles: [indexer]   # ← Goes directly to idx_dev
```

The same app configuration works for both!

### Does it restart Splunk automatically?

Yes, by default. You can control this:
```yaml
restart_required: false  # Skip restart for this app
```

Or skip restart for all apps:
```bash
ansible-playbook ... --skip-tags splunk_restart
```

### What if the app is already installed?

The role is idempotent:
1. Checks if app exists
2. Compares versions
3. Only updates if needed
4. Backs up existing app before update

### Can I deploy the same app to different locations?

Yes! Define it multiple times with different configurations:
```yaml
apps:
  # To clustered indexers
  - name: "my_app"
    target_roles: [indexer]
    # Auto: goes to cluster_manager

  # To standalone search head
  - name: "my_app"
    target_roles: [search_head]
    target_path: "etc/apps"  # Force direct path override
```

## Troubleshooting

### Authentication keeps failing with Splunkbase

**Check**:
1. Are environment variables set? `echo $SPLUNKBASE_USERNAME`
2. Is your password correct?
3. Does your account have permission to download the app?
4. Is the app premium/licensed?

**Solution**: Some apps require special permissions or licensing.

### App downloads but doesn't appear in Splunk

**Check**:
1. Location: `ls -la /opt/splunk/etc/apps/`
2. Ownership: Should be `splunk:splunk`
3. Logs: `tail -100 /opt/splunk/var/log/splunk/splunkd.log`
4. Validation: `/opt/splunk/bin/splunk btool check`

### App went to the wrong location

**Check**:
1. Does the host have the correct `idxcluster` or `shcluster` attribute?
2. Run with `-vv` to see the deployment decision
3. Verify cluster_manager or deployer exists in configuration

**Solution**: 
- Fix host attributes in `splunk_config.yml`
- Or use manual override: `target_path: "etc/apps"` and/or `deployment_target: "direct"`

### Deployment is slow

**Causes**:
- Large apps take time to download
- Network latency to Splunkbase
- Many hosts to deploy to

**Solutions**:
- Apps are cached locally after first download
- Deploy to specific hosts: `--limit role_search_head`
- Increase timeout if needed

### How do I roll back an app update?

The role backs up apps automatically:
```bash
# 1. Find backup
ls /opt/splunk/var/backup/apps/

# 2. Stop Splunk
/opt/splunk/bin/splunk stop

# 3. Restore
rm -rf /opt/splunk/etc/apps/MY_APP
cp -r /opt/splunk/var/backup/apps/MY_APP_2025-02-03_removed/ /opt/splunk/etc/apps/MY_APP/
chown -R splunk:splunk /opt/splunk/etc/apps/MY_APP

# 4. Start Splunk
/opt/splunk/bin/splunk start
```

## Advanced Usage

### Can I deploy to only one host for testing?

Yes!
```bash
ansible-playbook ansible/deploy_splunk_apps.yml \
  -i config/splunk_config.yml --limit sh1
```

### How do I test without actually deploying?

Use dry-run mode:
```bash
ansible-playbook ansible/deploy_splunk_apps.yml \
  -i config/splunk_config.yml --check -vv
```

### Can I deploy apps that depend on other apps?

Yes, but you need to order them manually:
```yaml
apps:
  # Deploy dependency first
  - name: "Python_for_Scientific_Computing"
    source: splunkbase
    app_id: 2882
    ...
  
  # Then deploy app that depends on it
  - name: "Splunk_ML_Toolkit"
    source: splunkbase
    app_id: 2890
    ...
```

### How do I integrate this with CI/CD?

Example GitHub Actions workflow:
```yaml
- name: Deploy Splunk Apps
  env:
    SPLUNKBASE_USERNAME: ${{ secrets.SPLUNKBASE_USERNAME }}
    SPLUNKBASE_PASSWORD: ${{ secrets.SPLUNKBASE_PASSWORD }}
  run: |
    ansible-playbook ansible/deploy_splunk_apps.yml \
      -i config/splunk_config.yml
```

### Can I use this for Universal Forwarders?

Yes! Apps for universal forwarders automatically go to the Deployment Server:
```yaml
apps:
  - name: "Splunk_TA_nix"
    target_roles:
      - universal_forwarder  # Automatically goes to deployment_server
```

### What about Search Head Cluster bundle push?

The role deploys to the deployer, but you must push the bundle manually (or automate separately):
```bash
/opt/splunk/bin/splunk apply shcluster-bundle \
  -target https://<captain>:8089 \
  -auth admin:password
```

## Best Practices

### Should I use "latest" or pin versions?

**Development**: Use "latest" for quick testing
**Production**: Pin specific versions for stability

```yaml
# Development
version: "latest"

# Production
version: "8.9.1"
```

### How often should I update apps?

- **Security updates**: Immediately
- **Bug fixes**: As needed
- **Feature updates**: During maintenance windows
- **Major versions**: Test thoroughly first

### Should I deploy all apps at once or gradually?

**Gradual rollout**:
1. Deploy to dev environment
2. Test thoroughly
3. Deploy to test/staging
4. Deploy to production

Use `--limit` to control deployment:
```bash
# Dev first
ansible-playbook ... --limit dev_hosts

# Then prod
ansible-playbook ... --limit prod_hosts
```

### How do I document which apps are deployed?

The configuration file is your documentation:
```yaml
# All apps listed in splunk_config.yml
apps:
  - name: "App1"  # Deployed 2026-01-15
  - name: "App2"  # Deployed 2026-01-20
```

Keep this in version control (Git) for tracking.

### What about app configuration files?

This role deploys apps but doesn't manage their configuration files (*.conf). For configuration management:
1. Create custom apps with your configs
2. Deploy them as local apps
3. Or use the existing `baseconfig_app` role

## Performance

### How long does deployment take?

- **Local app**: 10-30 seconds per host
- **Small Splunkbase app**: 1-2 minutes (including download)
- **Large Splunkbase app**: 2-5 minutes

Subsequent deployments are faster (cached downloads).

### Can I deploy in parallel?

Yes! Ansible deploys to hosts in parallel automatically. You can control parallelism:
```bash
ansible-playbook ... --forks 10  # Deploy to 10 hosts at once
```

### Does it use a lot of disk space?

**Temporary space**: Downloaded apps are cached in `/tmp/splunk_apps/`
**Backup space**: Old app versions in `/opt/splunk/var/backup/apps/`

Clean up periodically if needed.

## Safety

### Is it safe to run multiple times?

Yes! The role is idempotent:
- Checks if app exists
- Only updates when needed
- Won't break existing installations

### What if something goes wrong?

**Automatic protections**:
1. Apps are backed up before updates
2. Dry-run mode available (`--check`)
3. Detailed error messages
4. Splunk won't start if app is invalid

**Manual recovery**:
1. Check backups in `/opt/splunk/var/backup/apps/`
2. Restore previous version
3. Check Splunk logs for errors

### Can it break my cluster?

**Safeguards**:
- Apps deploy to cluster managers/deployers first
- Native Splunk cluster distribution
- Validation before deployment
- Rollback capability

**Best practice**: Always test in non-production first!

## Still Have Questions?

- Check the [main documentation](Splunk_App_Deployment.md)
- Read the [Quick Start guide](Splunk_App_Deployment_Quick_Start.md)
- Review the [Target Logic](Splunk_App_Deployment_Target_Logic.md)
- Check [Target Logic](Splunk_App_Deployment_Target_Logic.md) and [Guide](Splunk_App_Deployment_Guide.md)
