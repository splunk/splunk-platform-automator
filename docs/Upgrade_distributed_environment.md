# Upgrade steps of a distributed Splunk environment

## This example upgrades from 6.6.x to 7.0.x or from 7.0.x to 7.1.x

Docs: https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Upgradeacluster#Upgrade_each_tier_separately

```
ansible-playbook ansible/upgrade_splunk.yml --limit cm

ansible-playbook ansible/stop_splunk.yml --limit role_search_head,ds
ansible-playbook ansible/upgrade_splunk.yml --limit ds
ansible-playbook ansible/upgrade_splunk.yml --limit sh1,sh2,sh3
```

Docs: https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Upgradeacluster#Site-by-site_upgrade_for_multisite_indexer_clusters

```
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='enable maintenance-mode'"
ansible-playbook ansible/upgrade_splunk.yml --limit idxcluster_idxc1_site1
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='disable maintenance-mode'"
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='show cluster-status'"
```

Wait until bucket fixup tasks have completed

```
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='enable maintenance-mode'"
ansible-playbook ansible/upgrade_splunk.yml --limit idxcluster_idxc1_site2
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='disable maintenance-mode'"
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='show cluster-status'"
```

Wait again until bucket fixup tasks have completed

```
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='remove excess-buckets'"
```

## This example upgrades from 7.1.x with rolling upgrades

Upgrade the Cluster Master

```
ansible-playbook ansible/upgrade_splunk.yml --limit cm
```

## Rolling upgrade for search head cluster
Docs: https://docs.splunk.com/Documentation/Splunk/latest/DistSearch/SHCrollingupgrade#Perform_a_rolling_upgrade

```
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='upgrade-init shcluster-members'"
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='edit shcluster-config -manual_detention on'"
```

Check if all searches are finished
```
splunk list shcluster-member-info | grep "active_"
```

Output should be:
```
active_historical_search_count:0
active_realtime_search_count:0
```

Build sum
```
splunk list shcluster-member-info | grep "active_" | cut -d: -f 2 | awk '{ sum += $1; } END { print sum; }' "$@"
```

Upgrade first node
```
ansible-playbook ansible/upgrade_splunk.yml --limit sh1
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='edit shcluster-config -manual_detention off'"
```

Check cluster health
```
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='show shcluster-status --verbose'"
```

Repeat the above two steps for the rest of the nodes

When all nodes are finished upgrade the deployer:
```
ansible-playbook ansible/upgrade_splunk.yml --limit ds
```

Finalize the SHC upgrade
```
ansible-playbook ansible/run_splunk_command.yml --limit sh1 -e "splunk_command='upgrade-finalize shcluster-members'"
```

## Rolling upgrade for indexer cluster
Docs: https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Searchablerollingupgrade#Perform_a_rolling_upgrade

Initiate the rolling upgrade
```
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='upgrade-init cluster-peers'"
```

Take the first node offline

```
ansible-playbook ansible/run_splunk_command.yml --limit idx1 -e "splunk_command='offline'"
```

Wait until the idx is down and check the indexer status with:
```
splunk show cluster-status
```

If the response shows `ReassigningPrimaries`, the peer is not yet shut down.

Upgrade the indexer

```
ansible-playbook ansible/upgrade_splunk.yml --limit idx1
```

Repeat the three last steps for the rest of the indexers

Finalize the upgrade
```
ansible-playbook ansible/run_splunk_command.yml --limit cm -e "splunk_command='upgrade-finalize cluster-peers'"
```
