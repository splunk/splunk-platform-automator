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
config_file = "#{config_dir}/splunk_config.yml"
inventory_dir = "#{dir}/inventory"
group_vars_dir = "#{inventory_dir}/group_vars"
host_vars_dir = "#{inventory_dir}/host_vars"

# Default values
defaults = {
  "ansible"=>{
    "verbose"=>"",
    "skip_tags"=>[]
  },
  "virtualbox"=>{
    "box"=>"centos/7",
    "memory"=>512,
    "cpus"=>1,
    "install_vbox_additions"=>false,
    "synced_folder"=>nil
  },
  "aws"=>{
    "access_key_id"=>ENV['AWS_ACCESS_KEY_ID'],
    "secret_access_key"=>ENV['AWS_SECRET_ACCESS_KEY'],
    "region"=>"eu-central-1",
    "instance_type"=>"t2.micro"
  },
  "os"=>{
    "time_zone"=>"Europe/Zurich",
    "packages"=>nil
  },
  "splunk_dirs"=>{
    "splunk_baseconfig_dir"=>"../Software",
    "splunk_software_dir"=>"../Software",
    "splunk_auth_dir"=>"../auth",
  },
  "splunk_defaults"=>{
    "splunk_env_name"=>"splk",
    "splunk_version"=>"latest",
    "splunk_admin_password"=>"splunklab",
    "splunk_outputs"=>"all",
    "splunk_search_peers"=>"all",
    "splunk_secret_share"=>{
      "splunk"=>false,
      "splunkforwarder"=>false,
      "equal"=>false
    },
    "splunk_volume_defaults"=>{
      "homePath"=>"primary",
      "coldPath"=>"primary"
    },
    "splunk_ssl"=>{
      "web"=>{
        "enable"=>false,
        "own_certs"=>false
      },
      "inputs"=>{
        "enable"=>false,
        "own_certs"=>false
      },
      "outputs"=>{
        "enable"=>false,
        "own_certs"=>false
      }
    }
  },
  "splunk_systemd"=>{
    "splunk_systemd_services"=>{
      "splunk"=>{
        "Service"=>{
          "LimitCORE"=>0,
          "LimitFSIZE"=>"infinity",
          "LimitDATA"=>"infinity",
          "LimitNPROC"=>20480,
          "LimitNOFILE"=>65536
        }
      }
    }
  },
  "splunk_apps"=>{
    "splunk_save_baseconfig_apps_dirs"=>"apps",
    "splunk_save_baseconfig_apps"=>false,
    "splunk_save_serverclass"=>false
  }
}

# Default ssl settings
defaults_splunk_ssl = {
  "web"=>{
    "config"=>{
      "enableSplunkWebSSL"=>true,
      "privKeyPath"=>"etc/auth/{{splunk_env_name}}/privkey.web.key",
      "serverCert"=>"etc/auth/{{splunk_env_name}}/cacert.web.pem"
    }
  },
  "inputs"=>{
    "config"=>{
      "rootCA"=>"$SPLUNK_HOME/etc/auth/cacert.pem",
      "serverCert"=>"$SPLUNK_HOME/etc/auth/server.pem",
      "sslPassword"=>"password"
    }
  },
  "outputs"=>{
    "config"=>{
      "sslRootCAPath"=>"$SPLUNK_HOME/etc/auth/cacert.pem",
      "sslCertPath"=>"$SPLUNK_HOME/etc/auth/server.pem",
      "sslPassword"=>"password"
    }
  }
}

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

# Create splunk_dirs variables
splunk_dirs = defaults['splunk_dirs'].dup
if !settings['splunk_dirs'].nil?
  splunk_dirs = splunk_dirs.merge(settings['splunk_dirs'])
end

# Create splunk_apps variables
splunk_apps = defaults['splunk_apps'].dup
if !settings['splunk_apps'].nil?
  splunk_apps = splunk_apps.merge(settings['splunk_apps'])
end

# Create splunk_systemd variables
splunk_systemd = defaults['splunk_systemd'].dup
if !settings['splunk_systemd'].nil?
  splunk_systemd = splunk_systemd.merge(settings['splunk_systemd'])
