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
            host = {"name": f"host_{i}", "roles": [role]}
            # cluster_manager requires idxcluster
            if role == "cluster_manager":
                host["idxcluster"] = "idxc1"
            hosts.append(host)
        
        config = {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": hosts
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
                }
            ]
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
                }
            ]
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
                {"name": "ds1", "roles": ["deployer"], "site": "site1"}
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
                {"name": "idx1", "roles": ["indexer"], "idxcluster": "idxc1"}
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
                {"name": "sh1", "roles": ["search_head"], "shcluster": "shc1"}
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
                {"name": "ds", "roles": ["deployment_server", "deployer"]}
            ]
        }
        result = validate_config(config)
        assert len(result.splunk_hosts[0].roles) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
