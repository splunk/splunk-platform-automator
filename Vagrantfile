# -*- mode: ruby -*-
#
# This file is part of Splunk Platform Automator
#
###############################################################################
# Copyright 2022 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
###############################################################################

# Specify minimum Vagrant version and Vagrant API version
Vagrant.require_version '>= 2.2.7'
VAGRANTFILE_API_VERSION = '2'

require 'yaml'
require 'securerandom'
dir = File.dirname(File.expand_path(__FILE__))
config_dir = File.join(dir,"config")
defaults_dir = File.join(dir,"defaults")
config_file = File.join(config_dir,"splunk_config.yml")
inventory_dir = File.join(dir,"inventory")
hosts_file = File.join(inventory_dir, "hosts")
host_vars_dir = File.join(inventory_dir,"host_vars")
defaults = {}

# Workaround for bug with vagrant 2.2.7
# https://github.com/mitchellh/vagrant-aws/issues/566
class Hash
  def slice(*keep_keys)
    h = {}
    keep_keys.each { |key| h[key] = fetch(key) if has_key?(key) }
    h
  end unless Hash.method_defined?(:slice)
  def except(*less_keys)
    slice(*keys - less_keys)
  end unless Hash.method_defined?(:except)
end

# Check for Ansible binary
system("type ansible > /dev/null 2>&1")
if $?.exitstatus != 0
  print "ERROR: Cannot find ansible binary\n"
  exit 2
end

if !File.file?("Vagrantfile")
  print "ERROR: Run the command from the top directory, where 'Vagrantfile' is located!\n"
  exit 2
end

# Create some dirs if needed
[config_dir, inventory_dir].each do |dir|
  if !File.directory?(dir)
    FileUtils.mkdir_p(dir)
  end
end
# Create empty file, if not there
if !File.file?(hosts_file)
  File.open(hosts_file, "w") do |f|
    f.write("")
  end
end

if !File.file?(config_file)
  print "ERROR: Please copy a config file from the examples dir to #{config_file} to continue\n"
  exit 2
end

# Read YAML file with instance information (box, CPU, RAM, IP addresses)
# Edit the config file to change VM and environment configuration details
settings = YAML.load_file(config_file)

# Create splunk_apps variables
splunk_apps = YAML.load_file(File.join(defaults_dir,"splunk_apps.yml"))
defaults['splunk_apps'] = splunk_apps['splunk_apps']
splunk_apps = defaults['splunk_apps'].dup
if !settings['splunk_apps'].nil?
  splunk_apps = splunk_apps.merge(settings['splunk_apps'])
end

# Check for virtualization provider
if !settings.has_key?("virtualbox") and !settings.has_key?("aws")
    print "ERROR: No virtualization provider defined in #{config_file} \n\n"
    print "Supported types are virtualbox or aws\n"
    exit 2
end

stanza_merge_list = ['os']
if settings.has_key?("virtualbox")
  provider = "virtualbox"
  virtualbox = YAML.load_file(File.join(defaults_dir, "virtualbox.yml"))
  defaults['virtualbox'] = virtualbox['virtualbox']
  stanza_merge_list.append(provider)
  if !Vagrant.has_plugin?("vagrant-vbguest")
    print "ERROR: Plugin for virtualbox provider is missing, install with 'vagrant plugin install vagrant-vbguest'.\n"
    exit 2
  end
  # Create inventory/host_vars directory
  if !File.directory?(host_vars_dir)
    FileUtils.mkdir_p(host_vars_dir)
  end
elsif settings.has_key?("aws")
  provider = "aws"
  aws = YAML.load_file(File.join(defaults_dir,"aws.yml"))
  defaults['aws'] = aws['aws']
  stanza_merge_list.append(provider)
  if !Vagrant.has_plugin?("vagrant-gecko-aws") and !Vagrant.has_plugin?("vagrant-aws")
    print "ERROR: Plugin for AWS provider missing, install with 'vagrant plugin install vagrant-aws'.\n"
    exit 2
  end
  if !settings['general'].nil? and settings['general'].has_key?("start_ip")
    print "WARN: Ignoring general.start_ip setting for AWS provider.\n"
    print "INFO: You can remove this setting from the config file.\n"
    settings['general'].delete("start_ip")
  end
end

# Create ansible inventory from the config file
special_host_vars = {}
network = {}
defaults['os'] = {}
aws_merged = {}

