# Removed Biased Language

With Splunk 9.x some configuration terms have been renamed and are considered deprecated. The Base Config Apps habe been changed and need to be updated and some apps have been renamed. Please download the latest version. The Splunk Platform Automator Framework does taking care of this automatically when Splunk version 9.x or higher is installed. Existing installation are working as is but the settings should be changed manually in the apps.

Those settings have been changed:

- server.conf[clustering]
  - mode = `manager` or `peer`
  - master_uri -> manager_uri
- server.conf[clustermaster:&lt;name&gt;] -> [clustermanager:&lt;name&gt;]
- server.conf[license]
  - master_uri -> manager_uri
- outputs.conf[indexer_discovery:&lt;name&gt;]
  - master_uri -> manager_uri

Due to this some roles have been renamed in the config file. Please update your exsiting configs:

- cluster_master -> cluster_manager
- license_master -> license_manager
