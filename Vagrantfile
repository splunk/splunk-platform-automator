# -*- mode: ruby -*-
# vi: set ft=ruby :

# Specify minimum Vagrant version and Vagrant API version
Vagrant.require_version '>= 1.6.0'
VAGRANTFILE_API_VERSION = '2'

require 'yaml'
dir = File.dirname(File.expand_path(__FILE__))
config_file = "splunk_config.yml"
config_dir = "config"
certs_dir = "certs"

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
  "os"=>{
    "time_zone"=>"Europe/Zurich",
    "packages"=>nil
    },
  "splunk_dirs"=>{
    "splunk_baseconfig_dir"=>"../Software",
    "splunk_software_dir"=>"../Software"
    },
  "splunk_defaults"=>{
    "splunk_env_name"=>"splk",
    "splunk_version"=>"latest",
    "splunk_admin_password"=>"splunklab",
    "splunk_outputs"=>"all",
    "splunk_search_peers"=>"all",
    "splunk_volume_defaults"=>{
      "homePath"=>"primary",
      "coldPath"=>"primary"
      },
    "splunk_ssl"=>{
      "web"=>{
        "enable"=>false,
        "own_certs"=>false,
        "config"=>{
          "enableSplunkWebSSL"=>true,
          "privKeyPath"=>"etc/auth/{{splunk_env_name}}/privkey.web.key",
          "serverCert"=>"etc/auth/{{splunk_env_name}}/cacert.web.pem"
        },
      },
      "inputs"=>{
        "enable"=>false,
        "own_certs"=>false,
        "config"=>{
          "rootCA"=>"$SPLUNK_HOME/etc/auth/cacert.pem",
          "serverCert"=>"$SPLUNK_HOME/etc/auth/server.pem"
        }
      },
      "outputs"=>{
        "enable"=>false,
        "own_certs"=>false,
        "config"=>{
          "sslRootCAPath"=>"$SPLUNK_HOME/etc/auth/cacert.pem",
          "sslCertPath"=>"$SPLUNK_HOME/etc/auth/client.pem",
          "sslPassword"=>"password"
        }
      }
    }
  }
}
#puts JSON.pretty_generate(defaults)

# Check for Ansible binary
system("type ansible > /dev/null 2>&1")
if $?.exitstatus != 0
  print "ERROR: Cannot find ansible binary\n"
  exit 2
end

# Check for supported ansible version
ansible_version_supported = '2.4.3.*'
ansible_version = `ansible --version | head -1 | awk '{print $2}' | tr -d '\n'`
if !ansible_version.match(ansible_version_supported)
  print "ERROR: Ansible version #{ansible_version} not supported with Splunkenizer\n"
  print "Support versions are: #{ansible_version_supported}\n"
  exit 2
end

# Create needed directories
if !File.directory?("#{dir}/#{config_dir}")
  FileUtils.mkdir_p("#{dir}/#{config_dir}")
end
if !File.directory?("#{dir}/#{certs_dir}")
  FileUtils.mkdir_p("#{dir}/#{certs_dir}")
end

if !File.file?("Vagrantfile")
  print "ERROR: Run the command from the top directory, where 'Vagrantfile' is located!\n"
  exit 2
end

if !File.file?("#{dir}/#{config_dir}/#{config_file}")
  print "ERROR: Please copy a config file from the examples dir to #{dir}/#{config_dir}/#{config_file} to continue\n"
  exit 2
end

# Read YAML file with instance information (box, CPU, RAM, IP addresses)
# Edit the config file to change VM and environment configuration details
settings = YAML.load_file("#{dir}/#{config_dir}/#{config_file}")

splunk_dirs = defaults['splunk_dirs'].dup
if !settings['splunk_dirs'].nil?
  splunk_dirs = splunk_dirs.merge(settings['splunk_dirs'])
end

# Get timezone from the vagrant host as default for the virtual machines
defaults['os']['time_zone'] = `ls -l /etc/localtime | sed -e 's%.*zoneinfo/%%' | tr -d '\n'`

