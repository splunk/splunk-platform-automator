# Upgrade steps of a distributed Splunk environment

## This example upgrades 8.0+ to later versions with rolling upgrades

- Edit splunk_config.yml to have the new splunk_version
- Make sure the binaries are download to the Software directory
- Check the [Splunk Upgrade Order Process](https://docs.splunk.com/images/d/d3/Splunk_upgrade_order_of_ops.pdf)

## Checks during upgrade

- Check migration logs with this search:
  - `index=_internal sourcetype=splunk_migration`
  - `index=_internal sourcetype=splunk_migration | stats latest(VERSION) by host`


### Upgrade the Deployment Server

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_deployment_server
```

### Upgrade the License Master

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_license_master
```

### Upgrade the Cluster Master

Check Indexer Cluster status

```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='show cluster-status --verbose'"
```

Note: Look for this line: Pre-flight check successful .................. YES

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_cluster_master
```

### Upgrade the Monitoring Console

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_monitoring_console
```

### Upgrade any single search head

```
ansible-playbook ansible/upgrade_splunk.yml --limit <search_head1>,<search_head2>
```

### Upgrade the SHC Deployer

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_deployer
```

## Rolling upgrade for search head cluster
[Splunk Docs](https://docs.splunk.com/Documentation/Splunk/latest/DistSearch/SHCrollingupgrade)

### Prework and Preflight checks

Check if we have a KV Store Backup (from the cronjob script)


Check captain and status of SHC
```
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='show shcluster-status'"
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='show kvstore-status'"
```

Switch Captain to last node in the cluster (sh3 in this example)

```
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='transfer shcluster-captain -mgmt_uri https://sh3:8089'"
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='show shcluster-status'"
```

### Run SHC Rolling Upgrade

```
ansible-playbook ansible/upgrade_splunk_shc_rolling.yml
```

### Check for proper functionality on the SHC

- Check some searches
- Check some dashboards

## Rolling upgrade for indexer cluster
[Splunk Docs](https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Searchablerollingupgrade#Perform_a_rolling_upgrade)

### Run the rolling Indexer Cluster upgrade playbook

```
ansible-playbook ansible/upgrade_splunk_idxc_rolling.yml
```

### Rerun the peer offline
Sometime it happens after running the peer offline command the indexer does the primaries reassign but then does not go down.
It can happen that it goes back to status Up and the process does not proceed. You can send the offline call again manually:

```
ansible-playbook ansible/call_splunk_rest.yml -e "splunk_rest_endpoint=/services/cluster/slave/control/control/decommission" -e "http_method=POST" --limit <indexer_name>
```

## Upgrade Heavy Forwarders

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_heavy_forwarder
```

## Upgrade Intermediate Universal Forwarders

If you have pairs, do not upgrade both at the same time

```
ansible-playbook ansible/upgrade_splunk.yml --limit iuf1
ansible-playbook ansible/upgrade_splunk.yml --limit iuf2
```

## Upgrade Universal Forwarders

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_universal_forwarder
```

## Check all versions

```
ansible-playbook ansible/run_splunk_command.yml -e "splunk_command='version'"
```