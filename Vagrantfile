# -*- mode: ruby -*-
#
# This file is part of Splunkenizer
#
###############################################################################
# Copyright 2018 Marco Stadler
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
Vagrant.require_version '>= 1.6.0'
VAGRANTFILE_API_VERSION = '2'

require 'yaml'
dir = File.dirname(File.expand_path(__FILE__))
config_dir = "#{dir}/config"
defaults_dir = "#{dir}/defaults"
config_file = "#{config_dir}/splunk_config.yml"
inventory_dir = "#{dir}/inventory"
host_vars_dir = "#{inventory_dir}/host_vars"
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

# Create config_dir
if !File.directory?("#{config_dir}")
  FileUtils.mkdir_p("#{config_dir}")
end

if !File.file?("#{config_file}")
  print "ERROR: Please copy a config file from the examples dir to #{config_file} to continue\n"
  exit 2
end

# Read YAML file with instance information (box, CPU, RAM, IP addresses)
# Edit the config file to change VM and environment configuration details
settings = YAML.load_file("#{config_file}")

# Create splunk_apps variables
splunk_apps = YAML.load_file("#{defaults_dir}/splunk_apps.yml")
defaults['splunk_apps'] = splunk_apps['splunk_apps']
splunk_apps = defaults['splunk_apps'].dup
if !settings['splunk_apps'].nil?
  splunk_apps = splunk_apps.merge(settings['splunk_apps'])
end

#TODO: Remove
# # Create auth_dir
# if !File.directory?("#{dir}/ansible/#{splunk_dirs['splunk_auth_dir']}")
#   FileUtils.mkdir_p("#{dir}/ansible/#{splunk_dirs['splunk_auth_dir']}")
# end

# Check for virtualization provider
if !settings.has_key?("virtualbox") and !settings.has_key?("aws")
    print "ERROR: No virtualization provider defined in #{config_file} \n\n"
    print "Supported types are virtualbox or aws\n"
    exit 2
end
if settings.has_key?("virtualbox")
  provider = "virtualbox"
  virtualbox = YAML.load_file("#{defaults_dir}/virtualbox.yml")
  defaults['virtualbox'] = virtualbox['virtualbox']
  if !Vagrant.has_plugin?("vagrant-vbguest")
    print "ERROR: Plugin for virtualbox provider is missing, install with 'vagrant plugin install vagrant-vbguest'.\n"
    exit 2
  end
elsif settings.has_key?("aws")
  provider = "aws"
  aws = YAML.load_file("#{defaults_dir}/aws.yml")
  defaults['aws'] = aws['aws']
  # Read access keys from environment variable, if not spcified in settings
  if !defaults['aws'].has_key?("access_key_id")
    defaults['aws']['access_key_id'] = ENV['AWS_ACCESS_KEY_ID']
  end
  if !defaults['aws'].has_key?("secret_access_key")
    defaults['aws']['secret_access_key'] = ENV['AWS_SECRET_ACCESS_KEY']
  end
  if !Vagrant.has_plugin?("vagrant-aws")
    print "ERROR: Plugin for AWS provider missing, install with 'vagrant plugin install vagrant-aws'.\n"
    exit 2
  end
  if !settings['general'].nil? and settings['general'].has_key?("start_ip")
    print "WARN: Ignoring general.start_ip setting for AWS provider.\n"
    print "INFO: You can remove this setting from the config file.\n"
    settings['general'].delete("start_ip")
  end
end

# Check for hostmanager plugin
if !Vagrant.has_plugin?("vagrant-hostmanager")
  print "ERROR: Plugin 'vagrant-hostmanager' is missing, install with 'vagrant plugin install vagrant-hostmanager'.\n"
  exit 2
end

# Create ansible inventory from the config file
special_host_vars = {}
network = {}
defaults['os'] = {}

# Create inventory/host_vars directory
FileUtils.mkdir_p("#{host_vars_dir}")

# Create inventory host groups
settings['splunk_hosts'].each do |splunk_host|
  var_obj = defaults.dup
  ['virtualbox','aws','os'].each do |config_group|
    if !settings[config_group].nil?
      var_obj[config_group] = var_obj[config_group].merge(settings[config_group])
    end
    if !splunk_host[config_group].nil?
      var_obj[config_group] = var_obj[config_group].merge(splunk_host[config_group])
    end
  end
  special_host_vars[splunk_host['name']] = var_obj.dup
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

# Create inventory host vars
host_vars = {}
splunk_host_list = []
settings['splunk_hosts'].each do |splunk_host|
  per_host_vars = {}
  ['ip_addr', 'site', 'cname'].each do |var|
    if !start_ip.nil?
      # Keep the ip, if defined
      if provider == "virtualbox"
        if splunk_host['ip_addr'].nil?
          splunk_host['ip_addr'] = base_ip+"."+start_num.to_s
        end
      end
    end
    if splunk_host[var]
      var_obj = {}
      var_obj[var] = splunk_host[var]
      per_host_vars=per_host_vars.merge(var_obj)
    end
  end
  host_vars[splunk_host['name']] = per_host_vars
  if start_num
    start_num += 1
  end
  hosts_entry = {}
  hosts_entry['name'] = splunk_host['name']
  if provider == "virtualbox"
    hosts_entry['ip_addr'] = splunk_host['ip_addr']
  end
  if !splunk_host['ip_addr'].nil?
    network[splunk_host['name']] = { 'ip_addr' => splunk_host['ip_addr'] }
  else
    network[splunk_host['name']] = { 'ip_addr' => "undef" }
  end
  splunk_host_list.push(hosts_entry)
end

