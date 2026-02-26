"""
Unit tests for Splunk Platform Automator configuration schema validation.

Tests the Pydantic schema models defined in ansible/plugins/inventory/schema.py.
"""

import pytest
import sys
import os

# Add the inventory plugin directory to the path so we can import the schema
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ansible', 'plugins', 'inventory'))

from schema import (
    SplunkConfig,
    SplunkHost,
    AllowedRole,
    validate_config,
    ConfigValidationError,
    GeneralConfig,
    IdxClusterConfig,
    ShClusterConfig,
)


class TestValidConfigurations:
    """Test valid configuration scenarios."""

    def test_minimal_valid_config(self):
        """Test minimal valid configuration with just required fields."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "roles": ["indexer"]}
            ]
        }
        result = validate_config(config)
        assert result.plugin == "splunk-platform-automator"
        assert len(result.splunk_hosts) == 1
        assert result.splunk_hosts[0].name == "idx1"

    def test_host_with_list(self):
        """Test host definition using list syntax."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"list": ["idx1", "idx2", "idx3"], "roles": ["indexer"]}
            ]
        }
        result = validate_config(config)
        assert result.splunk_hosts[0].list == ["idx1", "idx2", "idx3"]

    def test_host_with_iter(self):
        """Test host definition using iter syntax."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {
                    "iter": {"prefix": "idx", "numbers": "1..5"},
                    "roles": ["indexer"]
                }
            ]
        }
        result = validate_config(config)
        assert result.splunk_hosts[0].iter.prefix == "idx"
        assert result.splunk_hosts[0].iter.numbers == "1..5"

    def test_all_roles_valid(self):
        """Test that all allowed roles are accepted."""
        all_roles = [
            "cluster_manager", "deployer", "deployment_server",
            "heavy_forwarder", "indexer", "license_manager",
            "monitoring_console", "search_head", "universal_forwarder",
            "universal_forwarder_windows"
        ]
        hosts = []
        for i, role in enumerate(all_roles):
            # Use iter for search_head to create 3 hosts (SHC minimum when deployer exists)
            if role == "search_head":
                host = {"iter": {"numbers": "1..3"}, "roles": [role], "shcluster": "shc1"}
            # Use iter for indexer to create 2 hosts (IDXC minimum when cluster_manager exists)
            elif role == "indexer":
                host = {"iter": {"numbers": "1..2"}, "roles": [role], "idxcluster": "idxc1"}
            else:
                host = {"name": f"host_{i}", "roles": [role]}
            # cluster_manager requires idxcluster
            if role == "cluster_manager":
                host["idxcluster"] = "idxc1"
            # deployer requires shcluster
            if role == "deployer":
                host["shcluster"] = "shc1"
            hosts.append(host)
        
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_defaults": {"splunk_license_file": "Splunk.License"},
            "splunk_hosts": hosts,
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_idxclusters": [{"idxc_name": "idxc1", "idxc_password": "secret"}]
        }
        result = validate_config(config)
        assert len(result.splunk_hosts) == len(all_roles)

    def test_site_with_indexer(self):
        """Test that site is allowed with indexer role."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "roles": ["indexer"], "site": "site1"}
            ]
        }
        result = validate_config(config)
        assert result.splunk_hosts[0].site == "site1"

    def test_site_with_search_head(self):
        """Test that site is allowed with search_head role."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"], "site": "site1"}
            ]
        }
        result = validate_config(config)
        assert result.splunk_hosts[0].site == "site1"

    def test_site_with_cluster_manager(self):
        """Test that site is allowed with cluster_manager role."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {
                    "name": "cm1",
                    "roles": ["cluster_manager"],
                    "site": "site0",
                    "idxcluster": "idxc1"
                },
                {"iter": {"numbers": "1..2"}, "roles": ["indexer"], "idxcluster": "idxc1"}
            ],
            "splunk_idxclusters": [{"idxc_name": "idxc1", "idxc_password": "secret"}]
        }
        result = validate_config(config)
        assert result.splunk_hosts[0].site == "site0"

    def test_cluster_manager_with_idxcluster(self):
        """Test that cluster_manager with idxcluster is valid."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {
                    "name": "cm",
                    "roles": ["cluster_manager"],
                    "idxcluster": "idxc1"
                },
                {"iter": {"numbers": "1..2"}, "roles": ["indexer"], "idxcluster": "idxc1"}
            ],
            "splunk_idxclusters": [{"idxc_name": "idxc1", "idxc_password": "secret"}]
        }
        result = validate_config(config)
        assert result.splunk_hosts[0].idxcluster == "idxc1"

    def test_full_config_with_all_sections(self):
        """Test configuration with all optional sections."""
        config = {
            "plugin": "splunk-platform-automator",
            "general": {"url_locale": "en-GB"},
            "os": {"set_hostname": True, "packages": ["vim", "wget"]},
            "terraform": {
                "aws": {
                    "region": "eu-central-1",
                    "instance_type": "t3.large"
                }
            },
            "splunk_defaults": {
                "splunk_version": "9.1.0",
                "splunk_admin_password": "changeme"
            },
            "splunk_idxclusters": [
                {"idxc_name": "idxc1", "idxc_password": "secret"}
            ],
            "splunk_shclusters": [
                {"shc_name": "shc1", "shc_password": "secret"}
            ],
            "splunk_hosts": [
                {"name": "idx1", "roles": ["indexer"]}
            ]
        }
        result = validate_config(config)
        assert result.general.url_locale == "en-GB"
        assert result.splunk_defaults.splunk_version == "9.1.0"

    def test_url_locale_with_underscore(self):
        """Test url_locale accepts underscore separator."""
        config = {
            "plugin": "splunk-platform-automator",
            "general": {"url_locale": "en_US"},
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}]
        }
        result = validate_config(config)
        assert result.general.url_locale == "en_US"


class TestInvalidConfigurations:
    """Test invalid configuration scenarios that should raise errors."""

    def test_missing_plugin(self):
        """Test that missing plugin field raises error."""
        config = {
            "splunk_hosts": [{"name": "idx1", "roles": ["indexer"]}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "plugin" in str(exc_info.value).lower()

    def test_wrong_plugin_name(self):
        """Test that wrong plugin name raises error."""
        config = {
            "plugin": "wrong-plugin",
            "splunk_hosts": [{"name": "idx1", "roles": ["indexer"]}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "plugin" in str(exc_info.value).lower()

    def test_missing_splunk_hosts(self):
        """Test that missing splunk_hosts raises error."""
        config = {
            "plugin": "splunk-platform-automator"
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "splunk_hosts" in str(exc_info.value).lower()

    def test_empty_splunk_hosts(self):
        """Test that empty splunk_hosts list raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": []
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "splunk_hosts" in str(exc_info.value).lower()

    def test_invalid_role(self):
        """Test that invalid role name raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "roles": ["invalid_role"]}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "roles" in str(exc_info.value).lower() or "invalid_role" in str(exc_info.value).lower()

    def test_missing_roles(self):
        """Test that host without roles raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1"}  # Missing roles
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "roles" in str(exc_info.value).lower()

    def test_empty_roles(self):
        """Test that empty roles list raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "roles": []}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "roles" in str(exc_info.value).lower()

    def test_host_with_no_identifier(self):
        """Test that host without name/list/iter raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"roles": ["indexer"]}  # Missing name, list, or iter
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "name" in str(exc_info.value).lower() or "list" in str(exc_info.value).lower() or "iter" in str(exc_info.value).lower()

    def test_host_with_multiple_identifiers(self):
        """Test that host with both name and list raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "list": ["idx2", "idx3"], "roles": ["indexer"]}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "name" in str(exc_info.value).lower() or "list" in str(exc_info.value).lower() or "multiple" in str(exc_info.value).lower()

    def test_site_on_disallowed_role(self):
        """Test that site on deployer role raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "ds1", "roles": ["deployer"], "shcluster": "shc1", "site": "site1"}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "site" in str(exc_info.value).lower()

    def test_site_on_universal_forwarder(self):
        """Test that site on universal_forwarder role raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "uf1", "roles": ["universal_forwarder"], "site": "site1"}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "site" in str(exc_info.value).lower()

    def test_cluster_manager_without_idxcluster(self):
        """Test that cluster_manager without idxcluster raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "cm", "roles": ["cluster_manager"]}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "idxcluster" in str(exc_info.value).lower()

    def test_deployer_without_shcluster(self):
        """Test that deployer without shcluster raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"]}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "shcluster" in str(exc_info.value).lower()

    def test_invalid_url_locale_format(self):
        """Test that invalid url_locale format raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "general": {"url_locale": "english"},
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "url_locale" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    def test_invalid_key_in_general(self):
        """Test that unknown key in general section raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "general": {"unknown_key": "value"},
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "unknown_key" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()

    def test_invalid_iter_numbers_format(self):
        """Test that invalid iter numbers format raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {
                    "iter": {"prefix": "idx", "numbers": "1-5"},  # Should be 1..5
                    "roles": ["indexer"]
                }
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "numbers" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    def test_negative_memory(self):
        """Test that negative memory value raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "virtualbox": {"memory": -512},
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "memory" in str(exc_info.value).lower()


class TestClusterConfigurations:
    """Test indexer and search head cluster configurations."""

    def test_valid_idxcluster_config(self):
        """Test valid indexer cluster configuration."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_idxclusters": [
                {
                    "idxc_name": "idxc1",
                    "idxc_password": "secret",
                    "idxc_replication_port": 9887
                }
            ],
            "splunk_hosts": [
                {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc1"},
                {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"},
                {"name": "idx2", "roles": ["indexer"], "idxcluster": "idxc1"}
            ]
        }
        result = validate_config(config)
        assert len(result.splunk_idxclusters) == 1
        assert result.splunk_idxclusters[0].idxc_name == "idxc1"

    def test_valid_shcluster_config(self):
        """Test valid search head cluster configuration."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_shclusters": [
                {
                    "shc_name": "shc1",
                    "shc_password": "secret",
                    "shc_replication_port": 9887
                }
            ],
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"}
            ]
        }
        result = validate_config(config)
        assert len(result.splunk_shclusters) == 1
        assert result.splunk_shclusters[0].shc_name == "shc1"

    def test_invalid_replication_port(self):
        """Test that invalid port number raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_idxclusters": [
                {"idxc_name": "idxc1", "idxc_replication_port": 70000}  # > 65535
            ],
            "splunk_hosts": [
                {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc1"}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "port" in str(exc_info.value).lower() or "65535" in str(exc_info.value)

    def test_cluster_manager_requires_idxcluster_on_indexers(self):
        """Test that at least 2 indexers must have idxcluster when cluster_manager exists."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc1"},
                {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"},
                # Only 1 IDXC member - not enough
            ],
            "splunk_idxclusters": [{"idxc_name": "idxc1", "idxc_password": "secret"}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "2" in str(exc_info.value) and "idxcluster" in str(exc_info.value).lower()

    def test_idxc_members_require_cluster_manager_raises(self):
        """Indexers with idxcluster set require a cluster_manager role."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"},
                {"name": "idx2", "roles": ["indexer"], "idxcluster": "idxc1"},
            ],
            "splunk_idxclusters": [{"idxc_name": "idxc1", "idxc_password": "secret"}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "cluster_manager" in msg and "idxcluster" in msg

    def test_host_idxcluster_requires_splunk_idxclusters_section_raises(self):
        """If any host has idxcluster set, splunk_idxclusters must define that cluster."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc1"},
                {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"},
                {"name": "idx2", "roles": ["indexer"], "idxcluster": "idxc1"}
            ]
            # No splunk_idxclusters
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "splunk_idxclusters" in msg

    def test_host_idxcluster_name_must_match_splunk_idxclusters_raises(self):
        """Host idxcluster value must appear in splunk_idxclusters."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "cm", "roles": ["cluster_manager"], "idxcluster": "idxc_other"},
                {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc_other"},
                {"name": "idx2", "roles": ["indexer"], "idxcluster": "idxc_other"}
            ],
            "splunk_idxclusters": [{"idxc_name": "idxc1", "idxc_password": "secret"}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "splunk_idxclusters" in msg and "idxc_other" in str(exc_info.value)

    def test_deployer_requires_minimum_search_heads(self):
        """Test that deployer with fewer than 3 search heads raises error."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"name": "sh1", "roles": ["search_head"]}
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "3 search heads" in str(exc_info.value)

    def test_deployer_requires_shcluster_on_search_heads(self):
        """Test that at least 3 search heads must have shcluster when deployer exists."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"name": "sh1", "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "sh2", "roles": ["search_head"], "shcluster": "shc1"},
                # Only 2 SHC members - not enough
            ]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        # Either validator may trigger - both require at least 3
        assert "3" in str(exc_info.value)

    def test_shc_members_require_deployer_raises(self):
        """Search heads with shcluster set require a deployer role."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "sh2", "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "sh3", "roles": ["search_head"], "shcluster": "shc1"},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "deployer" in msg and "shcluster" in msg

    def test_host_shcluster_requires_splunk_shclusters_section_raises(self):
        """If any host has shcluster set, splunk_shclusters must define that cluster."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"}
            ]
            # No splunk_shclusters - or name mismatch
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "splunk_shclusters" in msg

    def test_host_shcluster_name_must_match_splunk_shclusters_raises(self):
        """Host shcluster value must appear in splunk_shclusters."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc_other"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc_other"}
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}]
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "splunk_shclusters" in msg and "shc_other" in str(exc_info.value)

    def test_license_manager_requires_license_file(self):
        """Test that license_manager role requires splunk_license_file."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "lm", "roles": ["license_manager"]}
            ]
            # No splunk_defaults with splunk_license_file
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "splunk_license_file" in str(exc_info.value)


