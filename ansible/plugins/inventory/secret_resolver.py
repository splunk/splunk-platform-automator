"""
Secret resolution for splunk_config.yml.

Resolves Ansible Vault (!vault) secret references to plain strings. No
credentials are stored in this module; resolution uses the Ansible vault
password from config or environment. For environment variables, use Ansible's
built-in lookup('env', 'VAR_NAME') in playbooks or set env vars and omit
secrets from config (e.g. AWS_ACCESS_KEY_ID for Terraform).
"""

from __future__ import (absolute_import, division, print_function)

import os
import yaml
from collections import abc

# Marker types for secret references (detected by isinstance in resolve_config)


class VaultEncrypted(object):
    """Holds Ansible Vault encrypted ciphertext (from YAML !vault)."""

    __slots__ = ('ciphertext',)

    def __init__(self, ciphertext):
        if isinstance(ciphertext, bytes):
            self.ciphertext = ciphertext
        else:
            self.ciphertext = ciphertext.encode('utf-8') if ciphertext else b''

    def __repr__(self):
        return 'VaultEncrypted(<...>)'


def resolve_config(config, type_resolvers):
    """
    Recursively walk config and replace every secret reference with its resolved string.

    type_resolvers: dict mapping type -> callable(ref) -> str.
                    e.g. {VaultEncrypted: vault_decrypt_fn}
    Returns a new dict/list structure; does not mutate input.
    """
    if config is None:
        return None

    def resolve_value(value):
        for ref_type, resolver in type_resolvers.items():
            if isinstance(value, ref_type):
                return resolver(value)
        return value

    if isinstance(config, dict):
        return {k: resolve_config(resolve_value(v), type_resolvers) for k, v in config.items()}
    if isinstance(config, list):
        return [resolve_config(resolve_value(item), type_resolvers) for item in config]
    # Already a leaf; resolve if it's a secret ref
    return resolve_value(config)


def get_vault_resolver():
    """
    Return (VaultEncrypted, resolver_fn) if Ansible vault is available and
    password is configured; else (None, None).

    Resolver raises with a clear message if decryption fails.
    """
    try:
        from ansible.constants import DEFAULT_VAULT_ID_MATCH, DEFAULT_VAULT_PASSWORD_FILE
        from ansible.parsing.vault import VaultLib, VaultSecret
    except ImportError:
        return None, None

    password_file = os.environ.get('ANSIBLE_VAULT_PASSWORD_FILE') or DEFAULT_VAULT_PASSWORD_FILE
    password = None
    if password_file and os.path.isfile(password_file):
        try:
            with open(password_file, 'rb') as f:
                password = f.read().rstrip(b'\n\r')
        except IOError:
            pass
    if not password and os.environ.get('ANSIBLE_VAULT_PASSWORD'):
        password = os.environ.get('ANSIBLE_VAULT_PASSWORD', '').encode('utf-8')

    if not password:
        return None, None

    try:
        vault = VaultLib([(DEFAULT_VAULT_ID_MATCH, VaultSecret(password))])
    except Exception:
        return None, None

    def decrypt(ref):
        try:
            return vault.decrypt(ref.ciphertext).decode('utf-8')
        except Exception as e:
            raise ValueError(
                'Failed to decrypt vault value. Check that the vault password is correct '
                'and that the value is valid Ansible Vault ciphertext. '
                'Configure vault_password_file in ansible.cfg or set ANSIBLE_VAULT_PASSWORD_FILE / '
                'ANSIBLE_VAULT_PASSWORD. Original error: %s' % e
            )

    return VaultEncrypted, decrypt


def build_type_resolvers(vault_available=True):
    """
    Build the type_resolvers dict for resolve_config (vault only).
    """
    type_resolvers = {}
    if vault_available:
        vtype, vfn = get_vault_resolver()
        if vtype is not None:
            type_resolvers[vtype] = vfn
    return type_resolvers