# Deal with the aws_ec2 file
if provider == "aws"
  if settings['aws'].nil?
    settings['aws'] = {}
  end
  aws_merged = defaults['aws'].merge(settings['aws'])
  splunkPlatformAutomatorID = "undef"
  aws_ec2 = false
  if File.file?(File.join(config_dir, "aws_ec2.yml"))
    aws_ec2 = YAML.load_file(File.join(config_dir, "aws_ec2.yml"))
  end
  if !aws_ec2
    aws_ec2 = {}
  end
  if aws_ec2.has_key?("filters")
    if aws_ec2['filters'].has_key?("tag:SplunkEnvID")
      splunkPlatformAutomatorID = aws_ec2['filters']['tag:SplunkEnvID']
    end
  else
    aws_ec2['filters'] = {}
  end
  if splunkPlatformAutomatorID == "undef"
    splunkPlatformAutomatorID = SecureRandom.uuid
  else
    aws_ec2['filters']['tag:SplunkEnvID'] = splunkPlatformAutomatorID
  end
  # Read access keys from environment variable, if not spcified in settings
  if aws_merged.has_key?("access_key_id")
    aws_ec2['aws_access_key'] = aws_merged['access_key_id']
  else
    defaults['aws']['access_key_id'] = ENV['AWS_ACCESS_KEY_ID']
    aws_ec2.delete('aws_access_key')
  end
  if aws_merged.has_key?("secret_access_key")
    aws_ec2['aws_secret_key'] = aws_merged['secret_access_key']
  else
    defaults['aws']['secret_access_key'] = ENV['AWS_SECRET_ACCESS_KEY']
    aws_ec2.delete('aws_secret_key')
  end
  aws_ec2['plugin'] = 'aws_ec2'
  aws_ec2['regions'] = [].append(aws_merged['region'])
  aws_ec2['filters']['tag:SplunkEnvID'] = splunkPlatformAutomatorID
  aws_ec2['hostnames'] = [].append("tag:SplunkHostname")
  aws_ec2['compose'] = {}.update('ansible_host'=>'public_dns_name')
  aws_ec2['compose']['ip_addr'] = 'private_ip_address'
  aws_ec2['compose']['ansible_user'] = "ansible_user|default('#{aws_merged['ssh_username']}')"
  aws_ec2['compose']['ansible_ssh_private_key_file'] = "ansible_ssh_private_key_file|default('#{aws_merged['ssh_private_key_path']}')"
  File.open(File.join(config_dir,"aws_ec2.yml"), "w") do |f|
    f.write(aws_ec2.to_yaml)
  end
end

# If dynamic IPs are used, calculate the start number
if provider == "virtualbox"
  if !settings['virtualbox'].nil? and !settings['virtualbox']['start_ip'].nil?
    start_ip = settings['virtualbox']['start_ip']
  else
    start_ip = virtualbox['virtualbox']['start_ip']
  end
  ip_array = start_ip.split(".")
  base_ip = ip_array[0..2].join(".")
  start_num = ip_array[3].to_i
end

# Create inventory host vars and groups
host_vars = {}
splunk_host_list = []
ssh_usernames = {}
settings['splunk_hosts'].each do |splunk_host|
  hostnames = []
  if !splunk_host['name'].nil?
    hostnames.append(splunk_host['name'])
  elsif !splunk_host['list'].nil?
    hostnames = splunk_host['list']
  elsif !splunk_host['iter'].nil?
    iteration = splunk_host['iter']['numbers']
    nums = iteration.split('..')
    startnum = nums[0]
    endnum = nums[1]
    width = endnum.length
    (startnum..endnum).each do |hostnum|
      hostname = hostnum.to_s.rjust(width,'0')
      if !splunk_host['iter']['prefix'].nil?
        hostname = splunk_host['iter']['prefix'] + hostname
      end
      if !splunk_host['iter']['postfix'].nil?
        hostname = hostname + splunk_host['iter']['postfix']
      end
      hostnames.append(hostname)
    end
  end
  hostnames.each do |hostname|
    var_obj = defaults.dup
    stanza_merge_list.each do |config_group|
      if !settings[config_group].nil?
        var_obj[config_group] = var_obj[config_group].merge(settings[config_group])
      end
      if !splunk_host[config_group].nil?
        var_obj[config_group] = var_obj[config_group].merge(splunk_host[config_group])
        if config_group == "aws"
          if !splunk_host[config_group].nil?
            ssh_usernames.update(hostname=>splunk_host[config_group]['ssh_username'])
          end
        end
      end
    end
    special_host_vars[hostname] = var_obj.dup
    if provider == "aws"
      if !aws_merged['tags'].nil?
        aws_tags = aws_merged['tags'].clone
      else
        aws_tags = {}
      end
      aws_tags['Name'] = hostname
      aws_tags['SplunkHostname'] = hostname
      aws_tags['SplunkEnvID'] = splunkPlatformAutomatorID
      if special_host_vars[hostname]['aws']['tags'].nil?
        special_host_vars[hostname]['aws']['tags'] = aws_tags
      else
        special_host_vars[hostname]['aws']['tags'] = special_host_vars[hostname]['aws']['tags'].merge(aws_tags)
      end
    end

    per_host_vars = {}
    ['ip_addr', 'site', 'cname'].each do |var|
      if splunk_host[var]
        var_obj = {}
        var_obj[var] = splunk_host[var]
        per_host_vars=per_host_vars.merge(var_obj)
      end

      if !start_ip.nil?
        # Keep the ip, if defined
        if provider == "virtualbox"
          if splunk_host['ip_addr'].nil?
            per_host_vars['ip_addr'] = base_ip+"."+start_num.to_s
          else
            if !splunk_host['list'].nil? or !splunk_host['iter'].nil?
              print "ERROR: 'ip_addr' not allowed when using 'list' or 'iter'!\n"
              exit 2
            end
          end
        end
      end
    end
    host_vars[hostname] = per_host_vars
    if start_num
      start_num += 1
    end
    hosts_entry = {}
    hosts_entry['name'] = hostname
    if provider == "virtualbox"
      hosts_entry['ip_addr'] = per_host_vars['ip_addr']
    end
    if !per_host_vars['ip_addr'].nil?
      network[hostname] = { 'ip_addr' => per_host_vars['ip_addr'] }
    else
      network[hostname] = { 'ip_addr' => "undef" }
    end
    splunk_host_list.push(hosts_entry)

  end
