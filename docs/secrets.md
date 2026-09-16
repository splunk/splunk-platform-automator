# Secrets

Keep credentials out of version control. In `splunk_config.yml`, use environment lookups or quoted Ansible Vault values. Agents and logs must report variables only as **set** or **not set**, never print values or decrypted content.

## Environment lookups

```yaml
splunk_passwords:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
```

Use CI or operating-system secret storage to set the variable. `spa validate` resolves the value without writing it back to config.

## Ansible Vault

Generate an encrypted string with `ansible-vault encrypt_string`, then quote the entire multiline value in YAML. The quote is required because SPA's inventory loader first parses standard YAML; a raw `!vault` tag is not a registered YAML constructor at that stage.

```yaml
splunk_passwords:
  splunk_admin_password: '!vault |
    $ANSIBLE_VAULT;1.1;AES256
    ENCRYPTED_DATA_FROM_ANSIBLE_VAULT'
```

The placeholder above is not a credential. Replace it with output generated locally; never paste real encrypted or plaintext secrets into chat.

Vault password sources, in precedence order:

1. `ANSIBLE_VAULT_PASSWORD_FILE`
2. `ANSIBLE_VAULT_PASSWORD`
3. `vault_password_file` in `ansible.cfg`

Do not commit the password file. In CI, use the platform's secret store.

## Provision-time decryption

Some infrastructure playbooks load config with `include_vars` rather than the inventory plugin. They use the SPA `spa_vault_decrypt` lookup for encrypted AWS values. It decrypts strings containing the Vault marker and returns non-vault strings unchanged, allowing one code path for env/vault-backed configuration.

Operators still call:

```bash
spa provision --yes
spa destroy --yes
```

Provide the vault password through the supported environment/file source before calling `spa`; do not pass secret values on the command line.

## Troubleshoot safely

- Parse errors around `!vault`: ensure the complete multiline value is quoted.
- Decryption failures: confirm the configured password source matches the password used to encrypt.
- Validation failures after decryption: the secret resolved, but its value does not satisfy the schema.
- Missing environment values: check whether the variable is set without echoing it.

Secret-resolution tests live in `tests/test_secret_resolver.py` and `tests/test_spa_vault_decrypt.py`.