end

# Create auth_dir
if !File.directory?("#{dir}/ansible/#{splunk_dirs['splunk_auth_dir']}")
  FileUtils.mkdir_p("#{dir}/ansible/#{splunk_dirs['splunk_auth_dir']}")
end

# Get timezone from the vagrant host as default for the virtual machines
defaults['os']['time_zone'] = `ls -l /etc/localtime | sed -e 's%.*zoneinfo/%%' | tr -d '\n'`

# Create splunk_defaults variables
splunk_defaults = defaults['splunk_defaults'].dup
if !settings['splunk_defaults'].nil?
  splunk_defaults = splunk_defaults.merge(settings['splunk_defaults'])
  # Treat ssl config individually, cause merging does not work for this deep levels
  defaults['splunk_defaults']['splunk_ssl'].each do |ssl_type, ssl_config|
    if !settings['splunk_defaults']['splunk_ssl'].nil? and !settings['splunk_defaults']['splunk_ssl'][ssl_type].nil?
      splunk_defaults['splunk_ssl'][ssl_type] = ssl_config.merge(settings['splunk_defaults']['splunk_ssl'][ssl_type])
    else
      splunk_defaults['splunk_ssl'][ssl_type] = ssl_config.dup
    end
    if !settings['splunk_defaults']['splunk_ssl'].nil? and !settings['splunk_defaults']['splunk_ssl'][ssl_type].nil? and settings['splunk_defaults']['splunk_ssl'][ssl_type]['enable'] == true
      if !settings['splunk_defaults']['splunk_ssl'][ssl_type]['config'].nil?
        splunk_defaults['splunk_ssl'][ssl_type]['config'] = defaults_splunk_ssl[ssl_type]['config'].merge(settings['splunk_defaults']['splunk_ssl'][ssl_type]['config'])
      else
        splunk_defaults['splunk_ssl'][ssl_type]['config'] = defaults_splunk_ssl[ssl_type]['config'].dup
      end
    end
    if ssl_type == "web" and splunk_defaults['splunk_ssl'][ssl_type]['own_certs'] == false
      splunk_defaults['splunk_ssl'][ssl_type]['config'] = {"enableSplunkWebSSL"=>true}
    end
  end
end

# Create splunk_environments group_vars
splunk_environments = []
if !settings['splunk_environments'].nil?
  settings['splunk_environments'].each do |splunkenv|
    env_obj = splunk_defaults.merge(splunkenv)
    splunk_environments.push(env_obj)
  end
else
  splunk_environments.push(splunk_defaults)
end

# Check for Splunk baseconfig apps
check_base = Dir.glob(dir+"/"+splunk_dirs['splunk_baseconfig_dir']+"/*/org_all_indexer_base")
check_cluster = Dir.glob(dir+"/"+splunk_dirs['splunk_baseconfig_dir']+"/*/org_cluster_indexer_base")
if check_base.length < 1 or check_cluster.length < 1
  print "ERROR: Please download the Splunk baseconfig apps here and extract it into #{dir}/#{splunk_dirs['splunk_baseconfig_dir']} \n\n"
  print "Configurations Base:      https://splunk.app.box.com/ConfigurationsBase\n"
  print "Configurations Cluster:   https://splunk.app.box.com/ConfigurationsCluster\n"
  exit 2
end