end

# Update aws_ec2 with custom ansible_user settings
if provider == "aws" and ssh_usernames.length > 0
  # If custom ssh_usernames are defined create a line like this:
  # "[tags.Name] | map('extract', {'uf': 'ec2-user'})|first|default('admin')"
  aws_ec2['compose']['ansible_user'] = "[tags.Name] | map(\"extract\", #{ssh_usernames.to_json})|first|default(\"#{aws_merged['ssh_username']}\")"
  File.open(File.join(config_dir,"aws_ec2.yml"), "w") do |f|
    f.write(aws_ec2.to_yaml)
  end
end

# Create and configure the specified systems
Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  # Loop through YAML file and set per-VM information
  splunk_host_list.each do |server|
    config.vm.define server['name'] do |srv|
      # Setting hostname
      srv.vm.hostname = server['name']

      if provider == "virtualbox"
        # Box image to use
        srv.vm.box = special_host_vars[server['name']]['virtualbox']['box']
        # Define synced folders
        if !special_host_vars[server['name']]['virtualbox']['synced_folder'].nil? and special_host_vars[server['name']]['virtualbox']['synced_folder'].length > 0
          if config.vbguest.no_install == true
            print "ERROR: 'install_vbox_additions' must be set to 'true' to enable synced folders!\n"
            exit 2
          end
          special_host_vars[server['name']]['virtualbox']['synced_folder'].each do |folder|
            srv.vm.synced_folder "#{folder['source']}", "#{folder['target']}"
          end
        end

      elsif provider == "aws"
        # Use dummy AWS box
        srv.vm.box = 'aws-dummy'
      end

      # Don't check for box updates
      #srv.vm.box_check_update = false

      # Splunk need some time to shutdown
      srv.vm.boot_timeout = 600
      srv.vm.graceful_halt_timeout = 600

      # Install vbguest additions
      if Vagrant.has_plugin?("vagrant-vbguest")
        config.vbguest.no_install = true
      end
      if provider == "virtualbox" and special_host_vars[server['name']]['virtualbox']['install_vbox_additions'] == true
        if !Vagrant.has_plugin?("vagrant-vbguest")
          print "ERROR: Plugin vagrant-vbguest missing, install with 'vagrant plugin install vagrant-vbguest'.\n"
          exit 2
        end
        config.vbguest.no_install = false

# Will enable this later again, but needs a propre check
#        # Use Caching for package deployments
#        if Vagrant.has_plugin?("vagrant-cachier")
#          config.cache.scope = :box
#        end
      end

      # Disable default shared folder
      srv.vm.synced_folder '.', '/vagrant', disabled: true

      if provider == "virtualbox"
        srv.vm.network :private_network, ip: server['ip_addr']
      end

