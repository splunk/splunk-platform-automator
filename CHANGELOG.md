Splunkenizer changes by release
===============================

## 1.3devel - ongoing



### Fixes

* Enable systemd-managed by default with Splunk 7.3.x
* Fixes broken universal forwarder install with 7.3.x
* Fixed search head cluster setup for 7.3.x

## 1.2 - 2019-06-02

* Added option to run ansible independent from vagrant.
  * Create VM first without Ansible and run playbooks in parallel on the nodes. See [README.md](README.md#optional-but-recommended-create-vm-first-without-ansible-and-run-playbooks-in-parallel-on-the-nodes)
  * More modularization in the code and playbooks
  * Added playbook to remove the Splunk installation from nodes
  * Added playbooks to stop/start/restart splunk
  * Added playbook to uninstall the splunk software along with THP and ulimit settings
  * Added playbook to run splunk commands
  * Added playbook to upgrade the Splunk software (not cluster aware)
* Support native systemd support introduced with Splunk Version 7.2.2
  * Added ulimit settings to native systemd service file
  * Create policy kit rule if systemd version 226 is available
  * Support polkit version 0.105 policy file.
  * Create suoders file as workaround to allow splunk user restart splunk service, if systemd version is too low.
* Added support for Ansible versions 2.7.x and removed Ansible version check
* Added support for Ansible versions 2.8.x
* Update permissions of comment macro to be global
* Moved python install on ubuntu to splunk_config file
* Added option 'idxc_discovery_password' to setup indexer discovery
* Support for multiple license files
* Add option general.url_locale (ex. en-US) to be added in index.html
* Added options to turn off login page info (ex. in AWS)
* Added options to force inventory name set as serverName and/or host (ex. in AWS)
* Added option to set os hostname (ex. in AWS)
* Support for windows virtual machine setup in Virtualbox
  * Installation and configuration of windows universal forwarder (deployment server needed for now)

### Fixes

* Fixed 'vbguest' error, when using AWS only
* Fixed some base_config installations on single node configs with additional roles
* Disable time sync cron for AWS by default

## 1.1.1 - 2018-10-18

* Optimized network config file upates for AWS instances

### Fixes

* Fixed SHC setup for Splunk 7.2
* Fixed updating the index.html, after restart AWS instances

## 1.1 - 2018-10-08

* Added support for Ansible versions 2.5.x and 2.6.x
* Added support for creating virtual machines in the Amazon Cloud (AWS)
* Replaced internal hosts file maintenance with the vagrant hostmanager plugin
* Improved standalone Ansible playbook usage
* Added option to download splunk binaries from splunk.com during install
* Added hf_host field to heavy_forwarder
* Added feature to save a copy of the base_config apps on the Ansible host

### Fixes

* Removed locale (en_GB) in the links of node link page (index.html)
* Fixed wrong systemd service name for universal forwarder
* Removed Deployment Server from serverclasses whitelists
* Do not install splk_all_forwarder_outputs on a single box, when adding LM, MC roles

## 1.0 - 2018-05-21

* Support hashed config values for cluster and ssl cert passwords
* Support for using the same splunk.secret file
* Support new password policy of Splunk 7.1 during install
* Reworked shcluster setup. Better support for adding shc nodes.
* Allow Splunk Version 'latest' to use the latest found splunk version in the directory
* Support for single node system
* Using systemd for splunk services, where available
* Timezone taken from vagrant host per default
* Support Ubuntu
* Support index volume definitions
* Support to use Ansible playbooks without vagrant
* Support ssl for splunk web (including custom certs)
* Support ssl for forwarder->indexer communicaion (including custom certs)

### Fixes

* Remove deployment server from the host lists generated for serverclasses
* Allow fgdn hosts
* Added missing org_search_volume_indexes to DS
* Added org_all_search_base to all roles with web enabled

## 0.9 - 2018-02-09

* Removed [splunk_env_name:vars] from the ansible inventory
* Added time sync workaround for the clock skew without virtualbox additions
* Configuration variables can now also be set on splunk_hosts level
  * Ansible vars are configurable in the config file (ex. skip_tags)
  * Allow to install additional os packages
* Make 'org_' for apps changeable, does set to splunk_env_name
* Make destname for apps changeable (ex. org_site_n_indexer_base)
* Added single indexer playbook, forwarding config to it not yet implemented
* Added ansible.cfg to turn off deprecation warnings on ansible 2.4+
* Add note about hostname, roles, user/pw on login page
* Simplifyed the configuration file. Established default values for most of the settings
* Support multiple indexer clusters in org_all_forwarder_outputs (use idxc name in stanza)
* Allow mixed splunk versions. Can be set per splunk_env or host level
* Reworked outputs and search_peer configuration
* Support single indexers
* Support single search heads
* Create HTML link page for all roles

### Fixes

* not all apps on single search head are deployed from deployment server
* add tags to the dserver and serverclass tasks
* volume and indexes should be deployed to single search head (create serverclass)
* org_all_forwarder_outputs should output to all indexers. does only use first cluster in multicluster config

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
