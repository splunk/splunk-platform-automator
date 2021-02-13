from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

###############################################################################
# Copyright 2021 Marco Stadler
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

DOCUMENTATION = r'''
    name: splunkenizer
    plugin_type: inventory
    short_description: Returns Ansible inventory from Splunkenizer config file
    description: Returns Ansible inventory from Splunkenizer config file
    options:
        plugin:
            description: Name of the plugin
            required: true
            choices: ['splunkenizer']
        general:
            description: general settings
            type: dictionary
            required: false
        os:
            description: os settings
            type: dictionary
            required: false
        aws:
            description: aws settings
            type: dictionary
            required: false
        virtualbox:
            description: virtualbox settings
            type: dictionary
            required: false
        splunk_defaults:
            description: splunk_defaults settings
            type: dictionary
            required: false
        splunk_environments:
            description: splunk_environments settings
            type: dictionary
            required: false
        splunk_dirs:
            description: splunk_dirs settings
            type: dictionary
            required: false
        splunk_apps:
            description: splunk_apps settings
            type: dictionary
            required: false
        splunk_systemd:
            description: splunk_systemd settings
            type: dictionary
            required: false
        splunk_idxclusters:
            description: splunk_idxclusters settings
            type: list
            required: false
        splunk_shclusters:
            description: splunk_shclusters settings
            type: list
            required: false
        splunk_hosts:
            description: splunk_hosts settings
            type: list
            required: true
'''

from ansible.plugins.inventory import BaseInventoryPlugin
from ansible.errors import AnsibleError, AnsibleParserError
import yaml
import glob
import os
from pathlib import Path
import collections