## Check for Splunk installer archives
splunk_environments.each do |splunkenv|
  ['splunk','splunkforwarder'].each do |splunk_arch|
    if splunkenv['splunk_version'] == 'latest'
      search_version = "*"
    else
      search_version = splunkenv['splunk_version']
    end
    check_arch = Dir.glob(dir+"/"+splunk_dirs['splunk_software_dir']+"/"+splunk_arch+"-"+search_version+"-*Linux-x86_64.tgz")
    if check_arch.length < 1
      print "ERROR: #{splunk_arch} version '#{splunkenv['splunk_version']}' missing in #{dir}/#{splunk_dirs['splunk_software_dir']}\n\n"
      print "Download "+splunk_arch+"-"+search_version+"-...-Linux-x86_64.tgz at https://www.splunk.com/download\n"
      exit 2
    end
  end
  # Check for Splunk license file
  if !splunkenv['splunk_license_file'].nil?
    if !File.file?(dir+"/"+splunk_dirs['splunk_software_dir']+"/"+splunkenv['splunk_license_file'])
      print "ERROR: Cannot find license file #{splunk_dirs['splunk_software_dir']+"/"+splunkenv['splunk_license_file']} \n\n"
      print "Comment variable 'splunk_license_file' in #{config_file} if no license available\n"
      exit 2
    end
  end
end


# Check for virtualization provider
if !settings.has_key?("virtualbox") and !settings.has_key?("aws")
    print "ERROR: No virtualization provider defined in #{config_file} \n\n"
    print "Supported types are virtualbox or aws\n"
    exit 2
end
if settings.has_key?("virtualbox")
  provider = "virtualbox"
  if !Vagrant.has_plugin?("vagrant-vbguest")
    print "ERROR: Plugin for virtualbox provider is missing, install with 'vagrant plugin install vagrant-vbguest'.\n"
    exit 2
  end
elsif settings.has_key?("aws")
  provider = "aws"
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
groups = {}
idxc_list = {}
idxc_sites = {}
shc_list = {}
outputs_list = {}
outputs_groups = {}
search_peer_list = {}
search_peer_groups = {}
envs = {}
special_host_vars = {}
network = {}

# Remove this in the future, cause only needed during upgrades
# Clean up host_vars directory
if File.directory?("#{dir}/ansible/host_vars")
  FileUtils.rm_r("#{dir}/ansible/host_vars")
end

# Clean up inventory/group_vars directory
if File.directory?("#{group_vars_dir}")
  FileUtils.rm_r("#{group_vars_dir}")
end
# Create up inventory/group_vars/all and inventory/host_vars directory
FileUtils.mkdir_p("#{group_vars_dir}/all")
FileUtils.mkdir_p("#{host_vars_dir}")

