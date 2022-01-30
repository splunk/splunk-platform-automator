# Splunkenizer changes by release

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/).

## 2.1.0-devel - ongoing

### Changed

- Changed default image for virtualbox to almalinux/8
- Index path settings are defined in the [default] per default. Can be disabled.
- Index definitions at splunk_defaults.splunk_indexes must be in dictionary format
- Changed start_ip for virtualbox, because of new restriction in Vbox 6.1.28

### Added

- Added new splunk_hosts types: list and iter (shorter config for lots of equal nodes)
- Added possibility to set addidional index options
- Added test_metrics index per default
- Added setting `splunk_kv_store_engine_wiredtiger` to disable config (enabled by default)
- Added playbook to run indexer cluster rolling upgrade
- Added playbook to cleanup splunk_backup (etc) archives
- Added playbook to update inputs ssl certificates
- Added playbook to call splunk rest endpoints

### Fixed

- Fail on install if no splunk.secret file is found and more than one host is deployed
- Create auth dir if needed
- Fixed missing bundle push after shc setup
- Fixed boolean comparison for older python versions
- Fixed removed collections.Mapping usage with python 3.10
- Added splunkd full service check during SHC member add. Did run into timeout when having lots of apps.
- Updated URL for downloads of splunk install archives
- Follow symlinks during Splunk archive extraction
- Fixed SPLUNK_HOME ownership, when having it linked to another directory

## [2.0.0](https://github.com/splunkenizer/Splunkenizer/releases/tag/v2.0.0) - 2021-07-27

### Changed

- Never disable SELinux on Universal Forwarders
- start_ip is now part of `virtualbox` section (was in general before)

### Added

- Added ability to add custom ansible variables globally and on host level
- Set storageEngine=wiredTiger on new installs for 8.1+
- Created Ansible inventory plugin (no more `vagrant status` needed to recalculate inventory)
- Create all AWS EC2 instances at the same time. Huge time saver!
- Better error checking in `splunk_config.yml` file
- Added playbook (`create_linkpage.yml`) to update index.html file
- Added disable_apparmor setting to disable AppArmor, if found
- Added pipelining = true to ansible.cfg

### Fixed

- Usage of own certificates for single indexers

### Removed

- Ansible cannot be called from vagrant directly
- Removed dependency to vagrant (Although vagrant does still work!)
- Removed usage of `vagrant-hostmanager` plugin. This plugin can be removed.

## [1.3.0](https://github.com/splunkenizer/Splunkenizer/releases/tag/v1.3.0) - 2021-04-11

### Changed

- New default: Do not run ansible from vagrant
- New default: disable_selinux: true (disables only, if state is 'enforcing')

### Deprecated

- Call ansible from vagrant

### Added

- Added support for SmartStore (S2)
- Install Policy Kit Rules by enable boot-start for 8.1.1+
- Added setting summary_replication = true
- Added Bucket tunings for indexers
- Do not update comment macro permissions for Splunk 8.1+
- Added playbook to update splunk web certs
- Support upgrades to Splunk 8.x
- Allow to set custom config file settings (splunk_conf)
- Option the 'os' section to disable SELinux (needs Ansible 2.7)
- Option to allow maxVolumeDataSizeMB for volumes to be calculated from the available filesystem free space

### Fixed

- Fixed ansible temp_dir warning during splunk download
- Fixed SHC setup for Splunk 8.1.x
- Fixed changed status to be ok for non changing shell and command tasks
- Fixed splunk command calls to run as user splunk instead of root
- Do not deploy org_search_volume_indexes on single node instance
- Fixed search head cluster setup when using own certificates
- Enable systemd-managed by default with Splunk 7.3.x
- Fixes broken universal forwarder install with 7.3.x
- Fixed search head cluster setup for 7.3.x
- Fixed hard coded ansible user home location
- Fixed issue: Special characters in Splunk password #6
- Added workaround for bug in vagrant-aws with vagrant 2.2.7

## [1.2](https://github.com/splunkenizer/Splunkenizer/releases/tag/v1.2) - 2019-06-02

### Added

