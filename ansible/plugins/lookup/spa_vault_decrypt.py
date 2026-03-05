# Copyright (c) 2024, Splunk Inc.
# Inline vault decryption lookup for playbooks (no temp files).

from __future__ import absolute_import, division, print_function

import os

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


def _normalize_vault_ciphertext(s):
    """Normalize vault ciphertext for VaultLib (newline-separated lines)."""
    if not s or not isinstance(s, str):
        return s
    s = s.strip()
    if "\n" in s:
        lines = [line.strip() for line in s.splitlines()]
        return "\n".join(lines)
    if " " in s:
        s = s.replace(" ", "\n")
    return s


def _get_vault_password():
    """Vault password from ANSIBLE_VAULT_PASSWORD_FILE or ANSIBLE_VAULT_PASSWORD."""
    try:
        from ansible.constants import DEFAULT_VAULT_PASSWORD_FILE
    except ImportError:
        DEFAULT_VAULT_PASSWORD_FILE = None
    password_file = os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE") or DEFAULT_VAULT_PASSWORD_FILE
    password = None
    if password_file and os.path.isfile(password_file):
        try:
            with open(password_file, "rb") as f:
                password = f.read().rstrip(b"\n\r")
        except IOError:
            pass
    if not password and os.environ.get("ANSIBLE_VAULT_PASSWORD"):
        password = os.environ.get("ANSIBLE_VAULT_PASSWORD", "").encode("utf-8")
    return password


def _decrypt_string(value):
    """
    If value contains $ANSIBLE_VAULT, decrypt and return plaintext; else return value trimmed.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value).strip()
    s = value.strip()
    if "$ANSIBLE_VAULT" not in s:
        return s
    idx = s.find("$ANSIBLE_VAULT")
    ciphertext = _normalize_vault_ciphertext(s[idx:])
    password = _get_vault_password()
    if not password:
        raise AnsibleError(
            "spa_vault_decrypt: no vault password. Set ANSIBLE_VAULT_PASSWORD or "
            "ANSIBLE_VAULT_PASSWORD_FILE (or use --ask-vault-pass / --vault-password-file)."
        )
    try:
        from ansible.constants import DEFAULT_VAULT_ID_MATCH
        from ansible.parsing.vault import VaultLib, VaultSecret
    except ImportError as e:
        raise AnsibleError("spa_vault_decrypt: Ansible vault not available: %s" % e)
    vault = VaultLib([(DEFAULT_VAULT_ID_MATCH, VaultSecret(password))])
    try:
        return vault.decrypt(ciphertext.encode("utf-8")).decode("utf-8").strip()
    except Exception as e:
        raise AnsibleError(
            "spa_vault_decrypt: decryption failed. Check vault password and value format. %s" % e
        )


class LookupModule(LookupBase):
    """
    Inline decrypt a vault-encrypted string (e.g. from include_vars).

    Usage:
      - lookup('spa_vault_decrypt', terraform.aws.access_key_id)
      - lookup('spa_vault_decrypt', some_var)

    If the value does not contain $ANSIBLE_VAULT, it is returned trimmed unchanged.
    Uses ANSIBLE_VAULT_PASSWORD or ANSIBLE_VAULT_PASSWORD_FILE.
    """

    def run(self, terms, variables=None, **kwargs):
        if not terms:
            raise AnsibleError("spa_vault_decrypt requires one argument (the value to decrypt).")
        if len(terms) > 1:
            raise AnsibleError("spa_vault_decrypt accepts a single value; got %d." % len(terms))
        value = terms[0]
        result = _decrypt_string(value)
        return [result]
