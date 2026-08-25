"""
Unit tests for the spa_vault_decrypt lookup plugin (playbook inline decryption).

Covers pass-through for plain values and error when vault string is used without
a vault password. Does not require real vault-encrypted data.

If import fails (e.g. in sandbox where ~/.ansible/tmp is not writable), the
entire module is skipped so test_secret_resolver.py still runs.
"""

import os
import sys
import pytest

# Ensure the lookup plugin can be imported (ansible is from ansible-core)
lookup_dir = os.path.join(os.path.dirname(__file__), '..', 'ansible', 'plugins', 'lookup')
sys.path.insert(0, os.path.abspath(lookup_dir))

lookup_module = None
AnsibleError = None
try:
    import spa_vault_decrypt as lookup_module
    from ansible.errors import AnsibleError
except Exception:
    pass

pytestmark = [
    pytest.mark.local,
    pytest.mark.skipif(
        lookup_module is None,
        reason="Could not import spa_vault_decrypt (Ansible may need writable ~/.ansible/tmp; run without sandbox or use full permissions)",
    ),
]


@pytest.fixture(autouse=True)
def _ansible_test_config(monkeypatch):
    """Isolate from project ansible.cfg (config/splunk_config.yml inventory)."""
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    monkeypatch.setenv("ANSIBLE_CONFIG", os.path.join(tests_dir, "ansible_test.cfg"))
    ansible_tmp = os.path.join(tests_dir, ".ansible_tmp")
    os.makedirs(ansible_tmp, exist_ok=True)
    monkeypatch.setenv("ANSIBLE_LOCAL_TMP", ansible_tmp)


class TestSpaVaultDecryptLookup:
    """Test spa_vault_decrypt lookup: pass-through and error cases."""

    def setup_method(self):
        if lookup_module is None:
            pytest.skip("spa_vault_decrypt not importable")
        self.lookup = lookup_module.LookupModule()

    def test_plain_string_passthrough(self):
        """Plain string without $ANSIBLE_VAULT is returned trimmed in a list."""
        result = self.lookup.run(["my_plain_value"], variables=None)
        assert result == ["my_plain_value"]

    def test_plain_string_trimmed(self):
        """Whitespace around plain value is trimmed."""
        result = self.lookup.run(["  aws_key_123  "], variables=None)
        assert result == ["aws_key_123"]

    def test_none_returns_empty_string(self):
        """None as value returns list with empty string."""
        result = self.lookup.run([None], variables=None)
        assert result == [""]

    def test_non_string_coerced_to_stripped_string(self):
        """Non-string value is coerced to string and trimmed."""
        result = self.lookup.run([12345], variables=None)
        assert result == ["12345"]

    def test_empty_terms_raises(self):
        """Empty terms list raises AnsibleError."""
        with pytest.raises(AnsibleError) as exc_info:
            self.lookup.run([], variables=None)
        assert "one argument" in str(exc_info.value)

    def test_too_many_terms_raises(self):
        """More than one term raises AnsibleError."""
        with pytest.raises(AnsibleError) as exc_info:
            self.lookup.run(["a", "b"], variables=None)
        assert "single value" in str(exc_info.value)

    def test_vault_like_string_without_password_raises(self):
        """Value containing $ANSIBLE_VAULT with no vault password raises AnsibleError."""
        vault_like = "!vault | $ANSIBLE_VAULT;1.1;AES256  deadbeef"
        saved_pass = os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
        saved_file = os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
        try:
            with pytest.raises(AnsibleError) as exc_info:
                self.lookup.run([vault_like], variables=None)
            assert "no vault password" in str(exc_info.value).lower() or "spa_vault_decrypt" in str(exc_info.value)
        finally:
            if saved_pass is not None:
                os.environ["ANSIBLE_VAULT_PASSWORD"] = saved_pass
            if saved_file is not None:
                os.environ["ANSIBLE_VAULT_PASSWORD_FILE"] = saved_file