# Write out hosts content to build /etc/hosts file
splunk_hosts = {}
splunk_hosts['splunk_hosts'] = splunk_host_list
#File.open("#{group_vars_dir}/all/hosts.yml", "w") do |f|
#  f.write(splunk_hosts.to_yaml)
#end

# Create and configure the specified systems
Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.hostmanager.enabled = true
  config.hostmanager.manage_guest = true
  config.hostmanager.include_offline = true
  if provider == "aws"
    config.hostmanager.include_offline = false
  end

  # Loop through YAML file and set per-VM information
  settings['splunk_hosts'].each do |server|
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
        special_host_vars[server['name']]['ansible']['skip_tags'].push('fix_time_sync')

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
        end
      elsif provider == "aws"

        # Parallel vm creation does still not work because of the hostmanager
        ENV['VAGRANT_NO_PARALLEL'] = 'yes'

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

      # Remove host_vars dir for this host
      destroy_trigger = []
      srv.trigger.after :destroy do |trigger|
        if File.directory?("#{host_vars_dir}/#{server['name']}")
          # Remove host_vars dir for this host
          destroy_trigger.push("#{host_vars_dir}/#{server['name']}")
        end
        if File.directory?("#{splunk_apps['splunk_save_baseconfig_apps_dir']}/#{server['name']}")
          # Remove apps dir for this host
          destroy_trigger.push("#{splunk_apps['splunk_save_baseconfig_apps_dir']}/#{server['name']}")
        end
        if destroy_trigger.length > 0
          trigger.run = { inline: "rm -r #{destroy_trigger.join(" ")}" }
        end
      end

      # Update ansible inventory/hosts with ansible variables
      srv.vm.provision :hostmanager
      ip_addr_list = {}
      srv.hostmanager.ip_resolver = proc do |vm, resolving_vm|
        vmname = vm.name.to_s
        network_info = {}
        update_file = false
        update_index_html = false
        if vm.provider_name == :virtualbox and !host_vars[vmname]['ip_addr'].nil? and ip_addr_list[vmname].nil?
          ip_addr_list[vmname] = host_vars[vmname]['ip_addr']
        # elsif vm.provider_name == :aws
        #   if File.file?("#{host_vars_dir}/#{vm.name}/network.yml")
        #     network_info = YAML.load_file("#{host_vars_dir}/#{vm.name}/network.yml")
        #     ip_addr_list[vmname] = network_info['ip_addr']
        #   elsif ip_addr_list[vmname].nil?
        #     if vm.communicate.ready?
        #       vm.communicate.execute('hostname --ip-address') do |type, privat_ip|
        #         allips = privat_ip.strip().split(' ')
        #         ip_addr_list[vmname] = allips[0]
        #         #network_info['ip_addr'] = allips[0]
        #       end
        #     end
        #   end
        end
        if !ip_addr_list[vmname].nil?
          network_info['ip_addr'] = ip_addr_list[vmname]
        end

        if !File.file?("#{host_vars_dir}/#{vm.name}/ansible_ssh_info.yml") and vm.provider_name == :virtualbox
          if ssh_info = (vm.ssh_info && vm.ssh_info.dup)
            ansible_ssh_info = {}
            ansible_ssh_info['ansible_host'] = ssh_info[:host]
            ansible_ssh_info['ansible_port'] = ssh_info[:port]
            # if vm.provider_name == :aws and network_info['dns_name'] != ssh_info[:host]
            #   network_info['dns_name'] = ssh_info[:host]
            #   update_file = true
            # end
            ansible_ssh_info['ansible_user'] = ssh_info[:username]
            if vm.provider_name == :virtualbox and !host_vars[vmname]['ip_addr'].nil?
              ansible_ssh_info['ansible_host'] = host_vars[vmname]['ip_addr']
              ansible_ssh_info['ansible_port'] = 22
            end
            if vm.communicate.ready?
              # Check for Windows guest
              if (vm.communicate.test("test -d $Env:SystemRoot"))
                ansible_ssh_info['ansible_port'] = 5985
                ansible_ssh_info['ansible_password'] = "vagrant"
                ansible_ssh_info['ansible_connection'] = "winrm"
              else
                ansible_ssh_info['ansible_ssh_private_key_file'] = ssh_info[:private_key_path].first
              end
            end
            FileUtils.mkdir_p("#{host_vars_dir}/#{vm.name}")
            if vm.provider_name == :virtualbox or update_file == true
              File.open("#{host_vars_dir}/#{vm.name}/ansible_ssh_info.yml", "w") do |f|
                f.write(ansible_ssh_info.to_yaml)
              end
              update_index_html = true
            end
          end
          # if update_file == true
          #   File.open("#{host_vars_dir}/#{vm.name}/network.yml", "w") do |f|
          #     f.write(network_info.to_yaml)
          #   end
          # end
        end

        #TODO: move this to the inventory plugin
        # # Create HTML link page for all the roles
        # if update_index_html == true
        #   require 'erb'
        #   settings['splunk_hosts'].each do |host|
        #     network_file = {}
        #     #TODO: extract this straight out of the config file
        #     if File.file?("#{host_vars_dir}/#{host['name']}/network.yml")
        #       network_file[host['name']] = YAML.load_file("#{host_vars_dir}/#{host['name']}/network.yml")
        #       network = network.merge(network_file)
        #     end
        #   end
        #   template = File.read("#{dir}/template/index.html.erb")
        #   result = ERB.new(template).result(binding)
        #   File.open("#{config_dir}/index.html", 'w+') do |f|
        #     f.write result
        #   end
        # end
        ip_addr_list[vmname]
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