def _normalize_vault_ciphertext(ciphertext_str):
    """
    Normalize vault ciphertext so Ansible VaultLib can decrypt it.
    - Strip leading/trailing whitespace and strip each line (fixes YAML indentation).
    - If ciphertext is space-separated instead of newline-separated (e.g. from
      paste or YAML folding), replace spaces with newlines.
    """
    if not ciphertext_str or not isinstance(ciphertext_str, str):
        return ciphertext_str
    s = ciphertext_str.strip()
    if "\n" in s:
        # Already has newlines; strip each line to remove YAML indentation
        lines = [line.strip() for line in s.splitlines()]
        return "\n".join(lines)
    # Single line with spaces: vault format expects newline-separated lines
    if " " in s:
        s = s.replace(" ", "\n")
    return s


def _resolve_plain_string_secret(value, vault_decrypt_fn):
    """
    If value is a string that looks like a quoted !vault reference, resolve it
    and return the decrypted string; otherwise return value unchanged.

    Quoted vault allows the file to remain valid standard YAML so Ansible can
    parse the inventory before delegating to our plugin.
    """
    if not isinstance(value, str) or not value:
        return value
    s = value.strip()
    # Quoted vault: string containing $ANSIBLE_VAULT (optionally after "!vault |\n")
    if "$ANSIBLE_VAULT" in s and vault_decrypt_fn is not None:
        idx = s.find("$ANSIBLE_VAULT")
        ciphertext_str = s[idx:]
        # Ansible Vault expects newline-separated lines; YAML or paste may give space-separated
        ciphertext_str = _normalize_vault_ciphertext(ciphertext_str)
        try:
            ref = VaultEncrypted(ciphertext_str)
            return vault_decrypt_fn(ref)
        except Exception as e:
            raise ValueError(
                "Failed to decrypt quoted vault value. Check vault password and format. %s" % e
            )
    return value


def _resolve_plain_string_secrets_recursive(config, vault_decrypt_fn):
    """
    Recursively walk config and resolve any string value that looks like
    a quoted !vault reference. Returns a new structure.
    """
    if config is None:
        return None
    if isinstance(config, dict):
        return {
            k: _resolve_plain_string_secrets_recursive(
                _resolve_plain_string_secret(v, vault_decrypt_fn),
                vault_decrypt_fn,
            )
            for k, v in config.items()
        }
    if isinstance(config, list):
        return [
            _resolve_plain_string_secrets_recursive(
                _resolve_plain_string_secret(item, vault_decrypt_fn),
                vault_decrypt_fn,
            )
            for item in config
        ]
    return config


def vault_constructor(loader, node):
    """YAML constructor for !vault -> VaultEncrypted(encrypted_string)."""
    value = loader.construct_scalar(node)
    if value is not None:
        value = value.strip()
    return VaultEncrypted(value or '')


def get_yaml_loader(with_vault=True):
    """
    Return a YAML Loader class that registers the !vault constructor.
    """
    class Loader(yaml.SafeLoader):
        pass
    if with_vault:
        Loader.add_constructor('!vault', vault_constructor)
    return Loader


def load_config_with_secrets(path, resolve_secrets=True):
    """
    Load YAML from path, optionally resolving quoted !vault secret references.

    Uses yaml.safe_load so the file must be valid standard YAML (no custom tags).
    Secret references must be quoted strings: '!vault |\\n...' so that Ansible
    can parse the inventory file before delegating to our plugin.
    If resolve_secrets=True, quoted !vault strings are decrypted and replaced
    with the actual secret values. If resolve_secrets=False, return as-is.
    """
    with open(path, "r") as f:
        config = yaml.safe_load(f) or {}
    if resolve_secrets:
        vtype, vault_decrypt_fn = get_vault_resolver()
        if vtype is None:
            vault_decrypt_fn = None
        config = _resolve_plain_string_secrets_recursive(config, vault_decrypt_fn)
    return config