# Create splunk_defaults variables
splunk_defaults = defaults['splunk_defaults'].dup
if !settings['splunk_defaults'].nil?
  splunk_defaults = splunk_defaults.merge(settings['splunk_defaults'])
  web_config = defaults['splunk_defaults']['splunk_ssl']['web']['config'].dup
  # Merging of splunk_ssl.web.config does not work, need to do it separatly
  if not settings['splunk_defaults']['splunk_ssl'].nil? and not settings['splunk_defaults']['splunk_ssl']['web'] and not settings['splunk_defaults']['splunk_ssl']['web']['config'].nil?
    web_config = web_config.merge(settings['splunk_defaults']['splunk_ssl']['web']['config'])
  end
  splunk_defaults['splunk_ssl']['web']['config'] = web_config
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
      print "Comment variable 'splunk_license_file' in #{dir}/#{config_dir}/#{config_file} if no license available\n"
      exit 2
    end
  end
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

# Clean up host_vars directory
if File.directory?("#{dir}/ansible/host_vars")
  FileUtils.rm_r("#{dir}/ansible/host_vars")
end
FileUtils.mkdir_p("#{dir}/ansible/host_vars")

# Create inventory host groups
settings['splunk_hosts'].each do |splunk_host|
  var_obj = defaults.dup
  ['ansible','virtualbox'].each do |config_group|
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
    if !File.directory?("#{dir}/ansible/host_vars/#{splunk_host['name']}")
      FileUtils.mkdir_p("#{dir}/ansible/host_vars/#{splunk_host['name']}")
    end
    File.open("#{dir}/ansible/host_vars/#{splunk_host['name']}/os.yml", "w") do |f|
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
    if !File.directory?("#{dir}/ansible/host_vars/#{splunk_host['name']}")
      FileUtils.mkdir_p("#{dir}/ansible/host_vars/#{splunk_host['name']}")
    end
    File.open("#{dir}/ansible/host_vars/#{splunk_host['name']}/splunk_env.yml", "w") do |f|
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
        # Needs to be defined, because not all hosts are populated to the ansible inventory from the start
        var_obj["vagrant_splunk_"+role_def] = [splunk_host['name']]
        groupname = "splunk_env_"+splunk_host['splunk_env']
        if envs.has_key?(groupname)
          envs[groupname] = envs[groupname].merge(var_obj)
        else
          envs[groupname] = var_obj
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

# Cleanup old group_vars files
Dir['ansible/group_vars/**/*'].select{|f| File.file?(f) }.each do |filepath|
  File.delete(filepath) if File.basename(filepath) != "dynamic.yml"
end

# Create os group_vars
os_defaults = defaults['os'].dup
if !settings['os'].nil?
  os_defaults = os_defaults.merge(settings['os'])
end
File.open("ansible/group_vars/all/os.yml", "w") do |f|
  f.write(os_defaults.to_yaml)
end

# Create splunk_basics group_vars
if !splunk_dirs.nil?
  File.open("ansible/group_vars/all/splunk_dirs.yml", "w") do |f|
    f.write(splunk_dirs.to_yaml)
  end
end

# Create splunk environment group_vars
if !splunk_environments.nil?
  splunk_environments.each do |splunkenv|
    group_name = "splunk_env_"+splunkenv['splunk_env_name']
    if envs.has_key?(group_name)
      splunkenv = splunkenv.merge(envs[group_name])
    end
    File.open("ansible/group_vars/#{group_name}.yml", "w") do |f|
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
    File.open("ansible/group_vars/#{group_name}.yml", "w") do |f|
      f.write(idxcluster.to_yaml)
    end
  end
end