# If we need a second disk for testing
#      dataDisk1 = srv.vm.hostname+'dataDisk1.vdi'

      # Set per-server VirtualBox provider configuration/overrides
      if provider == "virtualbox"
        srv.vm.provider :virtualbox do |vb, override|
          #override.vm.box = server['box']['vb']
          vb.memory = special_host_vars[server['name']]['virtualbox']['memory']
          vb.cpus = special_host_vars[server['name']]['virtualbox']['cpus']

# If we need a second disk for testing
#
#        if not File.exists?(dataDisk1)
#          vb.customize ['createmedium', '--filename', dataDisk1, '--variant', 'Standard', '--size', 10 * 1024]
#        end
#        vb.customize ['storageattach', :id, '--storagectl', 'IDE', '--port', 1, '--device', 0, '--type', 'hdd', '--medium', dataDisk1]
          if ENV.key?('VAGRANT_WSL_ENABLE_WINDOWS_ACCESS') and ENV['VAGRANT_WSL_ENABLE_WINDOWS_ACCESS'] == '1'
            vb.customize ['modifyvm', :id, '--uartmode1', 'disconnected']
          end
        end
      elsif provider == "aws"
        # Add all config attributes to the AWS config class
        srv.vm.provider :aws do |aws, override|
          special_host_vars[server['name']]['aws'].each do |k,v|
            next if k == "ssh_username" or k == "ssh_private_key_path"
            aws.send("#{k}=", v)
          end

          # Specify username and private key path
          override.ssh.username = special_host_vars[server['name']]['aws']['ssh_username']
          override.ssh.private_key_path = special_host_vars[server['name']]['aws']['ssh_private_key_path']
        end
      end

      # Create host_vars dir for this host with ssh infos
      if provider == "virtualbox"
        srv.trigger.after :up do |trigger|
          trigger.info = "Update local Ansible inventory"
          trigger.ruby do |env,machine|
            network_info = {}
            network_info['ip_addr'] = network[machine.name.to_s]['ip_addr']
            network_info['ansible_host'] = network[machine.name.to_s]['ip_addr']
            network_info['ansible_port'] = 22
            network_info['ansible_user'] = machine.ssh_info[:username]
            if machine.communicate.ready?
              # Check for Windows guest
              if (machine.communicate.test("test -d $Env:SystemRoot"))
                network_info['ansible_port'] = 5985
                network_info['ansible_password'] = "vagrant"
                network_info['ansible_connection'] = "winrm"
              else
                network_info['ansible_ssh_private_key_file'] = machine.ssh_info[:private_key_path].first
              end
            end
            if File.file?(hosts_file)
              hosts = File.readlines(hosts_file, chomp: true)
            else
              hosts = []
            end
            hosts.append(machine.name.to_s)
            File.open(hosts_file, "w") do |f|
              f.write(hosts.join("\n"))
            end
            FileUtils.mkdir_p(File.join(host_vars_dir, machine.name.to_s))
            File.open(File.join(host_vars_dir, machine.name.to_s,"network_info.yml"), "w") do |f|
              f.write(network_info.to_yaml)
            end
          end
        end
      end

      # Remove host_vars dir for this host
      destroy_trigger = []
      srv.trigger.after :destroy do |trigger|
        if File.directory?(File.join(host_vars_dir, server['name']))
          # Remove host_vars dir for this host
          destroy_trigger.push(File.join(host_vars_dir, server['name']))
        end
        if File.directory?(File.join(splunk_apps['splunk_save_baseconfig_apps_dir'],server['name']))
          # Remove apps dir for this host
          destroy_trigger.push(File.join(splunk_apps['splunk_save_baseconfig_apps_dir'],server['name']))
        end
        if destroy_trigger.length > 0
          trigger.info = "Update local Ansible inventory"
          trigger.ruby do |env,machine|
            FileUtils.rm_rf(destroy_trigger.join(' '))
            hosts_file = File.join(inventory_dir, "hosts")
            if File.file?(hosts_file)
              hosts = File.readlines(hosts_file, chomp: true)
            else
              hosts = []
            end
            hosts.each do |host_entry|
              if host_entry =~ /^#{machine.name.to_s}/
                hosts -= [host_entry]
              end
            end
            File.open(hosts_file, "w") do |f|
              f.write(hosts.join("\n"))
            end
          end
        end
      end

      # Allow remote commands, for example workaround for missing python in ubuntu/xenial64
      # Use this command to install python: 'which python || sudo apt-get -y install python'
      if special_host_vars[server['name']]['os'].has_key?("remote_command")
        srv.vm.provision "shell", inline: "#{special_host_vars[server['name']]['os']['remote_command']}"
      end

      #print "Special host vars:\n"
      #puts special_host_vars
    end
  end
end