# Create inventory host groups
settings['splunk_hosts'].each do |splunk_host|
  var_obj = defaults.dup
  ['ansible','virtualbox','aws'].each do |config_group|
    if !settings[config_group].nil?
      var_obj[config_group] = var_obj[config_group].merge(settings[config_group])
    end
    if !splunk_host[config_group].nil?
      var_obj[config_group] = var_obj[config_group].merge(splunk_host[config_group])
    end
  end
  special_host_vars[splunk_host['name']] = var_obj.dup

  # Create os host_vars
  if !splunk_host['os'].nil?
    if !File.directory?("#{host_vars_dir}/#{splunk_host['name']}")
      FileUtils.mkdir_p("#{host_vars_dir}/#{splunk_host['name']}")
    end
    File.open("#{host_vars_dir}/#{splunk_host['name']}/os.yml", "w") do |f|
      f.write(splunk_host['os'].to_yaml)
    end
  end

  # Create splunk_env host_vars
  splunk_env = {}
  ['splunk_version','splunk_admin_password','splunk_license_file','splunk_indexes','splunk_outputs','splunk_search_peers'].each do |splunk_var|
    if !splunk_host[splunk_var].nil?
      splunk_env[splunk_var] = splunk_host[splunk_var]
    end
  end
  if splunk_env.length > 0
    if !File.directory?("#{host_vars_dir}/#{splunk_host['name']}")
      FileUtils.mkdir_p("#{host_vars_dir}/#{splunk_host['name']}")
    end
    File.open("#{host_vars_dir}/#{splunk_host['name']}/splunk_env.yml", "w") do |f|
      f.write(splunk_env.to_yaml)
    end
  end

  # Build the ansible groups
  splunk_host['roles'].each do |role|
    if groups.has_key?("role_"+role)
      groups["role_"+role].push(splunk_host['name'])
    else
      groups["role_"+role] = [splunk_host['name']]
    end
    var_obj = {}
    if !splunk_host['splunk_env'].nil?
      if splunk_environments.find {|i| i["splunk_env_name"] == splunk_host['splunk_env']}.nil?
        print "ERROR: Cannot find splunk_env_name #{splunk_host['splunk_env']} from host #{splunk_host['name']} in config! \n\n"
        exit 2
      end
    else
      splunk_host['splunk_env'] = splunk_environments[0]['splunk_env_name']
    end

    # Add the management nodes here as well, since the role_* groups are not completely populated from the beginning
    ['deployment_server','monitoring_console', 'license_master'].each do |role_def|
      if role == role_def
        # Check if license file is available for license master
        if role_def == "license_master" and splunk_environments.find {|i| i["splunk_env_name"] == splunk_host['splunk_env']}["splunk_license_file"].nil?
          print "ERROR: Role 'license_master' on Splunk host '#{splunk_host['name']}' is not allowed if no license file available! \n\n"
          exit 2
        end
      end
    end

    # Create indexer cluster member list
    if role == 'indexer' and splunk_host['idxcluster']
      if idxc_list.has_key?(splunk_host['idxcluster'])
        if not idxc_list[splunk_host['idxcluster']].include?(splunk_host['name'])
          idxc_list[splunk_host['idxcluster']].push(splunk_host['name'])
        end
      else
        idxc_list[splunk_host['idxcluster']] = [splunk_host['name']]
      end
      # Create the site list
      if splunk_host['site']
        if idxc_sites.has_key?(splunk_host['idxcluster'])
          if not idxc_sites[splunk_host['idxcluster']].include?(splunk_host['site'])
            idxc_sites[splunk_host['idxcluster']].push(splunk_host['site'])
          end
        else
          idxc_sites[splunk_host['idxcluster']] = [splunk_host['site']]
        end
      end
    end

    # Build the outputs list
    if role == 'indexer' or role == 'heavy_forwarder'
      if not outputs_list.has_key?(splunk_host['splunk_env'])
        outputs_list[splunk_host['splunk_env']] = {}
      end
      if splunk_host['idxcluster']
        if not outputs_list[splunk_host['splunk_env']].has_key?('idxcluster')
          outputs_list[splunk_host['splunk_env']]['idxcluster'] = {}
        end
        if not outputs_list[splunk_host['splunk_env']]['idxcluster'].has_key?(splunk_host['idxcluster'])
          outputs_list[splunk_host['splunk_env']]['idxcluster'][splunk_host['idxcluster']] = idxc_list[splunk_host['idxcluster']]
        end
      else
        if not outputs_list[splunk_host['splunk_env']].has_key?(role)
          outputs_list[splunk_host['splunk_env']][role] = []
        end
        if not outputs_list[splunk_host['splunk_env']][role].include?(splunk_host['name'])
          outputs_list[splunk_host['splunk_env']][role].push(splunk_host['name'])
        end
      end
    end

    # Build the search_peer list
    if role == 'indexer' or role == 'cluster_master'
      if not search_peer_list.has_key?(splunk_host['splunk_env'])
        search_peer_list[splunk_host['splunk_env']] = {}
      end
      if role == 'cluster_master' and splunk_host['idxcluster']
        if not search_peer_list[splunk_host['splunk_env']].has_key?('idxcluster')
          search_peer_list[splunk_host['splunk_env']]['idxcluster'] = {}
        end
        if not search_peer_list[splunk_host['splunk_env']]['idxcluster'].has_key?(splunk_host['idxcluster'])
          search_peer_list[splunk_host['splunk_env']]['idxcluster'][splunk_host['idxcluster']] = splunk_host['name']
        end
      elsif role == 'indexer' and not splunk_host['idxcluster']
        if not search_peer_list[splunk_host['splunk_env']].has_key?(role)
          search_peer_list[splunk_host['splunk_env']][role] = []
        end
        if not search_peer_list[splunk_host['splunk_env']][role].include?(splunk_host['name'])
          search_peer_list[splunk_host['splunk_env']][role].push(splunk_host['name'])
        end
      end
    end

    # Create search head cluster member list
    if role == 'search_head' and splunk_host['shcluster']
      if shc_list.has_key?(splunk_host['shcluster'])
        if not shc_list[splunk_host['shcluster']].include?(splunk_host['name'])
          shc_list[splunk_host['shcluster']].push(splunk_host['name'])
        end
      else
        shc_list[splunk_host['shcluster']] = [splunk_host['name']]
      end
    end
  end

  # Splunk environment and cluster groups
  ['splunk_env','idxcluster','shcluster'].each do |var|
    tmparray = []
    if splunk_host[var].kind_of?(Array)
      tmparray = splunk_host[var]
    else
      tmparray = [splunk_host[var]]
    end
    tmparray.each do |item|
      if splunk_host[var]
        groupname = var+"_"+item
        if groups.has_key?(groupname)
          groups[groupname].push(splunk_host['name'])
        else
          groups[groupname] = [splunk_host['name']]
        end
      end
    end
  end
