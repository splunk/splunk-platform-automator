"""
Unit tests for secret resolution (vault) in splunk_config.yml.

Tests the secret_resolver module and integration with the inventory plugin.
"""

import os
import sys
import tempfile
import pytest

pytestmark = pytest.mark.local


@pytest.fixture(autouse=True)
def _ansible_test_config(monkeypatch):
    """Isolate from project ansible.cfg (config/splunk_config.yml inventory)."""
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    monkeypatch.setenv("ANSIBLE_CONFIG", os.path.join(tests_dir, "ansible_test.cfg"))
    ansible_tmp = os.path.join(tests_dir, ".ansible_tmp")
    os.makedirs(ansible_tmp, exist_ok=True)
    monkeypatch.setenv("ANSIBLE_LOCAL_TMP", ansible_tmp)


# Add the inventory plugin directory so we can import secret_resolver and schema
plugin_dir = os.path.join(os.path.dirname(__file__), '..', 'ansible', 'plugins', 'inventory')
sys.path.insert(0, os.path.abspath(plugin_dir))

from secret_resolver import (
    VaultEncrypted,
    resolve_config,
    build_type_resolvers,
    get_vault_resolver,
    get_yaml_loader,
    load_config_with_secrets,
)


class TestResolveConfig:
    """Test resolve_config recursive resolution."""

    def test_plain_dict_unchanged(self):
        """Plain dict with no secret refs is returned as-is (structure)."""
        config = {"a": 1, "b": "hello", "c": None}
        type_resolvers = {}
        out = resolve_config(config, type_resolvers)
        assert out == config

    def test_plain_list_unchanged(self):
        """Plain list is returned as-is."""
        config = [1, "two", None]
        out = resolve_config(config, {})
        assert out == config

    def test_nested_structure_preserved(self):
        """Nested dicts and lists are preserved."""
        config = {"top": {"inner": [1, 2], "k": "v"}}
        out = resolve_config(config, {})
        assert out == config
        assert out["top"]["inner"] == [1, 2]

    def test_vault_ref_resolved(self):
        """VaultEncrypted values are replaced by resolver."""
        type_resolvers = {
            VaultEncrypted: lambda ref: "decrypted_value"
        }
        config = {"password": VaultEncrypted(b"x")}
        out = resolve_config(config, type_resolvers)
        assert out["password"] == "decrypted_value"

    def test_mixed_nested_resolution(self):
        """Nested structure with plain and vault ref values."""
        type_resolvers = {
            VaultEncrypted: lambda ref: "vault_decrypted"
        }
        config = {
            "a": "plain",
            "b": {"secret": VaultEncrypted(b"x")},
            "c": [1, "z"]
        }
        out = resolve_config(config, type_resolvers)
        assert out["a"] == "plain"
        assert out["b"]["secret"] == "vault_decrypted"
        assert out["c"] == [1, "z"]


class TestBuildTypeResolvers:
    """Test build_type_resolvers (vault only)."""

    def test_vault_resolver_optional(self):
        """Vault resolver may or may not be present depending on Ansible/password."""
        resolvers = build_type_resolvers(vault_available=True)
        if VaultEncrypted in resolvers:
            assert callable(resolvers[VaultEncrypted])

    def test_no_vault_when_disabled(self):
        """When vault_available=False, no vault resolver."""
        resolvers = build_type_resolvers(vault_available=False)
        assert VaultEncrypted not in resolvers or resolvers.get(VaultEncrypted) is None


class TestYamlLoader:
    """Test custom YAML loader with !vault."""

    def test_plain_yaml_unchanged(self):
        """Plain YAML without custom tags loads normally."""
        loader_class = get_yaml_loader(with_vault=True)
        import yaml
        data = yaml.load("a: 1\nb: hello", Loader=loader_class)
        assert data == {"a": 1, "b": "hello"}


class TestLoadConfigWithSecrets:
    """Test full load_config_with_secrets with temp files."""

    def test_load_plain_yaml(self):
        """Config without secret tags loads and is unchanged."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("plugin: splunk-platform-automator\n")
            f.write("splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n")
            f.flush()
            path = f.name
        try:
            config = load_config_with_secrets(path, resolve_secrets=True)
            assert config["plugin"] == "splunk-platform-automator"
            assert len(config["splunk_hosts"]) == 1
            assert config["splunk_hosts"][0]["name"] == "idx1"
        finally:
            os.unlink(path)

    def test_quoted_vault_string_unchanged_when_no_password(self):
        """Quoted vault string in YAML is left unchanged when vault password is not set."""
        vault_literal = "!vault | $ANSIBLE_VAULT;1.1;AES256  deadbeef"
        saved_pass = os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
        saved_file = os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
                f.write("plugin: splunk-platform-automator\n")
                f.write("splunk_defaults:\n  splunk_admin_password: '%s'\n" % vault_literal)
                f.flush()
                path = f.name
            try:
                # With no vault password in env, get_vault_resolver returns None -> value unchanged
                config = load_config_with_secrets(path, resolve_secrets=True)
                assert "splunk_defaults" in config
                assert "splunk_admin_password" in config.get("splunk_defaults", {})
                assert "$ANSIBLE_VAULT" in config["splunk_defaults"]["splunk_admin_password"]
            finally:
                os.unlink(path)
        finally:
            if saved_pass is not None:
                os.environ["ANSIBLE_VAULT_PASSWORD"] = saved_pass
            if saved_file is not None:
                os.environ["ANSIBLE_VAULT_PASSWORD_FILE"] = saved_file

    def test_quoted_vault_string_unchanged_when_resolve_secrets_false(self):
        """Quoted vault string is unchanged when resolve_secrets=False."""
        vault_literal = "!vault | $ANSIBLE_VAULT;1.1;AES256  deadbeef"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("terraform:\n  aws:\n    access_key_id: '%s'\n" % vault_literal)
            f.flush()
            path = f.name
        try:
            config = load_config_with_secrets(path, resolve_secrets=False)
            assert config["terraform"]["aws"]["access_key_id"] == vault_literal
        finally:
            os.unlink(path)