- Added option to run ansible independent from vagrant.
  - Create VM first without Ansible and run playbooks in parallel on the nodes. See [README.md](README.md#optional-but-recommended-create-vm-first-without-ansible-and-run-playbooks-in-parallel-on-the-nodes)
  - More modularization in the code and playbooks
  - Added playbook to remove the Splunk installation from nodes
  - Added playbooks to stop/start/restart splunk
  - Added playbook to uninstall the splunk software along with THP and ulimit settings
  - Added playbook to run splunk commands
  - Added playbook to upgrade the Splunk software (not cluster aware)
- Support native systemd support introduced with Splunk Version 7.2.2
  - Added ulimit settings to native systemd service file
  - Create policy kit rule if systemd version 226 is available
  - Support polkit version 0.105 policy file.
  - Create suoders file as workaround to allow splunk user restart splunk service, if systemd version is too low.
- Added support for Ansible versions 2.7.x and removed Ansible version check
- Added support for Ansible versions 2.8.x
- Update permissions of comment macro to be global
- Moved python install on ubuntu to splunk_config file
- Added option 'idxc_discovery_password' to setup indexer discovery
- Support for multiple license files
- Add option general.url_locale (ex. en-US) to be added in index.html
- Added options to turn off login page info (ex. in AWS)
- Added options to force inventory name set as serverName and/or host (ex. in AWS)
- Added option to set os hostname (ex. in AWS)
- Support for windows virtual machine setup in Virtualbox
  - Installation and configuration of windows universal forwarder (deployment server needed for now)

### Fixed

- Fixed 'vbguest' error, when using AWS only
- Fixed some base_config installations on single node configs with additional roles
- Disable time sync cron for AWS by default

## [1.1.1](https://github.com/splunkenizer/Splunkenizer/releases/tag/v1.1.1) - 2018-10-18

### Changed

- Optimized network config file upates for AWS instances

### Fixed

- Fixed SHC setup for Splunk 7.2
- Fixed updating the index.html, after restart AWS instances

## [1.1](https://github.com/splunkenizer/Splunkenizer/releases/tag/v1.1) - 2018-10-08

### Added

- Added support for Ansible versions 2.5.x and 2.6.x
- Added support for creating virtual machines in the Amazon Cloud (AWS)
- Replaced internal hosts file maintenance with the vagrant hostmanager plugin
- Improved standalone Ansible playbook usage
- Added option to download splunk binaries from splunk.com during install
- Added hf_host field to heavy_forwarder
- Added feature to save a copy of the base_config apps on the Ansible host

### Fixed

- Removed locale (en_GB) in the links of node link page (index.html)
- Fixed wrong systemd service name for universal forwarder
- Removed Deployment Server from serverclasses whitelists
- Do not install splk_all_forwarder_outputs on a single box, when adding LM, MC roles

## [1.0](https://github.com/splunkenizer/Splunkenizer/releases/tag/v1.0) - 2018-05-21

### Added

- Support hashed config values for cluster and ssl cert passwords
- Support for using the same splunk.secret file
- Support new password policy of Splunk 7.1 during install
- Reworked shcluster setup. Better support for adding shc nodes.
- Allow Splunk Version 'latest' to use the latest found splunk version in the directory
- Support for single node system
- Using systemd for splunk services, where available
- Timezone taken from vagrant host per default
- Support Ubuntu
- Support index volume definitions
- Support to use Ansible playbooks without vagrant
- Support ssl for splunk web (including custom certs)
- Support ssl for forwarder->indexer communicaion (including custom certs)

### Fixed

- Remove deployment server from the host lists generated for serverclasses
- Allow fgdn hosts
- Added missing org_search_volume_indexes to DS
- Added org_all_search_base to all roles with web enabled

## [0.9](https://github.com/splunkenizer/Splunkenizer/releases/tag/v0.9) - 2018-02-09

### Added

- Added time sync workaround for the clock skew without virtualbox additions
- Configuration variables can now also be set on splunk_hosts level
  - Ansible vars are configurable in the config file (ex. skip_tags)
  - Allow to install additional os packages
- Make 'org_' for apps changeable, does set to splunk_env_name
- Make destname for apps changeable (ex. org_site_n_indexer_base)
- Added single indexer playbook, forwarding config to it not yet implemented
- Added ansible.cfg to turn off deprecation warnings on ansible 2.4+
- Add note about hostname, roles, user/pw on login page
- Support multiple indexer clusters in org_all_forwarder_outputs (use idxc name in stanza)
- Allow mixed splunk versions. Can be set per splunk_env or host level
- Support single indexers
- Support single search heads
- Create HTML link page for all roles

### Removed

- Removed [splunk_env_name:vars] from the ansible inventory

### Changed

- Simplifyed the configuration file. Established default values for most of the settings
- Reworked outputs and search_peer configuration

### Fixed

- not all apps on single search head are deployed from deployment server
- add tags to the dserver and serverclass tasks
- volume and indexes should be deployed to single search head (create serverclass)
- org_all_forwarder_outputs should output to all indexers. does only use first cluster in multicluster config

## [0.8](https://github.com/splunkenizer/Splunkenizer/releases/tag/v0.8) - 2017-11-12

- Check for site affinity in search head clusters
- Install path /opt changeable
- Disable indexing on CM, DS(?), Deployer (check in the cli file) -> done by the forwarder app
- set indexes from all config file
- org_search_volume_indexes on SH
- Check correct usage of ansible vars in when statements
- Set search head cluster label
- org_cluster_search_base needs probably app_path during config on deployer, wrong path used
- sh need splunk restart after cluster init
- Find solution for reboot before bootstrap (if command throws error, reboot and bootstrap)
- tries to add dservers twice on smc, dserver list must be created in a better way, indexer cluster not there
- create hosts file out of inventory of Vagrant file (done from config file)
- make Vagrant file dynamical
- Set role with Vagrant var
- make common main playbook and decide on Vagrant var (done on the config role)
- after shcluster build, bundle push must be performed: splunk apply shcluster-bundle -target https://sh3:8089
- uf is not connecting after install, needs reboot, how to check for it?
- do not add own host to dservers and make the list unique
- Multi site indexer cluster
- single site multiside cluster
- renamed playbooks -> ansible
- probably need to wait until the shcluster has restarted, otherwise bundle deploy can fail
- org_full_license_server should not be installed if role license master (check on cm)
- org_cluster_search_base should not be installed if role is cluster master
- ulimit settings https://docs.splunk.com/Documentation/Splunk/latest/Installation/Systemrequirements#Considerations_regarding_system-wide_resource_limits_on_.2Anix_systems
- THP settings http://docs.splunk.com/Documentation/Splunk/latest/ReleaseNotes/SplunkandTHP
- org_cluster_search_base misses multisite = true if multiside idx cluster
- one more restart for UF
- caclculate idxc_available_sites dynamically and add it to the cluster
- calculate shc_captain dynamically
- Change config to be able to have more than one cluster
- do not provide base_config apps, user must download
- Support multiple cluster masters in org_cluster_search_base (use idxc name in stanza)
- hashed password check must be changed to check inside the cm stanza in org_cluster_search_base on cm
- Add cm as search peer in SMC
- Support single search heads
- don't install relevant baseconfig, if clustermaster, deployment server, monitoring console is not there
- check if full_lic app is created, if license master is not already installed, works :-)
- check if deployment client app is installed, if deployment server is not yet installed, works :-)
- add forward app, if deployment server is missing
- add license client app, if deployment server is missing
- allow relative pathes for software an baseconfigs
- added org_all_search_base
- fix dserver list creation fail, if group was missing
- Output error if license file not there
- Added fix for clock skew on Linux in Virtualbox: https://oitibs.com/fix-virtualbox-guest-time-skew/ (not working, either)
- dserver list does not exclude UF
- Install forward output, if deployer is ds
- Install forward output, if cm is ds
- Create list of license clients in serverclass dynamically
- added new role for heavy forwarder
- cleanup ansible tags
- Calculate /etc/hosts from inventory if possible otherwise from splunk_config
- Single SH does not get license client app -> need to be added automatically in server class
- reload deploy server, if serverclass changes
- fix serverclass whitelisting
- dynamic ip addresses
- use a start_ip for dynamic ips
- update serverclass everytime a server is created
- Check host to be available before adding dserver
- set site0 to cluster masters in the example configs (no site affinity)
- Allow to turn on virtualbox addon installation inside config (disable clock skew fix)
- disable first login page
