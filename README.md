:white_check_mark: Ansible 2.4.3.0 seems to be stable with Splunkenizer!

:white_check_mark: Ansible 2.4.0.0 is good to go with Splunkenizer!

:bangbang: Due to the bug [#23609](https://github.com/ansible/ansible/issues/23609) ansible 2.4.2.0 does not work with Splunkenizer!

:bangbang: Due to the bug [#31755](https://github.com/ansible/ansible/issues/31755) ansible 2.4.1.0 does not work with Splunkenizer!


![Splunkenizer Overview](https://github.com/thesplunker/Splunkenizer/blob/master/pic/splunkenizer_overview.png)



# Splunkenizer

Ever wanted to build a complex Splunk environment for testing, which looks as close as possible to a production deployment? Need to test a Splunk upgrade? See how Splunk indexer- or search head clustering works? Or just need to verify some configuration changes? This is the right place for you! The aim of this framework is to produce a Splunk environment in a fast and convenient way for testing purposes or maybe also for production use. The created Splunk installation and setup follows best practices using base config apps from Splunk. There are many ways to configure a Splunk environment, in terms of configuration file locations, so this is just another example how to do it.

# Support

**Note: This framework is not officially supported by Splunk. I develop this on best effort in my spare time.**

# Features

* Build complex, reproducible Splunk environments in one shot, including all roles available for Splunk Enterprise.
* Building Cluster Master, Indexer Clusters, Deployer, Search Head Clusters, Deployment Server, Universal Forwarders, Heavy Forwarders, License Master and Monitoring Console. All ready to use.
* Configuration done according best practices with configuration apps
* Splunk environment definition stored in one simple [yaml](http://docs.ansible.com/ansible/latest/YAMLSyntax.html) file
* [Example configuration files](examples) for different setups included
* MacOSX and Linux Support
* Controlled by [Vagrant](https://www.vagrantup.com)
* Virtualized by [Virtualbox](https://www.virtualbox.org). It can be extended to other technologies like VMWare, Docker, AWS and such in the future.
* Deployment done with [Ansible](https://www.ansible.com), should be ready to use without vagrant (not tested yet)

## Roadmap

See the upcoming features in the [Roadmap](ROADMAP.md)

## Changelog

Implemented changes are to be found in the [Changelog](CHANGELOG.md)

# Download from

You can download the framework on [GitHub](https://github.com/thesplunker/Splunkenizer/)

# Software Dependencies

## Splunk Software
* [Splunk Enterprise](http://www.splunk.com/en_us/download/splunk-enterprise.html)
* [Splunk Universal Forwarder](http://www.splunk.com/en_us/download/universal-forwarder.html)

## Splunk Professional Services Best Practices Base Config Apps:
* [Configurations Base Apps](https://splunk.app.box.com/ConfigurationsBase)
* [Configurations Cluster Apps](https://splunk.app.box.com/ConfigurationsCluster)

# Installation

The Framework is currently only tested on Mac OSX, but any other Unix, which is supported by Virtualbox, should work.

## OSX Instructions

* Download and install Virtualbox and Vagrant from their websites. Both are coming with a simple installer in the package.
* Install Ansible: I personally prefer [Brew](https://brew.sh) for that, which is as simple as `brew install ansible`. Current ansible 2.4+ has bugs. You have to use the previous version.
* Download the framework in a folder of your choice with `git clone git@github.com:thesplunker/Splunkenizer.git`
* Download the prerequisites and put them in folder called `Software`, just beside the `Splunkenizer` folder. Folder structure should look like this, if you have the stuff extracted in a folder called `Vagrant`.

```
./Vagrant/Splunkenizer/...
./Vagrant/Software/Configurations - Base/...
./Vagrant/Software/Configurations - Index Replication/...
./Vagrant/Software/splunk-7.0.0-c8a78efdd40f-Linux-x86_64.tgz
./Vagrant/Software/Splunk_Enterprise.lic
./Vagrant/Software/splunkforwarder-7.0.0-c8a78efdd40f-Linux-x86_64.tgz
```

# Framework Usage

## Configuration file
There is one single configuration file, where all settings for your deployment are stored. If you run `vagrant` the first time, you will get a `config` directory created. Copy one configuration file from the [examples](examples) to `config/splunk_config.yml` and adjust the setting to your needs. For standard setup you should be fine with most of the default settings, but there are a lot of things you can adjust for secial needs. See the [configuration description](examples/configuration_description.yml) for all the possibilities.

## Start the deployment
The whole framework is managed by vagrant. You have to be in the top directory, where the `Vagrantfile` sits and just run the build command. It will pull an os image from the internet, when run the first time.

```
vagrant up
```

## Stop hosts

```
vagrant halt
```

## Destroy hosts

```
vagrant destroy [-f] [<hostname>]
```

## Rerun provisioning
Ansible playbooks can be run over and over again. If you need to start the playbooks on a certain host again run this:

```
vagrant provision <hostname>
```

## Login to Splunk Browser Interface
Splunk runs on port 8000 by default. Example: http://172.16.2.100:8000 (Username: admin, Password: splunklab)

## Login to the hosts
To login to one of the hosts just open the index.html file crated in the Splunkenizer/config directory. You will find links to every role.

Login with SSH:

```
vagrant ssh <hostname>
```

## Environment Users

### User vagrant
Vagrant uses a dedicated user to work inside the virtual machines. The user name is `vagrant` and has sudo rights to switch to root or other users.

### User splunk
Splunk Enterprise is installed and run as user `splunk`. You can switch to this user by `sudo su - splunk`. For convenience, I have added some command aliases to the user `vagrant` and user `splunk`

## Copy files

You can copy files from your host system to the virtual nodes with the vagrant command. You need to install the vagrant plugin `vagrant-scp` to have this feature available. Check [Vagrant Docs](https://www.vagrantup.com/docs/plugins/usage.html) on how to do this.

```
vagrant scp <file> <hostname>:/destdir
```

## Ansible playbooks only
I designed the ansible playbooks to be used without vagrant, just on its own. Till now I haven't tested this scenario so far.
Vagrant dynamically creates the ansible inventory. The file is located in `.vagrant/provisioners/ansible/inventory/vagrant_ansible_inventory`. If you would like to use the ansible playbooks without vagrant, you have to create the inventory accordingly with the same groups. The Vagrant script also dynamically creates group_vars for the used config file. In `ansible/group_vars/all` you can find the `general` and `splunk_basics` sections from the config file. In `ansible/group_vars` the indexer-, search head cluster and splunk_env configs are placed.

# Known issues, limitations

* Configuration from universal forwarder to heavy forwarder not yet implemented. Must be done manually after installation.
* Virtual host startup does not respond sometimes, if it fails, recreate the host again.
* If using ansible 2.4+, you will get some warnings
* Virtualbox has some issues with clock time skew, when not using virtualbox additions. I added a workaround with forcing time clock sync every 5 minutes. A working internet connection on the Virtualbox host is needed.

# Authors

Splunkenizer was created by [Marco Stadler](https://github.com/thesplunker) - a passionate Splunker.

# License

Apache License 2.0

See [COPYING](COPYING) to see the full text.
