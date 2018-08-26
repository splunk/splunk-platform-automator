# Roadmap

## New Features

Note: The order for implementation may change

* Add support for Windows hosts with Universal Forwarder
* Config options for forwarding to single indexers and heavy forwarders
* Separate output conf on DS for HF, separate cluster, single indexer
* Support config options for indexes (ex. new metrics index type)
* Option to have master_deployment_client or org_all_deploymentclient on cm
* Splunk generic app deployment
  * Add unix_TA: (needs this packages: net-tools lsof sysstat)
  * playbooks for common splunkbase apps
* org_all_deploymentclient for ds -> cm app deployment
* Disable all the tour and other info wizards after login
* Add dns_server role and configure nodes to get the host names from dns
* Finish ldap_server role to be usable in Splunk (new config file needed)
* Implement config syntax for host series (ex. idx1..16) for mass node deployment
* Support docker container as Splunk hosts

## Fixes

* Better error handling and logic checking for config file
  * Check in Vagrantfile, if listed idxc is defined

## Low prio, but still worth notable

* Download baseconfigs from internet (https://developer.box.com/docs/)
* Make vagrant user configurable
* Make splunk user configurable
* Run Bind server on one node: https://github.com/bertvv/ansible-role-bind