end

# Create the output groups
settings['splunk_hosts'].each do |splunk_host|
  splunk_host['roles'].each do |role|
    if role != 'indexer'
      if splunk_host.has_key?('splunk_outputs')
        output = splunk_host['splunk_outputs']
      else
        output = splunk_environments.find {|i| i["splunk_env_name"] == splunk_host['splunk_env']}["splunk_outputs"]
      end
      groupname = "output_"+splunk_host['splunk_env']+"_"+output
      if not outputs_groups.has_key?(groupname)
        outputs_groups[groupname] = {}
        if output == 'all'
          if outputs_list[splunk_host['splunk_env']].has_key?('idxcluster')
            outputs_groups[groupname]['idxcluster'] = outputs_list[splunk_host['splunk_env']]['idxcluster']
          end
          if outputs_list[splunk_host['splunk_env']].has_key?('indexer')
            outputs_groups[groupname]['indexer'] = outputs_list[splunk_host['splunk_env']]['indexer']
          end
        end
      end
      if groups.has_key?(groupname)
        if not groups[groupname].include?(splunk_host['name'])
          groups[groupname].push(splunk_host['name'])
        end
      else
        groups[groupname] = [splunk_host['name']]
      end
    end
  end
end

# Create the search_peer groups
settings['splunk_hosts'].each do |splunk_host|
  splunk_host['roles'].each do |role|
    if ['search_head','monitoring_console'].include?(role)
      if splunk_host.has_key?('splunk_search_peers')
        search_peer = splunk_host['splunk_search_peers']
      else
        search_peer = splunk_environments.find {|i| i["splunk_env_name"] == splunk_host['splunk_env']}["splunk_search_peers"]
      end
      groupname = "search_peer_"+splunk_host['splunk_env']+"_"+search_peer
      if not search_peer_groups.has_key?(groupname)
        search_peer_groups[groupname] = {}
        if search_peer == 'all'
          if search_peer_list[splunk_host['splunk_env']].has_key?('idxcluster')
            search_peer_groups[groupname]['idxcluster'] = search_peer_list[splunk_host['splunk_env']]['idxcluster']
          end
          if search_peer_list[splunk_host['splunk_env']].has_key?('indexer')
            search_peer_groups[groupname]['indexer'] = search_peer_list[splunk_host['splunk_env']]['indexer']
          end
        end
      end
      if groups.has_key?(groupname)
        if not groups[groupname].include?(splunk_host['name'])
          groups[groupname].push(splunk_host['name'])
        end
      else
        groups[groupname] = [splunk_host['name']]
      end
    end
  end
end

# Remove this in the future, cause only needed during upgrades
# Cleanup old group_vars files
Dir['ansible/group_vars/**/*'].select{|f| File.file?(f) }.each do |filepath|
  File.delete(filepath) if File.basename(filepath) != "dynamic.yml"
end

# Create os group_vars
os_defaults = defaults['os'].dup
if !settings['os'].nil?
  os_defaults = os_defaults.merge(settings['os'])
end
File.open("#{group_vars_dir}/all/os.yml", "w") do |f|
  f.write(os_defaults.to_yaml)