class TestMultiRoleHosts:
    """Test hosts with multiple roles."""

    def test_host_with_multiple_roles(self):
        """Test host with indexer and search_head roles."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "shidx", "roles": ["indexer", "search_head"]}
            ]
        }
        result = validate_config(config)
        assert AllowedRole.indexer in result.splunk_hosts[0].roles
        assert AllowedRole.search_head in result.splunk_hosts[0].roles

    def test_deployment_server_and_deployer(self):
        """Test deployment_server and deployer on same host."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "ds", "roles": ["deployment_server", "deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"}
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}]
        }
        result = validate_config(config)
        assert len(result.splunk_hosts[0].roles) == 2


class TestAppDeploymentConfig:
    """Schema validation for splunk_app_deployment section."""

    def test_valid_splunk_app_deployment_with_apps(self):
        """Valid splunk_app_deployment with apps list is accepted."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "Splunk_TA_nix", "source": "splunkbase", "app_id": "352", "target_roles": ["search_head", "indexer"]}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment is not None
        assert len(result.splunk_app_deployment.apps) == 1
        assert result.splunk_app_deployment.apps[0]["name"] == "Splunk_TA_nix"

    def test_splunk_app_deployment_optional(self):
        """Config without splunk_app_deployment is valid."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
        }
        result = validate_config(config)
        assert result.splunk_app_deployment is None

    def test_splunk_app_deployment_empty_apps(self):
        """splunk_app_deployment with empty apps list is valid."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {"apps": []},
        }
        result = validate_config(config)
        assert result.splunk_app_deployment is not None
        assert result.splunk_app_deployment.apps == []

    # --- premium_app ---
    def test_premium_app_itsi_valid_without_target_roles(self):
        """Premium app (premium_app: itsi) without target_roles is valid."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "Splunk IT Service Intelligence", "source": "splunkbase", "app_id": 1841, "version": "4.21.1", "premium_app": "itsi"}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0].get("premium_app") == "itsi"
        assert "target_roles" not in result.splunk_app_deployment.apps[0] or result.splunk_app_deployment.apps[0].get("target_roles") is None

    def test_premium_app_with_target_roles_raises(self):
        """premium_app set with target_roles must raise (target_roles not allowed on premium apps)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "target_roles": ["search_head"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "target_roles" in msg and "premium_app" in msg

    def test_premium_app_invalid_value_raises(self):
        """premium_app must be one of allowed values (e.g. itsi)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [{"name": "App", "source": "splunkbase", "app_id": 123, "premium_app": "other"}]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "premium_app" in str(exc_info.value).lower()

    # --- state ---
    def test_app_state_installed_absent_valid(self):
        """state: installed and state: absent are valid."""
        for state in ("installed", "absent"):
            config = {
                "plugin": "splunk-platform-automator",
                "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
                "splunk_app_deployment": {
                    "apps": [{"name": "MyApp", "source": "local", "state": state}]
                },
            }
            result = validate_config(config)
            assert result.splunk_app_deployment.apps[0].get("state") == state

    def test_app_state_invalid_raises(self):
        """state must be installed or absent."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [{"name": "MyApp", "state": "remove"}]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "state" in str(exc_info.value).lower()

    # --- version ---
    def test_app_version_latest_and_number_valid(self):
        """version: latest and dotted version number are valid."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "A", "source": "splunkbase", "app_id": 1, "version": "latest"},
                    {"name": "B", "source": "splunkbase", "app_id": 2, "version": "4.21.1"},
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0]["version"] == "latest"
        assert result.splunk_app_deployment.apps[1]["version"] == "4.21.1"

    def test_app_version_invalid_raises(self):
        """version must be latest or a version number."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [{"name": "MyApp", "source": "splunkbase", "app_id": 352, "version": "dev"}]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "version" in str(exc_info.value).lower()

    # --- app_id (splunkbase) ---
    def test_splunkbase_app_without_app_id_raises(self):
        """When source is splunkbase, app_id is required."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [{"name": "MyApp", "source": "splunkbase", "target_roles": ["indexer"]}]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "app_id" in str(exc_info.value).lower()

    def test_splunkbase_app_id_must_be_number_raises(self):
        """When source is splunkbase, app_id must be a number."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [{"name": "MyApp", "source": "splunkbase", "app_id": "not-a-number"}]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "app_id" in str(exc_info.value).lower()

    # --- customizations ---
    def test_customizations_valid_structure(self):
        """Valid customizations (remove, local_configs, run_playbook, extra_vars) accepted."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {
                        "name": "Splunk_TA_nix",
                        "source": "splunkbase",
                        "app_id": 833,
                        "target_roles": ["search_head"],
                        "customizations": {
                            "remove": ["default/indexes.conf"],
                            "local_configs": {"inputs.conf": {"tcp://5514": {"disabled": 0}}},
                            "run_playbook": "ansible/apps_playbooks/foo.yml",
                            "extra_vars": {"key": "value"},
                        },
                    }
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0]["customizations"]["remove"] == ["default/indexes.conf"]

    def test_customizations_not_dict_raises(self):
        """customizations must be a dict."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [{"name": "MyApp", "source": "local", "customizations": ["remove"]}]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "customizations" in str(exc_info.value).lower()

    def test_customizations_run_playbook_and_run_role_both_raises(self):
        """Only one of run_playbook or run_role per entry."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {
                        "name": "MyApp",
                        "customizations": {"run_playbook": "ansible/foo.yml", "run_role": "my.role"},
                    }
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "run_playbook" in msg and "run_role" in msg

    # --- splunk_app_deployment direct vars ---
    def test_splunk_app_deployment_direct_vars_valid(self):
        """Top-level target_download, temp_dir, download_timeout etc. validated when present."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "target_download": False,
                "cache_downloads": True,
                "temp_dir": "/tmp/splunk_apps",
                "download_timeout": 120,
                "retry_count": 3,
                "apps": [{"name": "MyApp", "source": "local"}],
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment is not None

    def test_splunk_app_deployment_target_download_not_bool_raises(self):
        """target_download must be boolean when present."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "target_download": "yes",
                "apps": [{"name": "MyApp", "source": "local"}],
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "target_download" in str(exc_info.value).lower()

    def test_splunk_app_deployment_temp_dir_empty_raises(self):
        """temp_dir must be non-empty string when present."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "temp_dir": "   ",
                "apps": [{"name": "MyApp", "source": "local"}],
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "temp_dir" in str(exc_info.value).lower()

    def test_splunk_app_deployment_download_timeout_positive_raises(self):
        """download_timeout must be positive integer when present."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "h1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "download_timeout": 0,
                "apps": [{"name": "MyApp", "source": "local"}],
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "download_timeout" in str(exc_info.value).lower()

    # --- Duplicate app (same name + same deployment target key) ---
    def test_duplicate_app_same_name_same_target_roles_raises(self):
        """Two apps with same name and same target_roles must raise (duplicate deployment target)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "ds", "roles": ["deployment_server"]}, {"name": "sh1", "roles": ["search_head"]}, {"name": "idx1", "roles": ["indexer"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "Splunk_TA_nix", "source": "splunkbase", "app_id": 833, "version": "latest", "target_roles": ["search_head", "indexer"]},
                    {"name": "Splunk_TA_nix", "source": "splunkbase", "app_id": 833, "version": "latest", "target_roles": ["search_head", "indexer"]},
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "duplicate" in msg and "splunk_ta_nix" in msg

    def test_same_app_name_twice_via_deployment_server_raises(self):
        """Same app name twice when both are managed by the same deployment server must raise (target_roles do not help)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "ds", "roles": ["deployment_server"]}, {"name": "sh1", "roles": ["search_head"]}, {"name": "uf1", "roles": ["universal_forwarder"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "Splunk_TA_nix", "source": "splunkbase", "app_id": 833, "version": "latest", "target_roles": ["search_head", "indexer"]},
                    {"name": "Splunk_TA_nix", "source": "splunkbase", "app_id": 833, "version": "latest", "target_roles": ["universal_forwarder"], "customizations": {"local_configs": {"inputs.conf": {}}}},
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "duplicate" in msg and ("deployment server" in msg or "splunk_ta_nix" in msg)

    def test_duplicate_app_same_name_same_target_roles_direct_raises(self):
        """Two apps with same name, same target_roles, and deployment_target direct = duplicate."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "deployment_target": "direct", "target_roles": ["search_head"]},
                    {"name": "MyApp", "source": "local", "deployment_target": "direct", "target_roles": ["search_head"]},
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "duplicate" in str(exc_info.value).lower()

    def test_same_app_name_one_direct_one_auto_allowed(self):
        """Same app name with different deployment_target (direct vs auto) is allowed."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}, {"name": "ds", "roles": ["deployment_server"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "deployment_target": "direct", "target_roles": ["search_head"]},
                    {"name": "MyApp", "source": "local", "deployment_target": "auto", "target_roles": ["search_head"]},
                ]
            },
        }
        result = validate_config(config)
        assert len(result.splunk_app_deployment.apps) == 2

    def test_premium_app_single_standalone_sh_no_target_filter_required(self):
        """Single standalone search head: premium app without shc/hosts filters is allowed."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi"}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0].get("premium_app") == "itsi"

    def test_premium_app_multiple_standalone_sh_requires_target_filter_raises(self):
        """Multiple standalone search heads: premium app must set shc_whitelist, hosts_whitelist, or other target filter."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"]},
                {"name": "sh2", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi"}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "shc_whitelist" in msg or "hosts_whitelist" in msg or "targeting" in msg

    def test_premium_app_multiple_standalone_sh_with_hosts_whitelist_allowed(self):
        """Multiple standalone search heads: premium app with hosts_whitelist set is allowed."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"]},
                {"name": "sh2", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "hosts_whitelist": ["sh1"]}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0].get("premium_app") == "itsi"
        assert result.splunk_app_deployment.apps[0].get("hosts_whitelist") == ["sh1"]

    def test_premium_app_shc_and_standalone_sh_requires_target_filter_raises(self):
        """SHC and standalone search head: premium app must set shc_whitelist or hosts_whitelist (no blacklists)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi"}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "shc_whitelist" in msg or "hosts_whitelist" in msg or "targeting" in msg

    def test_premium_app_shc_and_standalone_sh_with_shc_whitelist_allowed(self):
        """SHC and standalone search head: premium app with shc_whitelist set is allowed."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "shc_whitelist": ["shc1"]}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0].get("premium_app") == "itsi"
        assert result.splunk_app_deployment.apps[0].get("shc_whitelist") == ["shc1"]

    def test_premium_app_idxc_whitelist_not_allowed_raises(self):
        """Premium apps may only use hosts_whitelist and shc_whitelist (no blacklists); idxc_* is not allowed."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_idxclusters": [{"idxc_name": "idxc1"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "idxc_whitelist": ["idxc1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "idxc_whitelist" in msg
        assert "hosts_whitelist" in msg or "shc_whitelist" in msg

    def test_premium_app_am_whitelist_not_allowed_raises(self):
        """Premium apps may not use am_whitelist or am_blacklist; only hosts_* and shc_* filters allowed."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "ds1", "roles": ["deployment_server"]}, {"name": "uf1", "roles": ["universal_forwarder"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "am_whitelist": ["*"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "am_whitelist" in msg
        assert "hosts_whitelist" in msg or "shc_whitelist" in msg

    def test_premium_app_hosts_blacklist_not_allowed_raises(self):
        """Premium apps may only use hosts_whitelist and shc_whitelist; hosts_blacklist is not allowed (no blacklists)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "hosts_blacklist": ["sh1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "no blacklists" in msg
        assert "hosts_blacklist" in msg

    def test_premium_app_shc_blacklist_not_allowed_raises(self):
        """Premium apps may only use hosts_whitelist and shc_whitelist; shc_blacklist is not allowed (no blacklists)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "shc_blacklist": ["shc1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "no blacklists" in msg
        assert "shc_blacklist" in msg

    def test_premium_app_both_hosts_whitelist_and_shc_whitelist_not_allowed_raises(self):
        """Premium apps may use hosts_whitelist OR shc_whitelist, not both."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "dep", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "ITSI", "source": "splunkbase", "app_id": 1841, "premium_app": "itsi", "hosts_whitelist": ["standalone_sh"], "shc_whitelist": ["shc1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "premium" in msg
        assert "not both" in msg
        assert "hosts_whitelist" in msg
        assert "shc_whitelist" in msg


class TestTargetFilterOptions:
    """Tests for app deployment target filter options (hosts_whitelist, shc_whitelist, am_whitelist, etc.)."""

    def test_app_with_hosts_whitelist_and_shc_whitelist_valid(self):
        """App with hosts_whitelist (non-cluster hosts) and shc_whitelist (valid SHC name) validates."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "deployer1", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"prefix": "sh", "numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["search_head"], "shc_whitelist": ["shc1"], "hosts_whitelist": ["standalone_sh", "idx1"]}
                ]
            },
        }
        result = validate_config(config)
        app = result.splunk_app_deployment.apps[0]
        assert app.get("shc_whitelist") == ["shc1"]
        assert app.get("hosts_whitelist") == ["standalone_sh", "idx1"]

    def test_app_shc_whitelist_invalid_raises(self):
        """shc_whitelist must contain only names from splunk_shclusters."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "deployer1", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"prefix": "sh", "numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["search_head"], "shc_whitelist": ["shc_other"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "shc_whitelist" in msg or "splunk_shclusters" in msg

    def test_app_shc_whitelist_requires_splunk_shclusters_raises(self):
        """shc_whitelist or shc_blacklist requires splunk_shclusters to be defined."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["search_head"], "shc_whitelist": ["shc1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "shc_whitelist" in msg or "shc_blacklist" in msg
        assert "splunk_shclusters" in msg

    def test_app_idxc_whitelist_requires_splunk_idxclusters_raises(self):
        """idxc_whitelist or idxc_blacklist requires splunk_idxclusters to be defined."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "idx1", "roles": ["indexer"]},
                {"name": "idx2", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["indexer"], "idxc_whitelist": ["idxc1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "idxc_whitelist" in msg or "idxc_blacklist" in msg
        assert "splunk_idxclusters" in msg

    def test_app_am_whitelist_valid(self):
        """App with am_whitelist (serverclass patterns) validates."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "ds1", "roles": ["deployment_server"]}, {"name": "uf1", "roles": ["universal_forwarder"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["universal_forwarder"], "am_whitelist": ["*"]}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0].get("am_whitelist") == ["*"]

    def test_direct_deployment_am_whitelist_not_allowed_raises(self):
        """When deployment_target is direct, am_whitelist must not be set (deployment server is ignored)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}, {"name": "uf1", "roles": ["universal_forwarder"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "deployment_target": "direct", "target_roles": ["search_head"], "am_whitelist": ["*"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "am_whitelist" in msg
        assert "direct" in msg
        assert "deployment_target" in msg

    def test_direct_deployment_am_blacklist_not_allowed_raises(self):
        """When deployment_target is direct, am_blacklist must not be set (deployment server is ignored)."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "sh1", "roles": ["search_head"]}, {"name": "uf1", "roles": ["universal_forwarder"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "deployment_target": "direct", "target_roles": ["search_head"], "am_blacklist": ["some_serverclass"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "am_blacklist" in msg
        assert "direct" in msg
        assert "deployment_target" in msg

    def test_app_hosts_whitelist_must_exist_in_inventory_raises(self):
        """hosts_whitelist must contain only host names from splunk_hosts."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "sh1", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["search_head"], "hosts_whitelist": ["sh1", "unknown_host"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "hosts_whitelist" in msg
        assert "splunk_hosts" in msg or "unknown host" in msg

    def test_app_hosts_blacklist_must_exist_in_inventory_raises(self):
        """hosts_blacklist must contain only host names from splunk_hosts."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{"name": "uf1", "roles": ["universal_forwarder"]}, {"name": "uf2", "roles": ["universal_forwarder"]}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["universal_forwarder"], "hosts_blacklist": ["nonexistent"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "hosts_blacklist" in msg
        assert "splunk_hosts" in msg or "unknown host" in msg

    def test_app_hosts_whitelist_valid_when_hosts_exist(self):
        """hosts_whitelist with host names that exist in splunk_hosts validates."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "standalone_sh", "roles": ["search_head"]},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["search_head"], "hosts_whitelist": ["standalone_sh"]}
                ]
            },
        }
        result = validate_config(config)
        assert result.splunk_app_deployment.apps[0].get("hosts_whitelist") == ["standalone_sh"]

    def test_app_hosts_whitelist_cluster_member_raises(self):
        """hosts_whitelist and hosts_blacklist must not contain SHC or IDXC members."""
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [
                {"name": "deployer1", "roles": ["deployer"], "shcluster": "shc1"},
                {"iter": {"prefix": "sh", "numbers": "1..3"}, "roles": ["search_head"], "shcluster": "shc1"},
                {"name": "idx1", "roles": ["indexer"]},
            ],
            "splunk_shclusters": [{"shc_name": "shc1", "shc_secret": "secret"}],
            "splunk_app_deployment": {
                "apps": [
                    {"name": "MyApp", "source": "local", "target_roles": ["search_head"], "hosts_whitelist": ["sh1"]}
                ]
            },
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        msg = str(exc_info.value).lower()
        assert "hosts_whitelist" in msg or "hosts_blacklist" in msg
        assert "cluster" in msg
        assert "shc_whitelist" in msg or "idxc_whitelist" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
