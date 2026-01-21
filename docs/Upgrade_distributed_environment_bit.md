# Upgrade steps of a distributed Splunk environment

## This example upgrades 8.0+ to later versions with rolling upgrades

- Edit splunk_config.yml to have the new splunk_version
- Make sure the binaries are download to the Software directory

## Checks during upgrade

- Check migration logs with this search:
  - `index="_internal" source="*migration.log.*"`
  - `index="_internal" source="*migration.log.*" | stats latest(VERSION) by host`

### Upgrade the Cluster Master

Check Indexer Cluster status

```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='show cluster-status --verbose'"
```

Note: Look for this line: Pre-flight check successful .................. YES

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_cluster_master
```

### Upgrade vmsplunkshd91p51.mz.admin.ch (Dev SH)

```
ansible-playbook ansible/upgrade_splunk.yml --limit vmsplunkshd91p51.mz.admin.ch
```

### Upgrade the Monitoring Console

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_monitoring_console
```

### Upgrade OpenAccess SHs

```
ansible-playbook ansible/upgrade_splunk.yml --limit vmsplunksh91p04.mz.admin.ch
ansible-playbook ansible/upgrade_splunk.yml --limit vmsplunksh91p05.mz.admin.ch
```

## Rolling upgrade for search head cluster
Docs: https://docs.splunk.com/Documentation/Splunk/8.1.5/DistSearch/SHCrollingupgrade

### Prework and Preflight checks

Check if we have a KV Store Backup (from the cronjob script)


Check captain and status of SHC
```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='show shcluster-status'"
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='show kvstore-status'"
```

Switch Captain to last node in the cluster (if needed)

```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='transfer shcluster-captain -mgmt_uri https://vmsplunksh91p03.mz.admin.ch:8089'"
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='show shcluster-status'"
```

### Run SHC Rolling Upgrade

```
ansible-playbook ansible/upgrade_splunk_shc_rolling.yml
```

### Upgrade the deployer

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_deployer
```

### Check for proper functionality on the SHC

- ITSI
- Different Dashboards

## Rolling upgrade for indexer cluster
Docs: https://docs.splunk.com/Documentation/Splunk/8.1.5/Indexer/Searchablerollingupgrade#Perform_a_rolling_upgrade

### Run the rolling Indexer Cluster upgrade playbook

```
ansible-playbook ansible/upgrade_splunk_idxc_rolling.yml
```

### Rerun the peer offline
Sometime it happens, that after running the peer offline command the indexer does the primaries reassign, but then does not go down.
It happens that it goes back to status Up and the process does not proceed. You can send the offline call again manually:

```
ansible-playbook ansible/call_splunk_rest.yml -e "splunk_rest_endpoint=/services/cluster/slave/control/control/decommission" -e "http_method=POST" --limit <indexer_name>
```

## Upgrade Heavy Forwarders

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_heavy_forwarder
```

## Upgrade Intermediate Universal Forwarders

tbd: maybe in serial mode

```
ansible-playbook ansible/upgrade_splunk.yml --limit edavmp01515.eda.edaad.admin.ch
ansible-playbook ansible/upgrade_splunk.yml --limit edavmp01516.eda.edaad.admin.ch
```

## Check all versions

```
ansible-playbook ansible/run_splunk_command.yml -e "splunk_command='version'"
```

## Upgrade Universal Forwarders auf Datensammler

(als root)
```
systemctl stop splunkforwarder
/appl/splunkforwarder/bin/splunk disable boot-start
```

(als splunk)
```
cd /appl
tar -xzf /var/tmp/splunkforwarder-8.2.4-87e2dda940d1-Linux-x86_64.tgz
```

(als root)
```
/appl/splunkforwarder/bin/splunk enable boot-start -systemd-managed 1 -systemd-unit-file-name splunkforwarder -create-polkit-rules 1 -user splunk --answer-yes --no-prompt --accept-license
systemctl daemon-reload
systemctl start splunkforwarder
```

## Upgrade Heavy Forwarder on Windows
https://docs.splunk.com/Documentation/Splunk/8.1.5/Installation/UpgradeonWindows