end

# Create splunk_basics group_vars
if !splunk_dirs.nil?
  File.open("#{group_vars_dir}/all/splunk_dirs.yml", "w") do |f|
    f.write(splunk_dirs.to_yaml)
  end
end

# Create splunk_systemd group_vars
if !splunk_systemd.nil?
  File.open("#{group_vars_dir}/all/splunk_systemd.yml", "w") do |f|
    f.write(splunk_systemd.to_yaml)
  end
end

# Create splunk_apps group_vars
if !splunk_apps.nil?
  File.open("#{group_vars_dir}/all/splunk_apps.yml", "w") do |f|
    f.write(splunk_apps.to_yaml)
  end
end

# Create splunk environment group_vars
if !splunk_environments.nil?
  splunk_environments.each do |splunkenv|
    group_name = "splunk_env_"+splunkenv['splunk_env_name']
    if envs.has_key?(group_name)
      splunkenv = splunkenv.merge(envs[group_name])
    end
    File.open("#{group_vars_dir}/#{group_name}.yml", "w") do |f|
      f.write(splunkenv.to_yaml)
    end
  end
end

# Create splunk indexer cluster group_vars
if !settings['splunk_idxclusters'].nil?
  settings['splunk_idxclusters'].each do |idxcluster|
    group_name = "idxcluster_"+idxcluster['idxc_name']
    if idxc_sites[idxcluster['idxc_name']]
      idxcluster['idxc_available_sites'] = idxc_sites[idxcluster['idxc_name']]
    end
    File.open("#{group_vars_dir}/#{group_name}.yml", "w") do |f|
      f.write(idxcluster.to_yaml)
    end
  end
end

# Create splunk search head cluster group_vars
if !settings['splunk_shclusters'].nil?
  settings['splunk_shclusters'].each do |shcluster|
    group_name = "shcluster_"+shcluster['shc_name']
    File.open("#{group_vars_dir}/#{group_name}.yml", "w") do |f|
      f.write(shcluster.to_yaml)
    end
  end
end

# Create splunk outputs group_vars
if !outputs_groups.nil?
  outputs_groups.each do |group_name, group_content|
    outputs = {}
    outputs['splunk_outputs_list'] = group_content.dup
    File.open("#{group_vars_dir}/#{group_name}.yml", "w") do |f|
      f.write(outputs.to_yaml)
    end
  end
end

# Create splunk search_peers group_vars
if !search_peer_groups.nil?
  search_peer_groups.each do |group_name, group_content|
    search_peers = {}
    search_peers['splunk_search_peer_list'] = group_content.dup
    File.open("#{group_vars_dir}/#{group_name}.yml", "w") do |f|
      f.write(search_peers.to_yaml)
    end
  end
end

# If dynamic IPs are used, calculate the start number
if !settings['general'].nil? and !settings['general']['start_ip'].nil?
  ip_array = settings['general']['start_ip'].split(".")
  base_ip = ip_array[0..2].join(".")
  start_num = ip_array[3].to_i
end

