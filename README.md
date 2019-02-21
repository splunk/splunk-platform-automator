
![Splunkenizer Overview](https://github.com/splunkenizer/Splunkenizer/blob/master/pic/splunkenizer_overview.png)



# Splunkenizer

Ever wanted to build a complex Splunk environment for testing, which looks as close as possible to a production deployment? Need to test a Splunk upgrade? See how Splunk indexer- or search head clustering works? Or just need to verify some configuration changes? This is the right place for you! The aim of this framework is to produce a Splunk environment in a fast and convenient way for testing purposes or maybe also for production use. The created Splunk installation and setup follows best practices using base config apps from Splunk. There are many ways to configure a Splunk environment, in terms of configuration file locations, so this is just another example how to do it.

## Table of Contents

   * [Splunkenizer](#splunkenizer)
   * [Support](#support)
   * [Features](#features)
      * [Roadmap](#roadmap)
      * [Changelog](#changelog)
   * [Installation](#installation)
      * [Framework Installation (Mac OSX)](#framework-installation-mac-osx)
      * [Install Virtualbox support (optional)](#install-virtualbox-support-optional)
      * [Install and configure AWS support (optional)](#install-and-configure-aws-support-optional)
   * [Framework Usage](#framework-usage)
      * [First start and initialization](#first-start-and-initialization)
      * [Copy a configuration file](#copy-a-configuration-file)
      * [Start the deployment](#start-the-deployment)
         * [Experimental: Create VM first without Ansible and run playbooks in parallel on the nodes](#experimental-create-vm-first-without-ansible-and-run-playbooks-in-parallel-on-the-nodes)
      * [Stop hosts](#stop-hosts)
      * [Destroy hosts](#destroy-hosts)
      * [Rerun provisioning](#rerun-provisioning)
      * [Login to the hosts](#login-to-the-hosts)
         * [Login to Splunk Browser Interface](#login-to-splunk-browser-interface)
         * [Login by SSH](#login-by-ssh)
      * [Environment Users](#environment-users)
         * [User vagrant](#user-vagrant)
         * [User splunk](#user-splunk)
      * [Copy files](#copy-files)
      * [Deploying on Amazon Cloud](#deploying-on-amazon-cloud)
      * [Ansible playbooks only](#ansible-playbooks-only)
   * [Known issues, limitations](#known-issues-limitations)
      * [Supported Ansible Versions](#supported-ansible-versions)
   * [Authors](#authors)
   * [License](#license)

# Support

**Note: This framework is not officially supported by Splunk. I develop this on best effort in my spare time.**

# Features

* Build complex, reproducible Splunk environments in one shot, including all roles available for Splunk Enterprise.
* Building Cluster Master, Indexer Clusters, Deployer, Search Head Clusters, Deployment Server, Universal Forwarders, Heavy Forwarders, License Master and Monitoring Console. All ready to use.
* Configuration done according best practices with configuration apps
* Splunk environment definition stored in one simple [yaml](http://docs.ansible.com/ansible/latest/YAMLSyntax.html) file
* [Example configuration files](examples) for different setups included
* Deployment and configuration done with [Ansible](https://www.ansible.com)
* Controlled by [Vagrant](https://www.vagrantup.com)
* Virtualized by [Virtualbox](https://www.virtualbox.org) or in [AWS Cloud](https://aws.amazon.com). It can be extended to other technologies like VMWare, Docker and such in the future.
* Tested on MacOSX and Linux as vagrant and virtualbox host

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
1. The configuration is based on the Splunk Professional Services Best Practices Base Config Apps. Unfortunately, they are not publicly available anymore. Please contact Splunk Professional Services to have copy of them.
   1. Configurations Base Apps
   1. Configurations Cluster Apps
1. If you have a Splunk License file, link it to the name `Splunk_Enterprise.lic` inside the `Software` directory.

Your directory structure should now look like this:

```
./Vagrant/Splunkenizer/...
./Vagrant/Software/Configurations - Base/...
./Vagrant/Software/Configurations - Index Replication/...
./Vagrant/Software/splunk-7.1.1-8f0ead9ec3db-Linux-x86_64.tgz
./Vagrant/Software/splunkforwarder-7.1.1-8f0ead9ec3db-Linux-x86_64.tgz
./Vagrant/Software/Splunk_Enterprise.lic
```

## Install Virtualbox support (optional)

1. Download and install [Virtualbox](https://www.virtualbox.org/wiki/Downloads).
1. Install the Virtualbox plugin for Vagrant: `vagrant plugin install vagrant-vbguest`

## Install and configure AWS support (optional)

1. Install the aws vagrant plugin: `vagrant plugin install vagrant-aws`
1. Download the vagrant dummy box for aws: `vagrant box add aws-dummy https://github.com/mitchellh/vagrant-aws/raw/master/dummy.box`
1. Generate AWS ACCESS Keys, described [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html)
1. Optional, but recommended:
   1. Add AWS_ACCESS_KEY_ID=<your access key ID> as environment variable
   1. Add AWS_SECRET_ACCESS_KEY=<your secret access key> as environment variable
1. Create an ssh key pair described [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair) and store the public key on your disk for later reference in the config file
1. Create an AWS [security group](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-network-security.html#vpc-security-groups) and name it ex. Splunk and add the following TCP incoming ports: 22,8000,9887,8191,8065,8089,9997-9998

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

```
vagrant up
```

### Experimental: Create VM first without Ansible and run playbooks in parallel on the nodes
Since Splunkenizer can be used for existing servers as well, the creation of the virtual machines and the installation/configuration of Splunk will be separated in future versions. I started this in the code now and you can already make use of this to speed up the process even more.

To disable running Ansible from vagrant directly, touch this file:

```
touch config/no_vagrant_ansible
```

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
Ansible playbooks can be run over and over again. IF the virtual machine is already built and you need to start the playbooks on a certain host, you can call the provisioner again. This can be needed if something fails and you fixed the error.

```
vagrant provision <hostname>
```

## Login to the hosts

### Login to Splunk Browser Interface
To login to one of the hosts just open the `index.html` file created in the Splunkenizer/config directory. You will find links to every role of your deployment.

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

* Take the [AWS example](examples/splunk_config_aws.yml) and fill in the values you like in the 'aws' section. You need at least:
   * access_key_id, secret_access_key if not specified as ENV vars.
   * keypair_name
   * ssh_private_key_path
   * security_groups
   * you can use the new 'splunk_download' section in 'splunk_defaults', if you do not want to upload the splunk binaries from your host all the time. This will download them from splunk.com instead.

You can copy splunk_hosts and cluster configs from other example files to the AWS template to create more complex environments. There can be all configuration option used, which are described in the vargant-aws plugin. They can also set individually on the splunk hosts, if needed. Just add a aws: section to the host.

## Ansible playbooks only

You can also use the ansible playbooks without vagrant. Like that you can deploy Splunk to an existing set of hosts (virtual or physical). You have to create some config files, which is normally done by vagrant. Vagrant dynamically creates the ansible inventory file with the host and group variables for your configuration. Everything can be found in the `inventory` directory. The easiest way would be to create the same configuration with vagrant (ex. on your laptop) and copy the created files to your other Ansible environment.

# Known issues, limitations

* ulimit settings not working on Ubuntu 14 (without systemd)
* Forwarding data from a universal forwarder to a heavy forwarder cannot be configured in the config file. This must be done manually after installation.
* Virtualbox: Virtual host startup does not respond sometimes, if it fails, recreate the host again.
* Virtualbox has some issues with clock time skew, when not using virtualbox additions. I added a workaround with forcing time clock sync every 5 minutes. A working internet connection on the Virtualbox host is needed.
* AWS: Due to security reasons the login page with the admin password information has been disabled and https is enabled with splunk's own self signed certs.
* AWS: OS images (AMI) do not have ntp configured by default. This will be added in Splunkenizer later.

## Supported Ansible Versions

The following Ansible versions are tested and working with Splunkenizer, but any newer version should work as well.

:white_check_mark: Ansible 2.4.0.x
:white_check_mark: Ansible 2.4.3.x
:white_check_mark: Ansible 2.5.x
:white_check_mark: Ansible 2.6.x
:white_check_mark: Ansible 2.7.x

# Authors

Splunkenizer is created by [Marco Stadler](https://github.com/splunkenizer) - a passionate Splunker.

# License

Apache License 2.0

See [COPYING](COPYING) to see the full text.
