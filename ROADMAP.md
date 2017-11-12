# Roadmap

## New Features

Note: The order for implementation may change

* Support single indexers
* Support multiple indexer clusters in org_all_forwarder_outputs (use idxc name in stanza)
* separate output conf on DS for HF, separate cluster, single indexer
* Add note about hostname and roles to login page
* Disable THP in grub config
* allow mixed splunk versions -> add version var at splunk_hosts
* Create HTML link page for all roles
* Support config options for indexes (ex. new metrics index type)
* Make 'org_' for apps changeable
* make ansible vars configurable in the config file (ex. skip_tags)
* Make destname for apps changeable (ex. org_site_n_indexer_base)
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

* Find a propre fix/workaround for the clock skew without virtualbox additions
* org_all_forwarder_outputs should output to all indexers. does only use first cluster in multicluster config
* remove [splunk_env_name:vars] from the ansible inventory
* Better error handling and logic checking for config file
  * Check in Vagrantfile, if listed idxc is defined
* Output of ansible for /etc/hosts has to much in it, find better way

## Low prio, but still worth notable

* Download baseconfigs from internet (https://developer.box.com/docs/)
* Download Splunk from Internet
* Make vagrant user configurable
* Make splunk user configurable
* User vagrant host-manager to update host ips: https://github.com/devopsgroup-io/vagrant-hostmanager https://github.com/akeeba/vagrant/blob/master/Vagrantfile