# Create inventory host vars
host_vars = {}
splunk_host_list = []
settings['splunk_hosts'].each do |splunk_host|
  per_host_vars = {}
  ['ip_addr', 'site', 'cname'].each do |var|
    if !settings['general'].nil? and !settings['general']['start_ip'].nil?
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
        #srv.vm.box = settings['virtualbox']['box']
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

        # Force serial execution for now until the playbooks are reworked
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

      # Create ansible inventory/hosts
      if !host_vars.nil?
        File.open("inventory/hosts" ,'w') do |f|
          host_vars.each do |host_name, host_var_list|
            host_vars_conf = "#{host_name}"
            host_var_list.each do |host_var_name, host_var_value|
              host_vars_conf += " #{host_var_name}=#{host_var_value}"
            end
            f.write "#{host_vars_conf}\n"
          end
        end
      end

      # Create ansible inventory/groups
      if !groups.nil?
        File.open("inventory/groups" ,'w') do |f|
          groups.each do |group_name, group_hosts|
            f.write "[#{group_name}]\n"
            group_hosts.each do |group_host|
              f.write "#{group_host}\n"
            end
            f.write "\n"
          end
        end
      end

      # Remove host_vars dir for this host
      destroy_trigger = []
      srv.trigger.after :destroy do |trigger|
        if File.directory?("#{host_vars_dir}/#{server['name']}")
          # Remove host_vars dir for this host
          destroy_trigger.push("#{host_vars_dir}/#{server['name']}")
        end
        if File.directory?("#{splunk_apps['splunk_save_baseconfig_apps_dirs']}/#{server['name']}")
          # Remove apps dir for this host
          destroy_trigger.push("#{splunk_apps['splunk_save_baseconfig_apps_dirs']}/#{server['name']}")
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
        elsif vm.provider_name == :aws
          if File.file?("#{host_vars_dir}/#{vm.name}/network.yml")
            network_info = YAML.load_file("#{host_vars_dir}/#{vm.name}/network.yml")
            ip_addr_list[vmname] = network_info['ip_addr']
          elsif ip_addr_list[vmname].nil?
            if vm.communicate.ready?
              vm.communicate.execute('hostname --all-ip-addresses') do |type, privat_ip|
                allips = privat_ip.strip().split(' ')
                ip_addr_list[vmname] = allips[0]
                #network_info['ip_addr'] = allips[0]
              end
            end
          end
        end
        if !ip_addr_list[vmname].nil?
          network_info['ip_addr'] = ip_addr_list[vmname]
        end

        if !File.file?("#{host_vars_dir}/#{vm.name}/ansible_ssh_info.yml") or vm.provider_name == :aws
          if ssh_info = (vm.ssh_info && vm.ssh_info.dup)
            ansible_ssh_info = {}
            ansible_ssh_info['ansible_host'] = ssh_info[:host]
            ansible_ssh_info['ansible_port'] = ssh_info[:port]
            if vm.provider_name == :aws and network_info['dns_name'] != ssh_info[:host]
              network_info['dns_name'] = ssh_info[:host]
              update_file = true
            end
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
          if update_file == true
            File.open("#{host_vars_dir}/#{vm.name}/network.yml", "w") do |f|
              f.write(network_info.to_yaml)
            end
          end
        end

        # Create HTML link page for all the roles
        if update_index_html == true
          require 'erb'
          settings['splunk_hosts'].each do |host|
            network_file = {}
            if File.file?("#{host_vars_dir}/#{host['name']}/network.yml")
              network_file[host['name']] = YAML.load_file("#{host_vars_dir}/#{host['name']}/network.yml")
              network = network.merge(network_file)
            end
          end
          template = File.read("#{dir}/template/index.html.erb")
          result = ERB.new(template).result(binding)
          File.open("#{config_dir}/index.html", 'w+') do |f|
            f.write result
          end
        end
        ip_addr_list[vmname]
      end

      # Allow remote commands, for example workaround for missing python in ubuntu/xenial64
      # Use this command to install python: 'which python || sudo apt-get -y install python'
      if File.file?("#{group_vars_dir}/all/os.yml")
          os_info = YAML.load_file("#{group_vars_dir}/all/os.yml")
          if os_info['remote_command']
            srv.vm.provision "shell", inline: "#{os_info['remote_command']}"
          end
      end
      if File.file?("#{host_vars_dir}/#{server['name']}/os.yml")
          os_info = YAML.load_file("#{host_vars_dir}/#{server['name']}/os.yml")
          if os_info['remote_command']
            srv.vm.provision "shell", inline: "#{os_info['remote_command']}"
          end
      end

      #print "Special host vars:\n"
      #puts special_host_vars

      srv.vm.provision "ansible" do |ansible|
        ansible.compatibility_mode = "2.0"
        ansible.inventory_path = "inventory"
        ansible.skip_tags = special_host_vars[server['name']]['ansible']['skip_tags']
        ansible.verbose = special_host_vars[server['name']]['ansible']['verbose']
        ansible.playbook = "ansible/splunk.yml"
      end
    end
  end
end
