# Secrets

Keep credentials out of version control. In `splunk_config.yml`, use environment lookups or quoted Ansible Vault values. Agents and logs must report variables only as **set** or **not set**, never print values or decrypted content.

## Environment lookups

```yaml
splunk_passwords:
  splunk_admin_password: "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"
```

Use CI or operating-system secret storage to set the variable. `spa validate` resolves the value without writing it back to config.

`CCM_TOKEN` is a process environment variable for employee-only Corporate Cloud Manager, not a `splunk_config.yml` key. SPA reports it as **set** or **not set**. Schema and comments may say `lookup('env', 'CCM_TOKEN')`; do not add a `CCM_TOKEN:` YAML key. Never echo the value. Operator page: [CCM](ccm.md).

## Where to create missing credentials

Do not paste secret values into chat. Export them in the shell, then re-run `spa doctor` / `spa validate`.

| Need | Create in | Then |
| --- | --- | --- |
| `CCM_TOKEN` and the CCM SSH key | [CCM UI](https://ccm.splunkits.io/) | Export `CCM_TOKEN`. Set `ccm.key_name` and keep the private file at `ccm.ssh_private_key_file`. |
| AWS access keys or a named profile | [IAM console](https://console.aws.amazon.com/iam/) | Prefer `AWS_PROFILE`; otherwise `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (and `AWS_SESSION_TOKEN` when required). |
| AWS EC2 key pair | [EC2 console](https://console.aws.amazon.com/ec2/) in the env region | Download the PEM once. Set `terraform.aws.key_name` and `ssh_private_key_file`. |
| Splunkbase downloads | [Splunkbase](https://splunkbase.splunk.com/) (Splunk.com account) | Export `SPLUNKBASE_USERNAME` and `SPLUNKBASE_PASSWORD`. |

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
spa deploy --yes
spa destroy --yes
```

Provide the vault password through the supported environment/file source before calling `spa`; do not pass secret values on the command line.

## Troubleshoot safely

- Parse errors around `!vault`: ensure the complete multiline value is quoted.
- Decryption failures: confirm the configured password source matches the password used to encrypt.
- Validation failures after decryption: the secret resolved, but its value does not satisfy the schema.
- Missing environment values: check whether the variable is set without echoing it.

Secret-resolution tests live in `tests/test_secret_resolver.py` and `tests/test_spa_vault_decrypt.py`.
