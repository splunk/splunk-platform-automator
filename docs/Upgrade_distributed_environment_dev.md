# Upgrade steps of a distributed Splunk environment

## This example upgrades from 7.1.x with rolling upgrades

- Edit splunk_config.yml to have the new splunk_version
- Make sure the binaries are download to the Software directory

### Upgrade the Cluster Master

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
Docs: https://docs.splunk.com/Documentation/Splunk/8.1.5/Indexer/Searchablerollingupgrade#Perform_a_rolling_upgrade

### Prework and Preflight checks

Check captain
```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='show shcluster-status'"
```

Switch Captain to last node in the cluster

ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='transfer shcluster-captain -mgmt_uri https://vmsplunksh91p03.mz.admin.ch:8089'"

Check Indexer Cluster status

```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='show cluster-status --verbose'"
```

Note: Look for this line: Pre-flight check successful .................. YES

Initialize Rolling Upgrade

```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='upgrade-init shcluster-members'"
```

### Node Upgrade steps

Put node in manual detention

```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='edit shcluster-config -manual_detention on'"
```

Check if all searches are finished on the SHC Member

```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='list shcluster-member-info'"
```

Output should be:
```
active_historical_search_count:0
active_realtime_search_count:0
```

Upgrade node and remove manual detention
```
ansible-playbook ansible/upgrade_splunk.yml --limit vmsplunksh91p01.mz.admin.ch
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='edit shcluster-config -manual_detention off'"
```

Check cluster health
```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='show shcluster-status --verbose'"
```

Repeat the upgrade steps for the rest of the nodes

Node 2:
```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p02.mz.admin.ch -e "splunk_command='edit shcluster-config -manual_detention on'"
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p02.mz.admin.ch -e "splunk_command='list shcluster-member-info'"
ansible-playbook ansible/upgrade_splunk.yml --limit vmsplunksh91p02.mz.admin.ch
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p02.mz.admin.ch -e "splunk_command='edit shcluster-config -manual_detention off'"
```

Node 3:
```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='edit shcluster-config -manual_detention on'"
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='disable webserver'"
ansible-playbook ansible/restart_splunk.yml --limit vmsplunksh91p03.mz.admin.ch
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='list shcluster-member-info'"
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='enable webserver'"
ansible-playbook ansible/upgrade_splunk.yml --limit vmsplunksh91p03.mz.admin.ch
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='edit shcluster-config -manual_detention off'"
```

Check SHCluster and KV Store Status
```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='show shcluster-status'"
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p03.mz.admin.ch -e "splunk_command='show kvstore-status'"
```


### Upgrade the Deployer

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_deployer
```

### Finalize the SHC upgrade

```
ansible-playbook ansible/run_splunk_command.yml --limit vmsplunksh91p01.mz.admin.ch -e "splunk_command='upgrade-finalize shcluster-members'"
```

### Upgrade all the single node SHs

tbd


## Rolling upgrade for indexer cluster
Docs: https://docs.splunk.com/Documentation/Splunk/latest/Indexer/Searchablerollingupgrade#Perform_a_rolling_upgrade

### Prework and Preflight checks

Check Indexer Cluster status

```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='show cluster-status --verbose'"
```

Initiate the rolling upgrade
```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='upgrade-init cluster-peers'"
```

### Upgrade first indexer

Take the first node offline

```
ansible-playbook ansible/run_splunk_command.yml --limit pssplunk91p01.mz.admin.ch -e "splunk_command='offline'"
```

Wait until the idx is down and check the indexer status with:
```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='show cluster-status'"
```

If the response shows `ReassigningPrimaries`, the peer is not yet shut down.

Upgrade the indexer

```
ansible-playbook ansible/upgrade_splunk.yml --limit pssplunk91p01.mz.admin.ch
```

### Repeat the upgrade steps for the rest of the indexers

```
ansible-playbook ansible/run_splunk_command.yml --limit pssplunk91p02.mz.admin.ch -e "splunk_command='offline'"
ansible-playbook ansible/upgrade_splunk.yml --limit pssplunk91p02.mz.admin.ch
```

```
ansible-playbook ansible/run_splunk_command.yml --limit pssplunk91p03.mz.admin.ch -e "splunk_command='offline'"
ansible-playbook ansible/upgrade_splunk.yml --limit pssplunk91p03.mz.admin.ch
```

```
ansible-playbook ansible/run_splunk_command.yml --limit pssplunk91p04.mz.admin.ch -e "splunk_command='offline'"
ansible-playbook ansible/upgrade_splunk.yml --limit pssplunk91p04.mz.admin.ch
```

### Finalize the upgrade

```
ansible-playbook ansible/run_splunk_command.yml --limit role_cluster_master -e "splunk_command='upgrade-finalize cluster-peers'"
```

## Upgrade Heavy Forwarders

```
ansible-playbook ansible/upgrade_splunk.yml --limit role_heavy_forwarder
```

## Upgrade Intermediate Universal Forwarders

tbd: maybe in serial mode

```
ansible-playbook ansible/upgrade_splunk.yml --limit edavmp01515.eda.edaad.admin.ch
```