# Migrate existing Splunk Platform Automator Environments from 1.x to 2.x

From Splunk Platform Automator 2.0 the Framework does use an [Ansible Inventory Plugin](https://docs.ansible.com/ansible/latest/plugins/inventory.html) to build the inventory on the fly during execution. The local `inventory` directory does only hold minimum settings based on the virtualization you choose. The rest calculated in flight and not stored somewhere.

You can verify your inventory with

```bash
ansible-inventory --list --export
```

## Migrate splunk_config.yml

The steps here apply to all environments.

- You have to add the `plugin` setting to the top of your config file
  
```yml
# splunk_config.yml
plugin: splunk-platform-automator
```

## Migrate Virtualbox Environments

The steps here only apply if your current environment is built on virtualbox.

- Cleanup unneeded entries from the ansible inventory

```bash
rm -rf inventory/group*
```

- Move the setting `start_ip` in the `general` section to the `virtualbox` section.

## Migrate AWS Environments

The steps here only apply if your current environment is built on AWS.

- Cleanup unneeded entries from the ansible inventory

```bash
rm -rf inventory/*
```

- Build the config/aws_ec2.yml config file

```bash
vagrant status
```

- Get the GUID from config/aws_ec2.yml at `tag:SplunkEnvID:` and add a tag `SplunkEnvID` to every host in your AWS environment with that GUID
- Create also a tag `SplunkHostname` for every AWS host with the name of your hosts from the splunk_hosts section

If you have the aws cli available, this can be done with the following one liner

```bash
for machine in $(ls -1d .vagrant/machines/*); do aws ec2 create-tags --resources $(cat $machine/aws/id) --tags Key=SplunkHostname,Value=$(basename $machine) Key=SplunkEnvID,Value=$(grep "tag:SplunkEnvID:" config/aws_ec2.yml | cut -d: -f3 | tr -d " ") Key=Name,Value=$(basename $machine) --no-cli-pager; done
```

## Migrate Environments where ansible only is used

The steps here only apply if your current environment is not built with vagrant.

The process is not so traight forward, since I do not know how you built your ansible inventory. Basically, you have
to make sure everything you defined in your inventory files is reflected in the splunk_config.yml file.

- Before you upgrade your splunk automator environment, you have to export the inventory to a file

```bash
ansible-inventory --list --export > inventory_1.txt
```

- Migrate all settings to the splunk_config.yml file
- Remove the complete inventory

```bash
rm -rf inventory/*
```

- After the upgrade and building of your splunk_config.yml, you can check the new inventory with the `ansible-inventory` command and compare it with your dump from version 1.x