class InventoryModule(BaseInventoryPlugin):
    NAME = 'splunkenizer'

    def verify_file(self, path):
        '''Return true/false if this is possibly a valid file for this plugin to consume'''
        valid = False
        if super(InventoryModule, self).verify_file(path):
            # base class verifies that file exists and is readable by current user
            if path.endswith(('splunk_config.yml',
                              'splunkenizer_inventory.yml',
                              'splunkenizer_inventory.yaml')):
                valid = True
        return valid

    def _merge_dict(self, dict1, dict2, add_new=True):
        '''Recursively merge two directories and return the merged one
        Also add new keys, if any and add_new=True'''
        merged_dict = dict1.copy()
        if not add_new:
            dict2 = {
                key: dict2[key]
                for key in set(merged_dict).intersection(set(dict2))
            }

        for key, value in dict2.items():
            if isinstance(merged_dict.get(key), dict) and isinstance(value, collections.Mapping):
                merged_dict[key] = self._merge_dict(merged_dict[key], value, add_new=add_new)
            else:
                merged_dict[key] = value

        return merged_dict

    def _populate_defaults(self):
        '''Read all the default values'''
        defaults = {}
        for file in glob.glob("defaults/*.yml"):
            with open(file,"r") as configfile:
              file_content = yaml.load(configfile, Loader=yaml.FullLoader)
            stanza=Path(file).resolve().stem
            defaults[stanza] = file_content[stanza]
        setattr(self, 'defaults', defaults)

    def _populate_groupvars(self, vardict, groupname):
        '''adds all the variables from a dictionary to the given group'''
        #print("Groupname: %s, Dict: %s" % (groupname, vardict))
        if groupname != "all":
            self.inventory.add_group(groupname)
        for var in vardict:
            #print("Adding var: ", var)
            self.inventory.set_variable(groupname, var, vardict[var])

    def _populate(self):
        '''Populates the inventory with the hosts and groups and all the settings'''
        # Deal with the settings for the all group
        setattr(self, 'groups', {'all': {}})
        for section in ['os', 'splunk_dirs', 'splunk_apps', 'splunk_systemd', 'splunk_defaults']:
            #print("Defaults[%s]: " % section, self.defaults[section])
            if isinstance(self.configfiles.get(section), dict):
                #print("Configfile[%s]: " % section, self.configfiles[section])
                merged_section=self._merge_dict(self.defaults[section],self.configfiles[section])
                #print("Merged: ", merged)
            else:
                merged_section = self.defaults[section]
            #print("merged_section: ", merged_section)
            #TODO: maybe self.groups is not needed, can do populate directly
            self.groups['all'].update(merged_section)
        self._populate_groupvars(self.groups['all'], 'all')

        # Deal with the environments specific settings
        setattr(self, 'environments', {})
        setattr(self, 'clusters', {'idxcluster':[],'shcluster':[]})
        if isinstance(self.configfiles.get('splunk_environments'), list):
            for splunk_env in self.configfiles.get('splunk_environments'):
                try:
                    groupname = "splunk_env_" + splunk_env['splunk_env_name']
                    self._populate_groupvars(splunk_env, groupname)
                    self.environments[splunk_env['splunk_env_name']] = {}
                except Exception as e:
                    raise AnsibleParserError('Cannot populate settings for environment. Variable {} not found'.format(e))
        else:
            # Otherwise create the default splunk_env group
            try:
                default_splunk_env = "splunk_env_" + self.groups['all']['splunk_env_name']
                self.inventory.add_group(default_splunk_env)
                self.environments[self.groups['all']['splunk_env_name']] = {}
            except Exception as e:
                raise AnsibleParserError('Error: {}'.format(e))

        #TODO: Treat those sections individually: general, virtualbox, aws
        # Read in Indexer Cluster config
        if isinstance(self.configfiles.get('splunk_idxclusters'), list):
            for idxcluster in self.configfiles.get('splunk_idxclusters'):
                try:
                    groupname = "idxcluster_" + idxcluster['idxc_name']
                    #TODO: Add variable checks
                    self._populate_groupvars(idxcluster, groupname)
                    self.clusters['idxcluster'].append(idxcluster['idxc_name'])
                except Exception as e:
                    raise AnsibleParserError('Cannot populate settings for idxcluster. Error: {}'.format(e))
        
        # Read in Search Head Cluster config
        if isinstance(self.configfiles.get('splunk_shclusters'), list):
            for shcluster in self.configfiles.get('splunk_shclusters'):
                try:
                    groupname = "shcluster_" + shcluster['shc_name']
                    #TODO: Add variable checks
                    self._populate_groupvars(shcluster, groupname)
                    self.clusters['shcluster'].append(shcluster['shc_name'])
                except Exception as e:
                    raise AnsibleParserError('Cannot populate settings for shcluster. Error: {}'.format(e))

        #TODO: Verify volume definitions in splunk_indexer_volumes. If other names in homePath coldPath are used. Remove primary from the settings
        #TODO: set ansible_host: self.inventory.set_variable(hostname, 'ansible_host', data['Mgmt IP'])
        
        # Defining allowed settings
        allowed_roles = ['cluster_master','deployer','deployment_server','heavy_forwarder','indexer','license_master','monitoring_console','search_head','universal_forwarder','universal_forwarder_windows']
        allowed_hostvars = ['splunk_version','splunk_admin_password','splunk_license_file','splunk_indexes','splunk_outputs','splunk_search_peers','splunk_conf','os','aws','virtualbox']
        allowed_roles_with_site = ['indexer','search_head','cluster_master']

        # Creating some data structure for collecting information later on
        for environment in self.environments:
            for topic in ['output','search_peer']:   
                self.environments[environment][topic] = {}
        setattr(self, 'indexer_clusters', {})
        setattr(self, 'search_head_clusters', {})
        roles = {}
        for role in allowed_roles:
            roles[role] = []

        # Going through the hosts and parse the settings
        for splunkhost in self.configfiles['splunk_hosts']:
            hostname = splunkhost['name']
            #print("Working on host: ", splunkhost['name'])
            #print("Splunkhost: ", splunkhost)
            self.inventory.add_host(host=splunkhost['name'])

            # Add host to splunk_env
            try:
                if 'splunk_env' in splunkhost and splunkhost['splunk_env'] != self.groups['all']['splunk_env_name']:
                    splunk_env =  splunkhost['splunk_env']
                else:
                    splunk_env = self.groups['all']['splunk_env_name']
                self.inventory.add_host(host=hostname, group="splunk_env_" + splunk_env)
            except Exception as e:
                raise AnsibleParserError("Cannot add host %s to splunk_env %s. Error: %s" % (hostname, splunkhost['splunk_env'], e))   

            # This is currently hardcoded to all. I may add selection settings in the future.
            splunk_outputs = self.groups['all']['splunk_outputs']
            if splunk_outputs not in self.environments[splunk_env]['output']:
                self.environments[splunk_env]['output'][splunk_outputs] = {'targets':{}, 'hosts':[]}

            splunk_search_peers = self.groups['all']['splunk_search_peers']
            if splunk_search_peers not in self.environments[splunk_env]['search_peer']:
                self.environments[splunk_env]['search_peer'][splunk_search_peers] = {'targets':{}, 'hosts':[]}

            site_role_check = False
            site_role_check_passed = False
            if 'site' in splunkhost:
                #TODO: Check site syntax
                site_role_check = True

            # Work through the given roles
            if isinstance(splunkhost.get('roles'), list):

                for role in splunkhost['roles']:
                    #print("Role: ", role)
                    if role in allowed_roles:
                        #print("Role ok")

                        if site_role_check and role in allowed_roles_with_site:
                            site_role_check_passed = True

                        if role == "license_master":
                            #TODO: Check for license file, if role is license_master
                            pass
                        if role == "cluster_master" and 'idxcluster' not in splunkhost:
                            raise AnsibleParserError("Error: idxcluster variable not set for host %s with role %s." % (hostname, role))
                        
                        # Build the indexer_cluster lists with their sites
                        if role in ['indexer','cluster_master'] and 'idxcluster' in splunkhost:
                            #print("Building indexer_cluster lists")
                            
                            if splunkhost['idxcluster'] not in self.indexer_clusters:
                                self.indexer_clusters[splunkhost['idxcluster']] = {'hosts': []}
                                #TODO: Group creation must be moved to cluster section handling
                                #self.inventory.add_group("idxcluster_" + splunkhost['idxcluster'])
                            
                            if role == 'indexer':
                                self.indexer_clusters[splunkhost['idxcluster']]['hosts'].append(hostname)

                                if 'site' in splunkhost:
                                    if 'sites' not in self.indexer_clusters[splunkhost['idxcluster']]:
                                        self.indexer_clusters[splunkhost['idxcluster']].update({'sites': []})
                                    if splunkhost['site'] not in self.indexer_clusters[splunkhost['idxcluster']]['sites']:
                                        self.indexer_clusters[splunkhost['idxcluster']]['sites'].append(splunkhost['site'])
                                        self.inventory.add_group("idxcluster_" + splunkhost['idxcluster'] + "_" + splunkhost['site'])
                                    self.inventory.add_host(host=hostname, group="idxcluster_" + splunkhost['idxcluster'] + "_" + splunkhost['site'])

                            self.inventory.add_host(host=hostname, group="idxcluster_" + splunkhost['idxcluster'])
                        
                        # Build the outputs list (all the hosts getting an outputs.conf)
                        if role in ['indexer','heavy_forwarder']:
                            #print("Building outputs list")
                            if role =='indexer' and 'idxcluster' in splunkhost:
                                if 'idxcluster' not in self.environments[splunk_env]['output'][splunk_outputs]['targets']:
                                    self.environments[splunk_env]['output'][splunk_outputs]['targets']['idxcluster'] = {}
                                if splunkhost['idxcluster'] not in self.environments[splunk_env]['output'][splunk_outputs]['targets']['idxcluster']:
                                    self.environments[splunk_env]['output'][splunk_outputs]['targets']['idxcluster'][splunkhost['idxcluster']] = []
                                self.environments[splunk_env]['output'][splunk_outputs]['targets']['idxcluster'][splunkhost['idxcluster']].append(hostname)
                            else:
                                if role not in self.environments[splunk_env]['output'][splunk_outputs]['targets']:
                                    self.environments[splunk_env]['output'][splunk_outputs]['targets'][role] = []
                                self.environments[splunk_env]['output'][splunk_outputs]['targets'][role].append(hostname)

                        if role != 'indexer':
                            if hostname not in self.environments[splunk_env]['output'][splunk_outputs]['hosts']:
                                self.environments[splunk_env]['output'][splunk_outputs]['hosts'].append(hostname)

                        # Build the search_peer list (host where to search on)
                        if role in ['indexer','cluster_master']:
                            if role == 'cluster_master' and 'idxcluster' in splunkhost:
                                if 'idxcluster' not in self.environments[splunk_env]['search_peer'][splunk_search_peers]['targets']:
                                    self.environments[splunk_env]['search_peer'][splunk_search_peers]['targets']['idxcluster'] = {splunkhost['idxcluster']: hostname}
                                #self.environments[splunk_env]['search_peer'][splunk_search_peers]['targets']['idxcluster'][splunkhost['idxcluster']].append(hostname)
                            elif role == 'indexer' and 'idxcluster' not in splunkhost:
                                if role not in self.environments[splunk_env]['search_peer'][splunk_search_peers]['targets']:
                                    self.environments[splunk_env]['search_peer'][splunk_search_peers]['targets'] = {role: []}
                                self.environments[splunk_env]['search_peer'][splunk_search_peers]['targets'][role].append(hostname)

                        if role in ['search_head','cluster_master']:
                            if hostname not in self.environments[splunk_env]['search_peer'][splunk_search_peers]['hosts']:
                                self.environments[splunk_env]['search_peer'][splunk_search_peers]['hosts'].append(hostname)

                        # Build the search_head_clusters lists with their sites
                        if role in ['search_head','deployer'] and 'shcluster' in splunkhost:
                            if splunkhost['shcluster'] not in self.search_head_clusters:
                                self.search_head_clusters[splunkhost['shcluster']] = {'hosts': []}
                                #TODO: Group creation must be moved to cluster section handling
                                self.inventory.add_group("shcluster_" + splunkhost['shcluster'])

                            if role == 'search_head':
                                self.search_head_clusters[splunkhost['shcluster']]['hosts'].append(hostname)

                                if 'site' in splunkhost:
                                    if 'sites' not in self.search_head_clusters[splunkhost['shcluster']]:
                                        self.search_head_clusters[splunkhost['shcluster']].update({'sites': []})
                                    if splunkhost['site'] not in self.search_head_clusters[splunkhost['shcluster']]['sites']:
                                        self.search_head_clusters[splunkhost['shcluster']]['sites'].append(splunkhost['site'])
                                        self.inventory.add_group("shcluster_" + splunkhost['shcluster'] + "_" + splunkhost['site'])
                                    self.inventory.add_host(host=hostname, group="shcluster_" + splunkhost['shcluster'] + "_" + splunkhost['site'])

                            self.inventory.add_host(host=hostname, group="shcluster_" + splunkhost['shcluster'])

                        # Add host to the roles list from where is will be added to
                        roles[role].append(splunkhost['name'])
                    else:
                        raise AnsibleParserError("Unsupported role %s found for host %s. Supported roles are: (%s)" % (role, splunkhost['name'], ','.join(allowed_roles)))

            # Set site, if available and role check passed
            if site_role_check is True:
                if site_role_check_passed is True:
                    self.inventory.set_variable(hostname, 'site', splunkhost['site'])
                else:
                    raise AnsibleParserError("Error: site variable not allowed for host %s. Only roles %s can have a site." % (hostname, ','.join(allowed_roles_with_site)))
              

            # Add the rest of the host variables
            for key, val in splunkhost.items():
                if key in ['name','splunk_env_name','roles','aws','virtualbox']:
                    # Ignore those ones. Either not relevant or already worked on
                    continue
                if key in ['idxcluster','shcluster']:
                    #TODO: Handle special vars
                    continue
                if key in ['ip_addr', 'site', 'cname']:
                    #TODO: Handle special vars (site is done already)
                    continue
                #print("Addind key: %s with values %s" % (key, val))
                if key in allowed_hostvars:
                    # Extract section variables to add them directly
                    #TODO: Check how to deal with splunk_conf host vars
                    if key in ['os']:
                        for section_key, section_val in splunkhost.get(key).items():
                            #print("Addind key: %s with values %s" % (section_key, section_val))
                            self.inventory.set_variable(hostname, section_key, section_val)
                    else:
                        self.inventory.set_variable(hostname, key, val)
                else:
                    raise AnsibleParserError("Unsupported host_var %s found for host %s. Supported vars are: (%s)" % (key, hostname, ','.join(allowed_hostvars)))
    
        # Add hosts to role_ ansible groups
        for role in allowed_roles:
            if len(roles[role]) > 0:
                groupname = "role_" + role
                self.inventory.add_group(groupname)
                for hostname in roles[role]:
                    self.inventory.add_host(host=hostname, group=groupname)

        # Create output and search_peer groups
        for splunk_env, env_values in self.environments.items():
            for type, type_values in env_values.items():
                for group, group_values in type_values.items():
                    groupname = type + "_" + splunk_env + "_" + group
                    vars = {}
                    vars['splunk_'+type+'_list'] = group_values['targets']
                    self._populate_groupvars(vars, groupname)
                    for host in group_values['hosts']:
                        self.inventory.add_host(host=host, group=groupname)

        # Add available_sites to the indexer clusters
        for idxcluster, cluster_values in self.indexer_clusters.items():
            try:
                groupname = "idxcluster_" + idxcluster
                self.inventory.set_variable(groupname, 'idxc_available_sites', cluster_values['sites'])
            except Exception as e:
                raise AnsibleParserError('Cannot add stes to idxcluster. Error: {}'.format(e))

    def parse(self, inventory, loader, path, cache):
        '''Return dynamic inventory from source '''
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        # Read the inventory YAML file
        self._read_config_data(path)
        try:
            configfiles = {}
            # Store the required sections from the YAML file
            for section in ['plugin', 'splunk_hosts']:
                configfiles[section] = self.get_option(section)
            # Store the optional sections from the YAML file
            for section in ['general', 'os', 'splunk_dirs', 'splunk_defaults', 'splunk_environments', 'splunk_apps', 'splunk_systemd', 'splunk_idxclusters', 'splunk_shclusters', 'virtualbox', 'aws']:
                configfiles[section] = self.get_option(section)
            setattr(self, 'configfiles', configfiles)
        except Exception as e:
            raise AnsibleParserError('All correct options required: {}'.format(e))
        # Call our internal helper to read in default values
        self._populate_defaults()
        # Call our internal helper to populate the dynamic inventory from the config file
        self._populate()