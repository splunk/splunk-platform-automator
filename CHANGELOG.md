Splunkenizer Changes By Release
===============================

## 0.9.devel - ongoing

* Removed [splunk_env_name:vars] from the ansible inventory
* Added time sync workaround for the clock skew without virtualbox additions
* Configuration variables can now also be set on splunk_hosts level
  * Ansible vars are configurable in the config file (ex. skip_tags)
  * Allow to install additional os packages

## 0.8 - 2017-11-12

* Check for site affinity in search head clusters
* Install path /opt changeable
* Disable indexing on CM, DS(?), Deployer (check in the cli file) -> done by the forwarder app
* set indexes from all config file
* org_search_volume_indexes on SH
* Check correct usage of ansible vars in when statements
* Set search head cluster label
* org_cluster_search_base needs probably app_path during config on deployer, wrong path used
* sh need splunk restart after cluster init
* Find solution for reboot before bootstrap (if command throws error, reboot and bootstrap)
* tries to add dservers twice on smc, dserver list must be created in a better way, indexer cluster not there
* create hosts file out of inventory of Vagrant file (done from config file)
* make Vagrant file dynamical
* Set role with Vagrant var
* make common main playbook and decide on Vagrant var (done on the config role)
* after shcluster build, bundle push must be performed: splunk apply shcluster-bundle -target https://sh3:8089
* uf is not connecting after install, needs reboot, how to check for it?
* do not add own host to dservers and make the list unique
* Multi site indexer cluster
* single site multiside cluster
* renamed playbooks -> ansible
* probably need to wait until the shcluster has restarted, otherwise bundle deploy can fail
* org_full_license_server should not be installed if role license master (check on cm)
* org_cluster_search_base should not be installed if role is cluster master
* ulimit settings https://docs.splunk.com/Documentation/Splunk/latest/Installation/Systemrequirements#Considerations_regarding_system-wide_resource_limits_on_.2Anix_systems
* THP settings http://docs.splunk.com/Documentation/Splunk/latest/ReleaseNotes/SplunkandTHP
* org_cluster_search_base misses multisite = true if multiside idx cluster
* one more restart for UF
* caclculate idxc_available_sites dynamically and add it to the cluster
* calculate shc_captain dynamically
* Change config to be able to have more than one cluster
* do not provide base_config apps, user must download
* Support multiple cluster masters in org_cluster_search_base (use idxc name in stanza)
* hashed password check must be changed to check inside the cm stanza in org_cluster_search_base on cm
* Add cm as search peer in SMC
* Support single search heads
* don't install relevant baseconfig, if clustermaster, deployment server, monitoring console is not there
* check if full_lic app is created, if license master is not already installed, works :-)
* check if deployment client app is installed, if deployment server is not yet installed, works :-)
* add forward app, if deployment server is missing
* add license client app, if deployment server is missing
* allow relative pathes for software an baseconfigs
* added org_all_search_base
* fix dserver list creation fail, if group was missing
* Output error if license file not there
* Added fix for clock skew on Linux in Virtualbox: https://oitibs.com/fix-virtualbox-guest-time-skew/ (not working, either)
* dserver list does not exclude UF
* Install forward output, if deployer is ds
* Install forward output, if cm is ds
* Create list of license clients in serverclass dynamically
* added new role for heavy forwarder
* cleanup ansible tags
* Calculate /etc/hosts from inventory if possible otherwise from splunk_config
* Single SH does not get license client app -> need to be added automatically in server class
* reload deploy server, if serverclass changes
* fix serverclass whitelisting
* dynamic ip addresses
* use a start_ip for dynamic ips
* update serverclass everytime a server is created
* Check host to be available before adding dserver
* set site0 to cluster masters in the example configs (no site affinity)
* Allow to turn on virtualbox addon installation inside config (disable clock skew fix)
* disable first login page
