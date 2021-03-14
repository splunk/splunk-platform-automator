# Splunkenizer 2.0 (Beta)

![Splunkenizer Overview](https://github.com/splunkenizer/Splunkenizer/blob/master/pic/splunkenizer_overview.png)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Ever wanted to build a complex Splunk environment for testing, which looks as close as possible to a production deployment? Need to test a Splunk upgrade? See how Splunk indexer- or search head clustering works? Or just need to verify some configuration changes? This is the right place for you! The aim of this framework is to produce a Splunk environment in a fast and convenient way for testing purposes or maybe also for production use. The created Splunk installation and setup follows best practices using base config apps from Splunk. There are many ways to configure a Splunk environment, in terms of configuration file locations, so this is just another example how to do it.

## Table of Contents

- [Splunkenizer 2.0 (Beta)](#splunkenizer-20-beta)
  - [Table of Contents](#table-of-contents)
- [Support](#support)
- [Features](#features)
  - [Roadmap](#roadmap)
  - [Changelog](#changelog)
- [Installation](#installation)
  - [Framework Installation (Mac OSX)](#framework-installation-mac-osx)
  - [Install Virtualbox support (optional)](#install-virtualbox-support-optional)
  - [Install and configure AWS support (optional)](#install-and-configure-aws-support-optional)
    - [Example Basic AWS Security Group](#example-basic-aws-security-group)
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
  - [Deploying on Amazon Cloud](#deploying-on-amazon-cloud)
  - [Ansible playbooks only](#ansible-playbooks-only)
    - [inventory configuration](#inventory-configuration)
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

## Framework Installation (Mac OSX)

1. Download and install [Vagrant](https://www.vagrantup.com).
1. Install the hostmanager plugin for Vagrant: `vagrant plugin install vagrant-hostmanager`
1. Install Ansible, I personally prefer [Brew](https://brew.sh) which makes it as easy as `brew install ansible`. For [supported Ansible versions check here](#supported-ansible-versions)
1. Create a folder called `Vagrant` and change into it.
1. Download and extract a [Splunkenizer release here](https://github.com/splunkenizer/Splunkenizer/releases) or clone from GitHub when using the master branch: `git clone https://github.com/splunkenizer/Splunkenizer.git`
1. Create a folder called `Software`.
1. Download the tgz. archive for the Splunk Software and put in the `Software` directory
   1. [Splunk Enterprise](http://www.splunk.com/en_us/download/splunk-enterprise.html)
   1. [Splunk Universal Forwarder](http://www.splunk.com/en_us/download/universal-forwarder.html)
1. Download Splunk Professional Services Best Practices Base Config Apps and extract them into the `Software` directory
   1. [Configurations Base Apps](https://drive.google.com/open?id=107qWrfsv17j5bLxc21ymTagjtHG0AobF)
   1. [Configurations Cluster Apps](https://drive.google.com/open?id=10aVQXjbgQC99b9InTvncrLFWUrXci3gz)
1. If you have a Splunk License file, link it to the name `Splunk_Enterprise.lic` inside the `Software` directory.

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

## Install and configure AWS support (optional)

1. Install the aws vagrant plugin: `vagrant plugin install vagrant-aws`
1. Download the vagrant dummy box for aws: `vagrant box add aws-dummy https://github.com/mitchellh/vagrant-aws/raw/master/dummy.box`
1. Generate AWS ACCESS Keys, described [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html#cli-configure-quickstart-creds)
1. Optional, but recommended:
   1. Add AWS_ACCESS_KEY_ID=<your access key ID> as environment variable
   1. Add AWS_SECRET_ACCESS_KEY=<your secret access key> as environment variable
1. Create an ssh key pair described [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair) and store the public key on your disk for later reference in the config file
1. Create an AWS [security group](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-network-security.html#vpc-security-groups) and name it for example 'Splunk' and add the following TCP ports

### Example Basic AWS Security Group

| Type       | Protocol | Port Range | Source        | Description                |
| ---------- | -------- | ---------- | ------------- | -------------------------- |
| All TCP    | TCP      | 0 - 65535  | 172.31.0.0/16 | Allow all internal traffic |
| Custom TCP | TCP      | 8000       | 0.0.0.0/0     | Splunk Web Interface       |
| SSH        | TCP      | 22         | 0.0.0.0/0     | SSH to all hosts           |

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
vagrant scp <file> <hostname>:/destdir
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

You can also use the ansible playbooks without vagrant. For that you have to creare your virtual or physical machines by other means. You can use the ansible playbooks to
deploy the Splunk roles onto the existing servers. You can specify the hostnames in the `splunk_config.yml` files `splunk_hosts` section.
Ansible need to know, where to connect to via ssh to run the playbooks. For this you need to provide create some configs in the `inventory` folder.

### inventory configuration

TBD

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
:white_check_mark: Ansible 3.x

# Authors

Splunkenizer is created by [Marco Stadler](https://github.com/splunkenizer) - a passionate Splunker.

# License

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

See [COPYING](COPYING) to see the full text.