# Create splunk search head cluster group_vars
if !settings['splunk_shclusters'].nil?
  settings['splunk_shclusters'].each do |shcluster|
    group_name = "shcluster_"+shcluster['shc_name']
    shcluster['shc_captain'] = shc_list[shcluster['shc_name']].last
    File.open("ansible/group_vars/#{group_name}.yml", "w") do |f|
      f.write(shcluster.to_yaml)
    end
  end
end

# Create splunk outputs group_vars
if !outputs_groups.nil?
  outputs_groups.each do |group_name, group_content|
    outputs = {}
    outputs['splunk_outputs_list'] = group_content.dup
    File.open("ansible/group_vars/#{group_name}.yml", "w") do |f|
      f.write(outputs.to_yaml)
    end
  end
end

# Create splunk search_peers group_vars
if !search_peer_groups.nil?
  search_peer_groups.each do |group_name, group_content|
    search_peers = {}
    search_peers['splunk_search_peer_list'] = group_content.dup
    File.open("ansible/group_vars/#{group_name}.yml", "w") do |f|
      f.write(search_peers.to_yaml)
    end
  end
end

# If dynamic IPs are used, calculate the start number
if !settings['general']['start_ip'].nil?
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
    if !settings['general']['start_ip'].nil?
      # Keep the ip, if defined
      if splunk_host['ip_addr'].nil?
        splunk_host['ip_addr'] = base_ip+"."+start_num.to_s
      end
    end
    if splunk_host[var]
      var_obj = {}
      var_obj[var] = splunk_host[var]
      per_host_vars=per_host_vars.merge(var_obj)
    end
  end
  host_vars[splunk_host['name']] = per_host_vars
  start_num += 1
  hosts_entry = {}
  hosts_entry['name'] = splunk_host['name']
  hosts_entry['ip_addr'] = splunk_host['ip_addr']
  splunk_host_list.push(hosts_entry)
end

# Write out hosts content to build /etc/hosts file
splunk_hosts = {}
splunk_hosts['splunk_hosts'] = splunk_host_list
File.open("ansible/group_vars/all/hosts.yml", "w") do |f|
  f.write(splunk_hosts.to_yaml)
end

# Create HTML link page for all the roles
require 'erb'
template = File.read("#{dir}/template/index.html.erb")
result = ERB.new(template).result(binding)
File.open("#{dir}/#{config_dir}/index.html", 'w+') do |f|
  f.write result
end

# Create and configure the specified systems
Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  # Loop through YAML file and set per-VM information
  settings['splunk_hosts'].each do |server|
    config.vm.define server['name'] do |srv|
      # Setting hostname
      srv.vm.hostname = server['name']

      # Box image to use
      srv.vm.box = special_host_vars[server['name']]['virtualbox']['box']
      #srv.vm.box = settings['virtualbox']['box']

      # Don't check for box updates
      #srv.vm.box_check_update = false

      # Splunk need some time to shutdown
      srv.vm.boot_timeout = 600
      srv.vm.graceful_halt_timeout = 600

      # Install vbguest additions
      config.vbguest.no_install = true
      if special_host_vars[server['name']]['virtualbox']['install_vbox_additions'] == true
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

      srv.vm.network :private_network, ip: server['ip_addr']
      #srv.vm.network "forwarded_port", guest: 8000, host: 8000, auto_correct: true

# If we need a second disk for testing
#      dataDisk1 = srv.vm.hostname+'dataDisk1.vdi'

      # Set per-server VirtualBox provider configuration/overrides
      srv.vm.provider 'virtualbox' do |vb, override|
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

      # Workaround for missing python in ubuntu/xenial64
      srv.vm.provision "shell", inline: "which python || sudo apt-get -y install python"

      srv.vm.provision "ansible" do |ansible|
        ansible.compatibility_mode = "2.0"
        ansible.groups = groups
        ansible.host_vars = host_vars
        ansible.skip_tags = special_host_vars[server['name']]['ansible']['skip_tags']
        ansible.verbose = special_host_vars[server['name']]['ansible']['verbose']
        ansible.playbook = "ansible/site.yml"
      end
    end
  end
end
