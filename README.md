# Splunkenizer 2.2.0-devel

![Splunkenizer Overview](https://github.com/splunkenizer/Splunkenizer/blob/master/pic/splunkenizer_overview.png)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](#license)

Ever wanted to build a complex Splunk environment for testing, which looks as close as possible to a production deployment? Need to test a Splunk upgrade? See how Splunk indexer- or search head clustering works? Or just need to verify some configuration changes? This is the right place for you! The aim of this framework is to produce a Splunk environment in a fast and convenient way for testing purposes or maybe also for production use. The created Splunk installation and setup follows best practices. There are many ways to configure a Splunk environment in terms of configuration file locations, so this is just another example how to do it.

## Table of Contents

- [Splunkenizer 2.2.0-devel](#splunkenizer-220-devel)
  - [Table of Contents](#table-of-contents)
- [Support](#support)
- [Features](#features)
  - [Roadmap](#roadmap)
  - [Changelog](#changelog)
- [Installation](#installation)
  - [Framework Installation](#framework-installation)
  - [Install Virtualbox support (optional)](#install-virtualbox-support-optional)
  - [Setup Windows Subsystem for Linux (WSL2)](#setup-windows-subsystem-for-linux-wsl2)
  - [Install and configure AWS support (optional)](#install-and-configure-aws-support-optional)
    - [Example Basic AWS Security Group 'Splunk_Basic'](#example-basic-aws-security-group-splunk_basic)
      - [Inbound Rules](#inbound-rules)
      - [Outbound Rules](#outbound-rules)
- [Upgrade](#upgrade)
  - [Migrate existing Splunkenizer Environments from 1.x to 2.x](#migrate-existing-splunkenizer-environments-from-1x-to-2x)
    - [Migrate splunk_config.yml](#migrate-splunk_configyml)
    - [Migrate Virtualbox Environments](#migrate-virtualbox-environments)
    - [Migrate AWS Environments](#migrate-aws-environments)
    - [Migrate Environments where ansible only is used](#migrate-environments-where-ansible-only-is-used)
- [Building Windows Virtual Machine Template](#building-windows-virtual-machine-template)
- [Framework Usage](#framework-usage)
  - [First start and initialization](#first-start-and-initialization)
  - [Copy a configuration file](#copy-a-configuration-file)
  - [Start the deployment](#start-the-deployment)
    - [Create the Virtual Machines](#create-the-virtual-machines)
    - [Run Ansible playbooks to deploy and configure the Splunk software](#run-ansible-playbooks-to-deploy-and-configure-the-splunk-software)
  - [Stop hosts](#stop-hosts)
  - [Destroy hosts](#destroy-hosts)
  - [Rerun provisioning](#rerun-provisioning)
  - [Login to the hosts](#login-to-the-hosts)
    - [Login to Splunk Browser Interface](#login-to-splunk-browser-interface)
    - [Login by SSH](#login-by-ssh)
  - [Environment Users](#environment-users)
    - [User vagrant](#user-vagrant)
    - [User splunk](#user-splunk)
  - [Copy files](#copy-files)
    - [scp example](#scp-example)
  - [Deploying on Amazon Cloud](#deploying-on-amazon-cloud)
  - [Ansible playbooks only](#ansible-playbooks-only)
  - [Create vitualenv for specific Ansible version](#create-vitualenv-for-specific-ansible-version)
- [Known issues, limitations](#known-issues-limitations)
  - [Supported Ansible Versions](#supported-ansible-versions)
- [Authors](#authors)
- [License](#license)

# Support

**Note: This framework is not officially supported by Splunk. I am developing this on best effort in my spare time.**

# Features

- Build complex, reproducible Splunk environments in one shot, including all roles available for Splunk Enterprise.
- Building Cluster Master, Indexer Clusters, Deployer, Search Head Clusters, Deployment Server, Universal Forwarders, Heavy Forwarders, License Master and Monitoring Console. All ready to use.
- Configuration done according best practices with configuration apps
- Splunk environment definition stored in one simple [yaml](http://docs.ansible.com/ansible/latest/YAMLSyntax.html) file
- [Example configuration files](examples) for different setups included
- Deployment and configuration done with [Ansible](https://www.ansible.com)
- Virtual hosts can be created by [Vagrant](https://www.vagrantup.com)
  - Currently supports [Virtualbox](https://www.virtualbox.org) or [AWS Cloud](https://aws.amazon.com).
- Can deploy Splunk on existing hosts (virtual or physical)
- Developed and tested on MacOSX but should support Linux as well.

## Roadmap

See the upcoming features in the [Roadmap](ROADMAP.md)

## Changelog

Implemented changes are to be found in the [Changelog](CHANGELOG.md)

# Installation

The Framework is currently tested on Mac OSX and Linux, but any other Unix, which is supported by Virtualbox, should work too.

## Framework Installation

1. Download and install [Vagrant](https://www.vagrantup.com).
2. Install Ansible, I personally prefer [Brew](https://brew.sh) (on OSX) which makes it as easy as `brew install ansible`. For [supported Ansible versions check here](#supported-ansible-versions)
3. Create a folder called `Vagrant` and change into it.
4. Download and extract a [Splunkenizer release here](https://github.com/splunkenizer/Splunkenizer/releases) or clone from GitHub when using the master branch: `git clone https://github.com/splunkenizer/Splunkenizer.git`
5. Create a folder called `Software`.
6. Download the tgz. archive for the Splunk Software and put in the `Software` directory
   1. [Splunk Enterprise](http://www.splunk.com/en_us/download/splunk-enterprise.html)
   2. [Splunk Universal Forwarder](http://www.splunk.com/en_us/download/universal-forwarder.html)
7. Download Splunk Professional Services Best Practices Base Config Apps and extract them into the `Software` directory
   1. [Configurations Base Apps](https://drive.google.com/open?id=107qWrfsv17j5bLxc21ymTagjtHG0AobF)
   2. [Configurations Cluster Apps](https://drive.google.com/open?id=10aVQXjbgQC99b9InTvncrLFWUrXci3gz)
8. If you have a Splunk License file, link it to the name `Splunk_Enterprise.lic` inside the `Software` directory.

Your directory structure should now look like this:

```
./Vagrant/Splunkenizer/...
./Vagrant/Software/Configurations - Base/...
./Vagrant/Software/Configurations - Index Replication/...
./Vagrant/Software/splunk-8.1.2-545206cc9f70-Linux-x86_64.tgz
./Vagrant/Software/splunkforwarder-8.1.2-545206cc9f70-Linux-x86_64.tgz
./Vagrant/Software/Splunk_Enterprise.lic
```

## Install Virtualbox support (optional)

1. Download and install [Virtualbox](https://www.virtualbox.org/wiki/Downloads).
1. Install the Virtualbox plugin for Vagrant: `vagrant plugin install vagrant-vbguest`

## Setup Windows Subsystem for Linux (WSL2)

The [Windows Subsystem for Linux](https://docs.microsoft.com/en-us/windows/wsl/install-win10) does allow to run Splunkenizer on Windows. It even allows to create virtualbox hosts from it on the windows host directly.

Execute the steps [above](#framework-installation). To allow vagrant to talk to virtualbox follow the steps below.

- Create /etc/wsl.conf and reboot WSL (`wsl --shutdown`)

```
[automount]
options = "metadata"
```

- Enable WSL2 port forwarding by installing a vagrant plugin with: `vagrant plugin install virtualbox_WSL2`
- Add Environment Variables in WSL (maybe to your `~/.bashrc`)

```
export VAGRANT_WSL_ENABLE_WINDOWS_ACCESS="1"
export PATH="$PATH:/mnt/c/Program Files/Oracle/VirtualBox"
```

## Install and configure AWS support (optional)

1. Install the aws vagrant plugin: `vagrant plugin install vagrant-aws`
1. Download the vagrant dummy box for aws: `vagrant box add aws-dummy https://github.com/mitchellh/vagrant-aws/raw/master/dummy.box`
1. Generate AWS ACCESS Keys, described [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html#cli-configure-quickstart-creds)
1. Optional, but recommended:
   1. Add AWS_ACCESS_KEY_ID=<your access key ID> as environment variable
   1. Add AWS_SECRET_ACCESS_KEY=<your secret access key> as environment variable
1. Create an ssh key pair described [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair) and store the public key on your disk for later reference in the config file
1. Create an AWS [security group](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-network-security.html#vpc-security-groups) and name it for example 'Splunk_Basic' and add the following TCP ports

### Example Basic AWS Security Group 'Splunk_Basic'

#### Inbound Rules

| Type       | Protocol | Port Range | Source        | Description                |
| ---------- | -------- | ---------- | ------------- | -------------------------- |
| All TCP    | TCP      | 0 - 65535  | 172.31.0.0/16 | Allow all internal traffic |
| Custom TCP | TCP      | 8000       | 0.0.0.0/0     | Splunk Web Interface       |
| SSH        | TCP      | 22         | 0.0.0.0/0     | SSH to all hosts           |

#### Outbound Rules

| Type        | Protocol | Port Range | Destination   | Description               |
| ----------- | -------- | ---------- | ------------- | ------------------------- |
| All Traffic | All      | All        | 0.0.0.0/0     | Allow all traffic         |

# Upgrade

To upgrade your Splunkenizer, just update your local code from the repo

```
git pull
```

## Migrate existing Splunkenizer Environments from 1.x to 2.x

From Splunkenizer 2.0 the Framework does use an [Ansible Inventory Plugin](https://docs.ansible.com/ansible/latest/plugins/inventory.html) to build the inventory on the fly during execution. The local `inventory` directory does only hold minimum settings based on the virtualization you choose. The rest calculated in flight and not stored somewhere.

You can verify your inventory with
```
ansible-inventory --list --export
```

### Migrate splunk_config.yml

The steps here apply to all environments.

- You have to add the `plugin` setting to the top of your config file
```
# splunk_config.yml
plugin: splunkenizer
```

### Migrate Virtualbox Environments

The steps here only apply if your current environment is built on virtualbox.

- Cleanup unneeded entries from the ansible inventory
```
rm -rf inventory/group*
```
- Move the setting `start_ip` in the `general` section to the `virtualbox` section.

### Migrate AWS Environments

The steps here only apply if your current environment is built on AWS.

- Cleanup unneeded entries from the ansible inventory
```
rm -rf inventory/*
```
- Build the config/aws_ec2.yml config file
```
vagrant status
```
- Get the GUID from config/aws_ec2.yml at `tag:SplunkEnvID:` and add a tag `SplunkEnvID` to every host in your AWS environment with that GUID
- Create also a tag `SplunkHostname` for every AWS host with the name of your hosts from the splunk_hosts section

If you have the aws cli available, this can be done with the following one liner
```
for machine in $(ls -1d .vagrant/machines/*); do aws ec2 create-tags --resources $(cat $machine/aws/id) --tags Key=SplunkHostname,Value=$(basename $machine) Key=SplunkEnvID,Value=$(grep "tag:SplunkEnvID:" config/aws_ec2.yml | cut -d: -f3 | tr -d " ") Key=Name,Value=$(basename $machine) --no-cli-pager; done
```

### Migrate Environments where ansible only is used

The steps here only apply if your current environment is not built with vagrant.

The process is not so traight forward, since I do not know how you built your ansible inventory. Basically, you have
to make sure everything you defined in your inventory files is reflected in the splunk_config.yml file.

- Before you upgrade your splunkenizer environment, you have to export the inventory to a file
```
ansible-inventory --list --export > inventory_1.txt
```
- Migrate all settings to the splunk_config.yml file
- Remove the complete inventory
```
rm -rf inventory/*
```
- After the upgrade and building of your splunk_config.yml, you can check the new inventory with the `ansible-inventory` command and compare it with your dump from version 1.x

# Building Windows Virtual Machine Template

To build your own windows vagrant image follow [Setup Windows Vagrant image](docs/Setup_Windows_Box.md)

# Framework Usage

## First start and initialization

Run vagrant the first time to initialize itself and create needed directories. You must execute vagrant always in side the Splunkenizer directory where the `Vagrantfile` sits, otherwise it will not work correctly. You will see the usage page, when executing vagrant without options.

```
cd Splunkenizer
vagrant
```

## Copy a configuration file

There is one single configuration file, where all settings for your deployment are defined. Copy one configuration file from the [examples](examples) to `config/splunk_config.yml` and adjust the setting to your needs. For a standard setup you should be fine with most of the default settings, but there are a lot of things you can adjust for special cases. See the [configuration description](examples/configuration_description.yml) file, where all existing values are described.

AWS: See [instruction here](#deploying-on-amazon-cloud) when deploying into Amazon Cloud. You can start with [splunk_config_aws.yml](examples/splunk_config_aws.yml) for a simple environment. Copy `splunk_idxclusters`, `splunk_shclusters` and `splunk_hosts` sections from other examples for more complex deployments.

## Start the deployment

When building virtual machines (for virtualbox) the first time it will pull an os image from the internet. The box images are cached here: `~/.vagrant.d/boxes`.

### Create the Virtual Machines

```
vagrant up
```

### Run Ansible playbooks to deploy and configure the Splunk software 

The `vagrant up` command only creates the virtual machines. To deploy Splunk afterwards, run this command:

```
ansible-playbook ansible/deploy_site.yml
```

To run both steps with one command use:

```
vagrant up; ansible-playbook ansible/deploy_site.yml
```

## Stop hosts

This will gracefully shutdown all the virtual machines.

```
vagrant halt
```

## Destroy hosts

You can destroy all the virtual machines with one command.

```
vagrant destroy [-f] [<hostname>]
```

## Rerun provisioning

Ansible playbooks can be run over and over again. If the virtual machine is already built, you can rerun the playbooks on a certain host again. This can be needed if something fails and you fixed the error.

```
ansible-playbook ansible/deploy_site.yml [--limit <hostname>]
```

## Login to the hosts

### Login to Splunk Browser Interface

To login to one of the hosts just open the `index.html` file created in the Splunkenizer/config directory. You will find links to every role of your deployment.
If something changes along the way and you need to update the linkpage just call this playbook:

```
ansible-playbook ansible/create_linkpage.yml
```


### Login by SSH

Vagrant deployes an ssh key for the vagrant user to login without a password.

```
vagrant ssh <hostname>
```

## Environment Users

### User vagrant

Vagrant uses a dedicated user to work inside the virtual machines. The user name is `vagrant` and has sudo rights to switch to root or other users.

### User splunk

Splunk Enterprise is installed and run as user `splunk`. You can switch to this user by `sudo su - splunk`. For convenience, I have added some command aliases to the user `vagrant` and user `splunk`.

```
alias
```

## Copy files

You can copy files from your host system to the virtual nodes with the vagrant command. You need to install the vagrant plugin `vagrant-scp` to have this feature available. Check [Vagrant Docs](https://www.vagrantup.com/docs/plugins/usage.html) on how to do this.

```
vagrant scp <files> <target_on_dest> [vm_name]
```

### scp example

```
vagrant scp ../app_dir/splunk-add-on-for-unix-and-linux_831.tgz /var/tmp uf
```

## Deploying on Amazon Cloud

Splunkenizer can talk to the AWS cloud and create virtual machines with Splunk in the cloud. Vagrant is using the plugin [vagrant-aws](https://github.com/mitchellh/vagrant-aws) for that. Follow these steps to setup Splunkenizer for AWS. In the example there is a simple network setup, with only one Security group, covering all ports. More complex network setups should be possible, but make sure the host, where Splunkenizer is running does have ssh access to all instances.

To prepare the configuration file for Amazon deployments

- Take the [AWS example](examples/splunk_config_aws.yml) and fill in the values you like in the 'aws' section. You need at least:
  - access_key_id, secret_access_key if not specified as ENV vars.
  - keypair_name
  - ssh_private_key_path
  - security_groups
  - you can use the new 'splunk_download' section in 'splunk_defaults', if you do not want to upload the splunk binaries from your host all the time. This will download them from splunk.com instead.

You can copy splunk_hosts and cluster configs from other example files to the AWS template to create more complex environments. There can be all configuration option used, which are described in the vargant-aws plugin. They can also set individually on the splunk hosts, if needed. Just add a aws: section to the host.

## Ansible playbooks only

You can also use the ansible playbooks without vagrant. For that you have to create your virtual or physical machines by other means. You can use the ansible playbooks to
deploy the Splunk roles onto the existing servers. Specify the hostnames in the `splunk_config.yml` file in the `splunk_hosts` section.
Ansible needs to know where to connect to via ssh to run the playbooks. For this you need to create some custom variables in the 
`splunk_config.yml` file.

As a minimum specify the ssh user for ansible and the ssh private key which has been deployed on the systems. This user must be able to elevate to the `root` user with sudo.

```
custom:
  ansible_user: ansible
  ansible_ssh_private_key_file: '~/.ssh/id_rsa'
```

If you have host specific variables the custom section can also be added on host level. This could be for example `ansible_host` if different from the hostname. Also check [configuration description](examples/configuration_description.yml)

You can verify things like this first with an ansible ping:

```
ansible -m ping all
```

And then some more ansible prerequisites with this playbook
```
ansible-playbook ansible/test_ansible_prereqs.yml
```

## Create vitualenv for specific Ansible version

If you need a specific Ansible version you can create it inside a virtualenv environment. This can
 be useful when deploying older linux images, which too old python versions. 

```
python3 -m venv ansible_490
source ansible_490/bin/activate
python -m pip install ansible==4.9.0 # to have a certain version
```

You must install some additional modules for Splunkenizer to work

```
python -m pip install jmespath # required for json_query calls
python -m pip install lxml     # required for license file checks
python -m pip install boto3    # required for ec2 (aws) plugin
```

Check the ansible version. 

```
ansible --version
```

If the version is not correct, open a new terminal and activate the
virtual environment again with the command from above.

```
source ansible_490/bin/activate
```


# Known issues, limitations

- ulimit settings not working on Ubuntu 14 (without systemd)
- Forwarding data from a universal forwarder to a heavy forwarder cannot be configured in the config file. This must be done manually after installation.
- Virtualbox: Virtual host startup does not respond sometimes, if it fails, recreate the host again.
- Virtualbox has some issues with clock time skew, when not using virtualbox additions. I added a workaround with forcing time clock sync every 5 minutes. A working internet connection on the Virtualbox host is needed.
- AWS: Due to security reasons the login page with the admin password information has been disabled and https is enabled with splunk's own self signed certs.
- AWS: OS images (AMI) do not have ntp configured by default. This will be added in Splunkenizer later.

## Supported Ansible Versions

The following Ansible versions are tested and working with Splunkenizer, but any newer version should work as well.

:white_check_mark: Ansible 2.7.x
:white_check_mark: Ansible 2.8.x
:white_check_mark: Ansible 2.9.x
:white_check_mark: Ansible 2.10.x
:white_check_mark: Ansible 2.11.x
:white_check_mark: Ansible 2.12.x

# Authors

Splunkenizer is created by [Marco Stadler](https://github.com/splunkenizer) - a passionate Splunker.

# License

Copyright 2022 Splunk Inc.
 
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
 
http://www.apache.org/licenses/LICENSE-2.0
 
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. 