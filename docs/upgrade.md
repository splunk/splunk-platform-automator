# Upgrade steps of a distributed Splunk environment

From the environment directory. Discover names with `spa run --list` / `spa run NAME --help`.

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
spa run upgrade_splunk --yes --hosts deployment_server
```

### Upgrade the License Manager

```
spa run upgrade_splunk --yes --hosts license_manager
```

### Upgrade the Cluster Manager

Check Indexer Cluster status

```
spa run splunk_cli --yes --hosts cluster_manager -- -e "splunk_command='show cluster-status --verbose'"
```

Note: Look for this line: Pre-flight check successful .................. YES

```
spa run upgrade_splunk --yes --hosts cluster_manager
```

### Upgrade the Monitoring Console

```
spa run upgrade_splunk --yes --hosts monitoring_console
```

### Upgrade any single search head

```
spa run upgrade_splunk --yes --hosts <search_head1>,<search_head2>
```

### Upgrade the SHC Deployer

```
spa run upgrade_splunk --yes --hosts deployer
```

## Rolling upgrade for search head cluster
[Splunk Docs](https://docs.splunk.com/Documentation/Splunk/latest/DistSearch/SHCrollingupgrade)

### Prework and Preflight checks

Check if we have a KV Store Backup (from the cronjob script)


Check captain and status of SHC
```
spa run splunk_cli --yes --hosts sh1 -- -e "splunk_command='show shcluster-status'"
spa run splunk_cli --yes --hosts sh1 -- -e "splunk_command='show kvstore-status'"
```

Switch Captain to last node in the cluster (sh3 in this example)

```
spa run splunk_cli --yes --hosts sh1 -- -e "splunk_command='transfer shcluster-captain -mgmt_uri https://sh3:8089'"
spa run splunk_cli --yes --hosts sh1 -- -e "splunk_command='show shcluster-status'"
```

### Run SHC Rolling Upgrade

```
spa run upgrade_shc_rolling --yes
```

### Check for proper functionality on the SHC

- Check some searches
- Check some dashboards

## Rolling upgrade for indexer cluster
[Splunk Docs](https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Searchablerollingupgrade#Perform_a_rolling_upgrade)

### Run the rolling Indexer Cluster upgrade playbook

```
spa run upgrade_idxc_rolling --yes
```

### Rerun the peer offline
Sometime it happens after running the peer offline command the indexer does the primaries reassign but then does not go down.
It can happen that it goes back to status Up and the process does not proceed. You can send the offline call again manually:

```
spa run splunk_rest --yes --hosts <indexer_name> -- -e "splunk_software_rest_endpoint=/services/cluster/slave/control/control/decommission" -e "splunk_software_rest_method=POST"
```

## Upgrade Heavy Forwarders

```
spa run upgrade_splunk --yes --hosts heavy_forwarder
```

## Upgrade Intermediate Universal Forwarders

If you have pairs, do not upgrade both at the same time

```
spa run upgrade_splunk --yes --hosts iuf1
spa run upgrade_splunk --yes --hosts iuf2
```

## Upgrade Universal Forwarders

```
spa run upgrade_splunk --yes --hosts universal_forwarder
```

## Check all versions

```
spa run splunk_cli --yes -- -e "splunk_command='version'"
```
