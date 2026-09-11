# Splunk Platform Automator

![Splunk Platform Automator Overview](https://github.com/splunk/splunk-platform-automator/blob/master/pic/splunk-platform-automator_overview.png)

![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Ansible](https://img.shields.io/badge/Ansible-2.10%2B-red.svg?logo=ansible&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg?logo=python&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-1.3.0%2B-purple.svg?logo=terraform&logoColor=white)

Ever wanted to build a complex Splunk environment for testing, which looks as close as possible to a production deployment? Need to test a Splunk upgrade? See how Splunk indexer- or search head clustering works? Or just need to verify some configuration changes? This is the right place for you! The aim of this framework is to produce a Splunk environment in a fast and convenient way for testing purposes or maybe also for production use. The created Splunk installation and setup follows best practices. There are many ways to configure a Splunk environment in terms of configuration file locations, so this is just another example how to do it.

## Table of Contents

- [Splunk Platform Automator](#splunk-platform-automator)
  - [Table of Contents](#table-of-contents)
  - [Support](#support)
  - [Features](#features)
  - [Roadmap](#roadmap)
  - [Changelog](#changelog)
  - [Testing](#testing)
  - [Releasing](#releasing)
  - [Installation](#installation)
    - [Framework Installation](#framework-installation)
    - [Install Virtualbox support (optional)](#install-virtualbox-support-optional)
    - [Setup Windows Subsystem for Linux (WSL2)](#setup-windows-subsystem-for-linux-wsl2)
    - [Install and configure AWS support (optional - Legacy Vagrant Plugin)](#install-and-configure-aws-support-optional---legacy-vagrant-plugin)
      - [Example Basic AWS Security Group 'SplunkBasic'](#example-basic-aws-security-group-splunk_basic)
        - [Inbound Rules](#inbound-rules)
        - [Outbound Rules](#outbound-rules)
  - [Upgrade](#upgrade)
    - [Migrate existing Splunk Platform Automator Environments from 1.x to 2.x](#migrate-existing-splunk-platform-automator-environments-from-1x-to-2x)
  - [Removed Biased Language](#removed-biased-language)
  - [Building Windows Virtual Machine Template](#building-windows-virtual-machine-template)
  - [Framework Usage](#framework-usage)
    - [Start here](#start-here)
    - [First start and initialization](#first-start-and-initialization)
    - [Multiple environments, one clone](#multiple-environments-one-clone)
    - [Copy a configuration file](#copy-a-configuration-file)
    - [Start the deployment](#start-the-deployment)
      - [Option A: Virtualbox (Local Virtual Machines)](#option-a-virtualbox-local-virtual-machines)
      - [Option B: AWS with Terraform (Recommended for AWS)](#option-b-aws-with-terraform-recommended-for-aws)
      - [Option C: AWS with Vagrant Plugin (Legacy)](#option-c-aws-with-vagrant-plugin-legacy)
    - [Stop hosts](#stop-hosts)
    - [Destroy hosts](#destroy-hosts)
    - [Rerun provisioning](#rerun-provisioning)
    - [Login to the hosts](#login-to-the-hosts)
      - [Login to Splunk Browser Interface](#login-to-splunk-browser-interface)
      - [Login with spa shell](#login-with-spa-shell)
      - [Login by SSH](#login-by-ssh)
    - [Environment Users](#environment-users)
      - [User vagrant](#user-vagrant)
      - [User splunk](#user-splunk)
    - [Copy files](#copy-files)
      - [Copy with spa shell](#copy-with-spa-shell)
      - [Copy with vagrant scp](#copy-with-vagrant-scp)
        - [scp example](#scp-example)
    - [Ansible playbooks only](#ansible-playbooks-only)
    - [Build your own Python version](#build-your-own-python-version)
    - [Create a virtualenv for a specific Ansible version](#create-a-virtualenv-for-a-specific-ansible-version)
      - [Install needed python libraries in your virtualenv](#install-needed-python-libraries-in-your-virtualenv)
  - [Known issues, limitations](#known-issues-limitations)
    - [Supported Ansible Versions](#supported-ansible-versions)
  - [License](#license)



## Support

**Note: This framework is not officially supported by Splunk. I am developing this on best effort in my spare time.**

## Features

- Build complex, reproducible Splunk environments in one shot, including all roles available for Splunk Enterprise.
- Building Cluster Manager, Indexer Clusters, Deployer, Search Head Clusters, Deployment Server, Universal Forwarders, Heavy Forwarders, License Manager and Monitoring Console. All ready to use.
- Configuration done according best practices with configuration apps
- Splunk environment definition stored in one simple [yaml](http://docs.ansible.com/ansible/latest/YAMLSyntax.html) file
- [Example configuration files](examples) for different setups included
- **App Deployment**: Deploy and manage Splunk apps (Splunkbase, local, or URL) to search heads, indexers, and forwarders via `splunk_app_deployment` in the config. See the [App Deployment Guide](docs/App_Deployment.md).
- **Secrets and Vault**: Store passwords and other secrets in `splunk_config.yml` securely using [Ansible Vault](docs/Secrets_and_Vault.md) (encrypted values, no plain-text credentials in version control).
- Deployment and configuration done with [Ansible](https://www.ansible.com)
- **AWS Infrastructure provisioning via [Terraform](https://www.terraform.io)** (recommended for AWS deployments)
  - Ansible-driven Terraform workflow with single config file
  - Automatic inventory generation
  - Support for complex configurations (volumes, instance types, etc.)
- Virtual hosts can be created by [Vagrant](https://www.vagrantup.com)
  - Currently supports [Virtualbox](https://www.virtualbox.org) or [AWS Cloud](https://aws.amazon.com) (legacy).
- Can deploy Splunk on existing hosts (virtual or physical)
- Developed and tested on MacOSX but should support Linux as well.



## Roadmap

Shipped and upcoming work is tracked in the [Roadmap](ROADMAP.md).

## Changelog

Implemented changes are to be found in the [Changelog](CHANGELOG.md)

## Testing

Automated tests that do not need AWS or a live Splunk deployment:

```bash
./tests/run_local_tests.sh
```

See [tests/README.md](tests/README.md). Full AWS deployment tests stay manual.

## Releasing

Cut a version from `master` with [RELEASE.md](RELEASE.md) and `./scripts/release.sh`.

## Installation

The Framework is currently tested on Mac OSX and Linux, but any other Unix, which is supported by Virtualbox, should work too.

### Framework Installation

1. Install **Python 3.9+** (with the `venv` module). If your distro has no suitable package, [build your own Python](#build-your-own-python-version).
2. Clone this repository or extract a [release](https://github.com/splunk/splunk-platform-automator/tags). That checkout is the framework (`SPA_HOME`). Do not copy `ansible/` into each environment.
3. Create a `Software` directory as a **sibling** of the clone (or of the env dir). Put Splunk Enterprise and Universal Forwarder tarballs there, Professional Services baseconfig apps, and optionally `Splunk_Enterprise.lic`. See the layout below.
4. Ansible, Pydantic, and Ansible collections are **not** installed with Homebrew. `spa init` (or `./bin/spa_venv.sh --create`) creates `$SPA_HOME/.venv` from `requirements.txt` and `requirements.yml`. Check the machine with `spa doctor`.
5. **AWS environments:** install Terraform 1.3+ (e.g. `brew install terraform`) and an AWS key pair / security group. **VirtualBox:** install Vagrant (and VirtualBox); see [Install Virtualbox support](#install-virtualbox-support-optional). **Optional:** [direnv](https://direnv.net) so `cd` into an env dir activates the venv and `SPA_*` variables (`brew install direnv` plus the [shell hook](https://direnv.net/docs/hook.html)).

Primary flow: `spa init ~/envs/my-env` then `spa validate && spa provision && spa deploy`. `ansible-playbook` remains documented as the equivalent, not the default.

Your directory structure should now look like this:

```bash
./Vagrant/splunk-platform-automator/...
./Vagrant/Software/Configurations - Base/...
./Vagrant/Software/Configurations - Index Replication/...
./Vagrant/Software/splunk-10.4.0-f798d4d49089-linux-amd64.tgz
./Vagrant/Software/splunkforwarder-10.4.0-f798d4d49089-linux-amd64.tgz
./Vagrant/Software/Splunk_Enterprise.lic
```

Put installers in `Software/`:

- [Splunk Enterprise](http://www.splunk.com/en_us/download/splunk-enterprise.html) and [Universal Forwarder](http://www.splunk.com/en_us/download/universal-forwarder.html) `.tgz` archives
- Splunk Professional Services Best Practices baseconfig apps (not public; ask your PS contact)
- Optional license as `Splunk_Enterprise.lic`

The `Vagrant/` parent name is traditional (VirtualBox). The clone and `Software/` sibling can live anywhere; env dirs created with `spa init` look for `../Software` next to the env, then next to `SPA_HOME`.

### Install Virtualbox support (optional)

1. Download and install [Virtualbox](https://www.virtualbox.org/wiki/Downloads).
2. Install the Virtualbox plugin for Vagrant: `vagrant plugin install vagrant-vbguest`



### Setup Windows Subsystem for Linux (WSL2)

The [Windows Subsystem for Linux](https://docs.microsoft.com/en-us/windows/wsl/install-win10) does allow to run Splunk Platform Automator on Windows. It even allows to create virtualbox hosts from it on the windows host directly.

Execute the steps [above](#framework-installation). To allow vagrant to talk to virtualbox follow the steps below.

- Create /etc/wsl.conf and reboot WSL (`wsl --shutdown`)

```ini
[automount]
options = "metadata"
```

- Enable WSL2 port forwarding by installing a vagrant plugin with: `vagrant plugin install virtualbox_WSL2`
- Add Environment Variables in WSL (maybe to your `~/.bashrc`)

```bash
export VAGRANT_WSL_ENABLE_WINDOWS_ACCESS="1"
export PATH="$PATH:/mnt/c/Program Files/Oracle/VirtualBox"
```



### Install and configure AWS support (optional - Legacy Vagrant Plugin)

> ⚠️ **Note:** This section describes the legacy Vagrant AWS plugin setup. For new AWS deployments, we recommend using the [Terraform approach](#option-b-aws-with-terraform-recommended-for-aws) instead, which is more modern and easier to manage.

1. Install either of the aws vagrant plugins:
  - [vagrant-aws](https://github.com/mitchellh/vagrant-aws): This is te orig plugin but not maintained anymore and has issues with newer vagrant versions on OSX. The last working version of vagrant is 2.3.4. Install it with `vagrant plugin install vagrant-aws`
    - [vagrant-gecko-aws](https://github.com/geckoboard/vagrant-aws): This is a clone of the orig project and does support newer versions (up to 2.3.7) of vagrant. Install it with `vagrant plugin install vagrant-gecko-aws --entry-point vagrant-aws`
2. Download the vagrant dummy box for aws: `vagrant box add aws-dummy https://github.com/mitchellh/vagrant-aws/raw/master/dummy.box`
3. Generate AWS ACCESS Keys, described [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html#cli-configure-quickstart-creds)
4. Optional, but recommended:
  - Add AWS_ACCESS_KEY_ID=your access key ID as environment variable
    - Add AWS_SECRET_ACCESS_KEY=your secret access key as environment variable
5. Create an ssh key pair described [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair) and store the public key on your disk for later reference in the config file
6. Create an AWS [security group](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-network-security.html#vpc-security-groups) and name it for example 'Splunk_Basic' and add the following TCP ports



#### Example Basic AWS Security Group 'Splunk_Basic'



##### Inbound Rules


| Type       | Protocol | Port Range | Source        | Description                |
| ---------- | -------- | ---------- | ------------- | -------------------------- |
| All TCP    | TCP      | 0 - 65535  | 172.31.0.0/16 | Allow all internal traffic |
| Custom TCP | TCP      | 8000       | 0.0.0.0/0     | Splunk Web Interface       |
| SSH        | TCP      | 22         | 0.0.0.0/0     | SSH to all hosts           |




##### Outbound Rules


| Type        | Protocol | Port Range | Destination | Description       |
| ----------- | -------- | ---------- | ----------- | ----------------- |
| All Traffic | All      | All        | 0.0.0.0/0   | Allow all traffic |




## Upgrade

To upgrade your Splunk Platform Automator, just update your local code from the repo

```bash
git pull
```



### Migrate existing Splunk Platform Automator Environments from 1.x to 2.x

Please refer to the [Migration Guide](docs/Migrate_SPA_1x_to_2x.md).

## Removed Biased Language

Please refer to the [Removed Biased Language Guide](docs/Removed_Biased_Language.md).

## Building Windows Virtual Machine Template

To build your own windows vagrant image follow [Setup Windows Vagrant image](docs/Setup_Windows_Box.md)

## Framework Usage

### Start here

Pick one path. Ansible always comes from `bin/spa_venv.sh` (created by `spa init` if missing), not from Homebrew.

**AWS (recommended for a separate environment directory).** One clone, many environments. Terraform state and `splunk_config.yml` live in the env dir. `vagrant up` is not used.

```bash
cd /path/to/splunk-platform-automator
spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env
cd ~/envs/my-env
# With direnv: venv + SPA_HOME / SPA_ENV_DIR / ANSIBLE_* load on cd (init ran direnv allow).
# Without direnv:
#   source /path/to/clone/bin/spa_venv.sh --env ~/envs/my-env
#   eval "$(spa env --export)"
spa validate
spa provision --yes
spa deploy
```

Host links: `$SPA_ENV_DIR/config/index.html`. Destroy: `spa destroy --yes`. Details: [Multiple environments, one clone](#multiple-environments-one-clone) and [Option B](#option-b-aws-with-terraform-recommended-for-aws).

**VirtualBox (local VMs).** Keep config in the **clone** (`config/splunk_config.yml`). Run Vagrant from the directory that contains `Vagrantfile` (`SPA_HOME`). An env dir from `spa init` does **not** get a Vagrantfile; `vagrant up` from `~/envs/...` is not supported yet.

```bash
cd /path/to/splunk-platform-automator
cp examples/single_node.yml config/splunk_config.yml   # or another VirtualBox example
source bin/spa_venv.sh
spa doctor
vagrant up
spa deploy
```

### First start and initialization

For VirtualBox only: run `vagrant` once from the clone so it can create its working directories. You must execute Vagrant inside the Splunk Platform Automator directory where `Vagrantfile` sits.

```bash
cd splunk-platform-automator
vagrant
```

### Multiple environments, one clone

Keep one git checkout as the framework (`SPA_HOME`) and put each Splunk environment in its own directory (`SPA_ENV_DIR`). Env state is the config (including generated `index.html`), `.spa.yml`, `inventory/hosts`, Terraform state, and optional `saved_base_config_apps/` (pulled-back PS baseconfig apps) — not a copy of `ansible/`.

```bash
# Fresh AWS env from an example (not a VirtualBox example):
spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/itsi

# Old clone that already has a running env (config + inventory + Terraform state):
spa init ~/envs/itsi
# or, from a new framework checkout, pull state out of the old clone:
spa init --from /path/to/old-clone ~/envs/itsi

eval "$(spa env --export)"
spa validate
```

If `config/splunk_config.yml` already exists in `SPA_HOME` (or `--from`), `spa init` **migrates** that state instead of copying an example. Config, `inventory/hosts`, and Terraform state/`tfvars`/`.terraform` move into the env so destroy/redeploy still sees the same AWS resources. Framework files (`ansible/`, modules) stay in the clone. Use `--keep-source` to copy instead of move. Use `--example` when you want a new config even if the clone already has one. `--force` refreshes `.spa.yml` / `.envrc` and never replaces `splunk_config.yml` unless `--example` is also given.

If you copied a whole old checkout as the env directory, `spa init DIR` detects it and exits 2 until you pass `--force`. Then env state is kept, `ansible/` and other framework leftovers are removed, and `.spa.yml` points at the clone you ran `spa` from.

`spa env --export` prints `SPA_HOME`, `SPA_ENV_DIR`, `SPLUNK_CONFIG_FILE`, and `ANSIBLE_INVENTORY` so playbooks use the env YAML, not `config/splunk_config.yml` in the clone.

#### Python environment for an env dir

Ansible, Pydantic, and the other Python dependencies come from a virtualenv managed by `bin/spa_venv.sh`, so a broken system or Homebrew package does not block an environment:

```bash
# Created automatically by spa init when missing; or by hand:
./bin/spa_venv.sh --create              # shared venv in SPA_HOME/.venv
source bin/spa_venv.sh                  # activate (creates it when missing)
```

The venv used is the first match of `SPA_VENV_DIR` (or `--dir`), then `$SPA_ENV_DIR/.venv` when that exists, then `SPA_HOME/.venv`. Ansible collections from `requirements.yml` install next to the venv and `ANSIBLE_COLLECTIONS_PATH` is exported. Terraform stays a system binary.

Give one environment its own Python or Ansible version with an env-local venv:

```bash
spa init --example single_node.yml --venv ~/envs/py311
spa init --example single_node.yml --venv --python python3.11 ~/envs/py311
spa init --force --venv --ansible 2.17.8 ~/envs/py311   # keeps splunk_config.yml
# existing env:
./bin/spa_venv.sh --create --dir ~/envs/py311/.venv --python python3.11
```

`spa init` also writes an `.envrc` (skip with `--no-envrc`) and runs **`direnv allow`** for that env. For `cd` to load the environment automatically, direnv must run in your shell — a one-time setup:

```bash
brew install direnv
spa doctor --fix-direnv    # adds one line to ~/.zshrc (or ~/.bashrc)
# Close the terminal, open a new one, then: cd ~/envs/my-env
```

`spa doctor` checks that this line exists (not only that the `direnv` program is installed). Interactive `spa init` runs `--fix-direnv` for you. Then:

```bash
spa doctor --env ~/envs/my-env
```

`spa init` runs the same check at the end (use `--skip-doctor` to skip). Ansible and Pydantic are **not** brew requirements — they install into `spa_venv`.

Without direnv, activate the same environment explicitly:

```bash
source /path/to/clone/bin/spa_venv.sh --env ~/envs/itsi
eval "$(spa env --export)"
```

The test suites keep their own `tests/.venv` (pytest dependencies stay out of the venv an env uses); `tests/run_venv.sh` is a thin wrapper around the same `bin/spa_venv.sh`.

Installers and PS baseconfig apps default to `../Software`. Local `source: local` apps default to `../apps` (env sibling), then `$SPA_HOME/apps`. Resolution order for each: env (`SPA_SOFTWARE_DIR` / `SPA_BASECONFIG_DIR` / `SPA_APPS_DIR`), then a **custom** path in `splunk_config.yml` (`splunk_dirs.splunk_software_dir`, `splunk_dirs.splunk_baseconfig_dir`, `splunk_app_deployment.local_app_repo_path`), then `.spa.yml` (`software_dir` / `baseconfig_dir` / `apps_dir`), then discovery. Built-in defaults such as `../Software` do not override `.spa.yml`. `spa init` writes the keys it finds. Unset `SPA_HOME` / `SPA_ENV_DIR` to keep today's in-repo workflow.

Day-to-day commands: `spa validate`, `spa provision`, `spa deploy`, `spa run NAME`. Equivalent: `ansible-playbook` from `$SPA_HOME` after `eval "$(spa env --export)"`.

### Copy a configuration file

There is one single configuration file, where all settings for your deployment are defined. For a **separate environment**, `spa init --example … ENV_DIR` copies an example into `$SPA_ENV_DIR/config/splunk_config.yml`. For **clone-equal** (VirtualBox, or a single env in the checkout), copy an example to `config/splunk_config.yml` in the clone. Adjust the settings to your needs. For a standard setup you should be fine with most of the default settings, but there are a lot of things you can adjust for special cases. See the [configuration description](examples/configuration_description.yml) file, where all existing values are described. For a step-by-step AWS lab workflow (SVA topology, OS/SSH, validation), see [Splunk Config Guided Setup](docs/Splunk_Config_Guided_Setup.md). For AI agent skills (`spa-create-config`, `spa-add-test-scenario`), see [AGENTS.md](AGENTS.md) and [skills/spa/](skills/spa/). To store passwords and other secrets securely (e.g. Splunk admin password, cluster secrets), see [Storing secrets in splunk_config.yml](docs/Secrets_and_Vault.md).

AWS: See [instruction here](#option-b-aws-with-terraform-recommended-for-aws) when deploying into Amazon Cloud. You can start with [splunk_config_terraform_aws.yml](examples/splunk_config_terraform_aws.yml) for a simple environment. Copy `splunk_idxclusters`, `splunk_shclusters` and `splunk_hosts` sections from other examples for more complex deployments.

### Start the deployment

Splunk Platform Automator supports multiple deployment targets. Choose the appropriate method for your environment:

#### Option A: Virtualbox (Local Virtual Machines)

Use this path with config in the **clone** and commands run from `SPA_HOME` (where `Vagrantfile` is). Env directories from `spa init` do not include a Vagrantfile; do not run `vagrant up` from `$SPA_ENV_DIR`.

When building virtual machines for Virtualbox the first time it will pull an OS image from the internet. The box images are cached here: `~/.vagrant.d/boxes`.

**Create the Virtual Machines:**

```bash
vagrant up
```

**Run Ansible playbooks to deploy and configure the Splunk software:**

The `vagrant up` command only creates the virtual machines. To deploy Splunk afterwards, run this command:

```bash
ansible-playbook ansible/deploy_site.yml
```

To run both steps with one command use:

```bash
vagrant up; ansible-playbook ansible/deploy_site.yml
```

---



#### Option B: AWS with Terraform (Recommended for AWS)

**Modern, declarative infrastructure provisioning using Terraform managed by Ansible playbooks.**

**Prerequisites:**

- Terraform 1.3.0+ installed (`spa doctor --env …` requires it when the config has `terraform.aws`)
- Shared venv (`spa init` or `./bin/spa_venv.sh --create`) so `ansible-playbook` is not Homebrew Ansible
- AWS credentials (via environment variables or config file)
- AWS security group created (e.g., 'Splunk_Basic') - see [security group example](#example-basic-aws-security-group-splunk_basic)
- EC2 key pair created

Prefer an **environment directory** ([Start here](#start-here)) so Terraform state is not written into the clone. Clone-equal (`config/splunk_config.yml` in the checkout) still works.

**Quick Start** (clone-equal). For an env dir, `cd` the env first so `ANSIBLE_INVENTORY` points at that config, then run `spa provision` / `spa deploy` (or the same playbooks with `"$SPA_HOME/ansible/..."`).

- Configure `config/splunk_config.yml` with a `terraform.aws` section:

```yaml
terraform:
  aws:
    region: "eu-central-1"
    ami_id: "ami-03cbad7144aeda3eb"  # Redhat 9
    key_name: "aws_key"
    ssh_private_key_file: "~/.ssh/aws_key.pem"
    ssh_username: "ec2-user"
    security_group_names: ["Splunk_Basic"]
    instance_type: "t2.micro"

splunk_hosts:
  - name: idx1
    roles: [indexer]
    terraform:
      aws:
        instance_type: "c5.4xlarge"
        root_volume_size: 100
```

- Provision infrastructure:

```bash
ansible-playbook ansible/provision_terraform_aws.yml
```

- Deploy Splunk:

```bash
ansible-playbook ansible/deploy_site.yml
```

- Destroy infrastructure:

```bash
ansible-playbook ansible/destroy_terraform_aws.yml
```

**Features:**

- ✅ Single source of truth in `splunk_config.yml`
- ✅ Automatic Ansible inventory generation
- ✅ Support for `iter` to generate multiple hosts with numbering
- ✅ Support for `list` to generate multiple hosts with custom names
- ✅ Per-host instance types, volumes, and configurations
- ✅ AWS credentials can be in config or environment variables

**Documentation:**

- [Ansible-Terraform Integration Guide](docs/Ansible_Terraform_AWS_Integration.md) - Complete documentation
- [Terraform AWS README](terraform/aws/README.md) - Terraform configuration details

---



#### Option C: AWS with Vagrant Plugin (Legacy)

**Traditional Vagrant-based approach using the vagrant-aws plugin.**

> ⚠️ **Note:** This method is considered legacy. The Terraform approach (Option B) above is recommended for new AWS deployments.

To use the Vagrant AWS plugin:

1. Follow the [AWS plugin installation instructions](#install-and-configure-aws-support-optional---legacy-vagrant-plugin)
2. Configure `config/splunk_config.yml` with an `aws` section (see [splunk_config_aws.yml](examples/splunk_config_aws.yml))
3. Run `vagrant up` to create instances
4. Run `ansible-playbook ansible/deploy_site.yml` to deploy Splunk



### Stop hosts

This will gracefully shutdown all the virtual machines.

```bash
vagrant halt
```



### Destroy hosts

You can destroy all the virtual machines with one command.

```bash
vagrant destroy [-f] [<hostname>]
```



### Rerun provisioning

Ansible playbooks can be run over and over again. If the virtual machine is already built, you can rerun the playbooks on a certain host again. This can be needed if something fails and you fixed the error.

```bash
ansible-playbook ansible/deploy_site.yml [--limit <hostname>]
```



### Login to the hosts



#### Login to Splunk Browser Interface

To login to one of the hosts just open the `index.html` file created in the env `config/` directory (`$SPA_ENV_DIR/config/index.html`, or `config/index.html` in the clone when you are not using a separate env). You will find links to every role of your deployment.
If something changes along the way and you need to update the linkpage just call this playbook:

```bash
spa run create_linkpage
```



#### Login with spa shell

`spa shell` looks up host details from the Ansible inventory. It handles keys, users, and IP addresses automatically. (`spash` was never shipped on master; 3.0 uses `spa shell` only.)

**Usage:**

```bash
# SSH into a host (matches partial names)
spa shell <hostname>

# List all available hosts
spa shell -l

# Pass extra arguments to SSH
spa shell idx1 -- -L 8089:localhost:8089
```

From an env dir the generated `.envrc` adds `$SPA_HOME/bin` to `PATH`, so plain `spa` works. If it is not found, or runs from a different checkout than you expect, `spa doctor` reports which one wins — "not on PATH" usually means the direnv shell hook is not loaded in that shell (`spa doctor --fix-direnv`).



#### Login by SSH

Vagrant deployes an ssh key for the vagrant user to login without a password.

```bash
vagrant ssh <hostname>
```



#### Install additional SSH public keys

You can install additional SSH public keys on all managed hosts by adding them to the `os` section in `config/splunk_config.yml`. The keys are added to the Ansible login user's `authorized_keys` file.

```yaml
os:
  ssh_keys:
    - ~/.ssh/id_ed25519.pub
    - ~/.ssh/colleague_key.pub
```

To deploy keys without running a full site deployment, use the standalone playbook:

```bash
ansible-playbook ansible/install_ssh_keys.yml
```



### Environment Users



#### User vagrant

Vagrant uses a dedicated user to work inside the virtual machines. The user name is `vagrant` and has sudo rights to switch to root or other users.

#### User splunk

Splunk Enterprise is installed and run as user `splunk`. You can switch to this user by `sudo su - splunk`. For convenience, I have added some command aliases to the user `vagrant` and user `splunk`.

```bash
alias
```



### Copy files



#### Copy with spa shell

`spa shell -c` copies files to and from hosts using scp. It automatically resolves the connection details from the inventory.

```bash
# Copy a local file to a remote host
spa shell -c local_file.txt idx1:/tmp/

# Copy a remote file to the current directory
spa shell -c idx1:/opt/splunk/etc/system/local/server.conf .
```



#### Copy with vagrant scp

You can copy files from your host system to the virtual nodes with the vagrant command. You need to install the vagrant plugin `vagrant-scp` to have this feature available. Check [Vagrant Docs](https://www.vagrantup.com/docs/plugins/usage.html) on how to do this.

```bash
vagrant scp <files> <target_on_dest> [vm_name]
```



##### scp example

```bash
vagrant scp ../app_dir/splunk-add-on-for-unix-and-linux_831.tgz /var/tmp uf
```



### Ansible playbooks only

You can also use the ansible playbooks without vagrant. For that you have to create your virtual or physical machines by other means. You can use the ansible playbooks to
deploy the Splunk roles onto the existing servers. Specify the hostnames in the `splunk_config.yml` file in the `splunk_hosts` section.
Ansible needs to know where to connect to via ssh to run the playbooks. For this you need to create some custom variables in the
`splunk_config.yml` file.

As a minimum specify the ssh user for ansible and the ssh private key which has been deployed on the systems. This user must be able to elevate to the `root` user with sudo.

```yml
custom:
  ansible_user: ansible
  ansible_ssh_private_key_file: '~/.ssh/id_rsa'
```

If you have host specific variables the custom section can also be added on host level. This could be for example `ansible_host` if different from the hostname. Also check [configuration description](examples/configuration_description.yml)

You can verify things like this first with an ansible ping:

```bash
ansible -m ping all
```

And then some more ansible prerequisites with this playbook

```bash
ansible-playbook ansible/test_ansible_prereqs.yml
```



### Build your own Python version

You can build your own python version, if you need a specific python version or your local one is outdated.
Please install the needed development tools in order to be able to compile stuff.

An easy way to install new python versions is using [pyenv](https://github.com/pyenv/pyenv) but you can also manually install Python like for example:

```bash
cd
mkdir tmp
mkdir -p ~/Python/3.9.9
cd tmp
wget https://www.python.org/ftp/python/3.9.9/Python-3.9.9.tgz
tar -xzf Python-3.9.9.tgz
cd Python-3.9.9/
./configure --prefix=~/Python/3.9.9 --with-ensurepip=install
make
make install
```



### Create a virtualenv for a specific Ansible version

Prefer `bin/spa_venv.sh` (shared `$SPA_HOME/.venv`, or `spa init --venv` for an env). The following is only needed if you pin an old Ansible by hand. See [supported Ansible versions](#supported-ansible-versions).

If you need a specific Ansible version you can create it inside a virtualenv environment. This can
 be useful when deploying older linux images, which too old python versions. An easy way to install new virtual environments is using [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) or you can do it manually like the following example.

```bash
python3 -m venv ansible_414
source ansible_414/bin/activate
python -m pip install ansible==7.7.0
```

This installs ansible 2.14.10, see the [version mapping](https://docs.ansible.com/ansible/latest/reference_appendices/release_and_maintenance.html#ansible-community-changelogs)

#### Install needed python libraries in your virtualenv

You must install some additional python modules for Splunk Platform Automator to work:

- jmespath # required for json_query calls
- lxml     # required for license file checks
- boto3    # required for ec2 (aws) plugin

Use the requirements file for easy installation

```bash
python -m pip install -r requirements.txt
```

Check the ansible version

```bash
ansible --version
```

If the version is not correct, open a new terminal and activate the
virtual environment again with the command from above.

```bash
source ansible_414/bin/activate
```



## Known issues, limitations

- Ubuntu 20.04 fails on checking the systemd settings and needs a more current ansible version. See [service_facts broken in Ubuntu 20.04](https://github.com/DataDog/ansible-datadog/issues/274)
- ulimit settings not working on Ubuntu 14 (without systemd)
- Forwarding data from a universal forwarder to a heavy forwarder cannot be configured in the config file. This must be done manually after installation.
- Virtualbox: Virtual host startup does not respond sometimes, if it fails, recreate the host again.
- Virtualbox has some issues with clock time skew, when not using virtualbox additions. I added a workaround with forcing time clock sync every 5 minutes. A working internet connection on the Virtualbox host is needed.
- AWS: Due to security reasons the login page with the admin password information has been disabled and https is enabled with splunk's own self signed certs.
- AWS: OS images (AMI) do not have ntp configured by default. This will be added in Splunk Platform Automator later.



### Supported Ansible Versions

The following Ansible versions are tested and working with Splunk Platform Automator.

- :x: Ansible 2.9.x and below (EOL)
- :white_check_mark: Ansible 2.10.x - 2.17.x (EOL)
- :white_check_mark: Ansible 2.18.x - 2.20.x

Check the [Ansible Support Matrix](https://docs.ansible.com/ansible/latest/reference_appendices/release_and_maintenance.html#ansible-core-support-matrix) for the most current information.

## License

Copyright 2022 Splunk Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

[http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0)

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.