# Roadmap

## New Features

Note: The order for implementation may change

* Config options for forwarding to single indexers and heavy forwarders
* separate output conf on DS for HF, separate cluster, single indexer
* Disable THP in grub config
* Support config options for indexes (ex. new metrics index type)
* option to have master_deployment_client or org_all_deploymentclient on cm
* Splunk generic app deployment
  * Add unix_TA: (needs this packages: net-tools lsof sysstat)
  * playbooks for common splunkbase apps
* org_all_deploymentclient for ds -> cm app deployment
* Disable all the tour and other info wizzards after login
* Use custom certs for ssl
* add dns_server role and configure nodes to get the host names from dns
* finish ldap_server role to be usable in Splunk (new config file needed)
* implement config syntax for host series (ex. idx1..16) for mass node deployment
* support docker container as Splunk hosts

## Fixes

* Better error handling and logic checking for config file
  * Check in Vagrantfile, if listed idxc is defined
* Output of ansible for /etc/hosts has to much in it, find better way

## Low prio, but still worth notable

* Download baseconfigs from internet (https://developer.box.com/docs/)
* Download Splunk from Internet
* Make vagrant user configurable
* Make splunk user configurable
* User vagrant host-manager to update host ips: https://github.com/devopsgroup-io/vagrant-hostmanager https://github.com/akeeba/vagrant/blob/master/Vagrantfile
