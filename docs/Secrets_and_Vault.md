# Storing Secrets in splunk_config.yml

Passwords and other secrets in `config/splunk_config.yml` can be stored securely using **Ansible Vault** (`!vault`) instead of plain text. This keeps secrets out of version control and follows good security practice.

For **environment variables** (e.g. AWS credentials for Terraform), use Ansible’s built-in mechanism: set the env vars when running Ansible (e.g. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) and omit those keys from the config so Terraform uses the default credential chain. Or in playbooks use `lookup('env', 'VAR_NAME')` to pass env values into tasks.

**Important:** Vault references must be written as **quoted strings** in the YAML. Ansible parses the inventory file with standard YAML before delegating to the plugin; unquoted `!vault` would cause a parse error. Use quoted form (e.g. `'!vault |\n...'`) so the file is valid and the plugin can decrypt when it runs.

## Quick start

1. **Encrypt a secret with Ansible Vault** (one-time):
   ```bash
   ansible-vault encrypt_string 'mySecretPassword' --name 'splunk_admin_password'
   ```
   Copy the output (including the `!vault |` block) into your `splunk_config.yml`. **Quote the entire value** so it is a single YAML string (see [Vault: quoted format](#vault-quoted-format) below).

2. **Provide the vault password** when running Ansible:
   - Set `vault_password_file` in `ansible.cfg` to a file that contains the vault password (one line), **or**
   - Set the `ANSIBLE_VAULT_PASSWORD_FILE` environment variable to that file path, **or**
   - Set the `ANSIBLE_VAULT_PASSWORD` environment variable to the password.

3. Run your playbooks as usual; the inventory plugin will decrypt secrets in the config when it loads it.

**Playbooks that load config via `include_vars`** (e.g. Terraform AWS provision/destroy) do not use the inventory plugin’s decryption. For those, use the **`spa_vault_decrypt` lookup** to decrypt vault-encrypted values in the playbook (see [spa_vault_decrypt lookup](#spa_vault_decrypt-lookup) below).

## YAML tags

### `!vault` (Ansible Vault)

Use Ansible Vault to encrypt sensitive values. Any string value in the config can be replaced with an encrypted block.

**Example: encrypt a single value**

```bash
ansible-vault encrypt_string 'MyS3cr3tP@ss' --name 'splunk_admin_password'
```

**Vault: quoted format**

The output of `ansible-vault encrypt_string` uses the tag `!vault |`. When pasting into `splunk_config.yml`, you **must wrap the whole value in quotes** (single or double) so that it is a single YAML string. Otherwise Ansible’s inventory parser will fail with “could not determine a constructor for the tag '!vault'”. The plugin then reads the file, sees the quoted string, and decrypts it when the vault password is available.

Example (quoted so the file is valid standard YAML):

```yaml
splunk_defaults:
  splunk_admin_password: '!vault |
    $ANSIBLE_VAULT;1.1;AES256
    663864396537386534643361653739316136646230333865...'
```

**Example: common secret locations**

- `splunk_defaults.splunk_admin_password` – Splunk admin password
- `splunk_defaults.splunk_ssl.inputs.config.password` – SSL passphrase (if used)
- `splunk_idxclusters[].idxc_password` – Indexer cluster secret
- `splunk_shclusters[].shc_password` – Search head cluster secret
- `splunk_hosts[].custom` – Any custom variable (e.g. connection passwords)
- `terraform.aws.access_key_id` / `secret_access_key` – Prefer leaving these unset and using the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables when running Terraform playbooks.

You can use `!vault` for **any** string value; the plugin resolves all encrypted values recursively.

## spa_vault_decrypt lookup

Playbooks that load `splunk_config.yml` with **`include_vars`** (for example `provision_terraform_aws.yml` and `destroy_terraform_aws.yml`) do not go through the inventory plugin, so vault-encrypted values in the config are still literal strings after `include_vars`. To decrypt them in the playbook, use the custom lookup **`spa_vault_decrypt`**.

**Usage**

- Pass a single variable (or expression) that may contain a vault-encrypted string or plain text:
  ```yaml
  - name: Set credentials from config (vault or plain)
    ansible.builtin.set_fact:
      my_secret: "{{ lookup('spa_vault_decrypt', some_var_from_config) | trim }}"
  ```
- If the value contains `$ANSIBLE_VAULT`, it is decrypted using the same vault password as the inventory (see [Vault password configuration](#vault-password-configuration)).
- If the value does **not** contain `$ANSIBLE_VAULT`, it is returned trimmed unchanged (so one task can handle both vault-encrypted and plain values).

**Where it’s used**

- **Terraform AWS playbooks** use `spa_vault_decrypt` to set `terraform_env` from `terraform.aws.access_key_id` and `terraform.aws.secret_access_key` when those keys are present in the config (vault or plain). Provide the vault password (e.g. `ANSIBLE_VAULT_PASSWORD` or `--ask-vault-pass`) when running those playbooks if you store vault-encrypted AWS credentials in the config.

**Requirements**

- The lookup plugin path must be set so Ansible can find it. The project’s `ansible.cfg` sets `lookup_plugins = ./ansible/plugins/lookup`.
- Same vault password sources as the rest of Ansible: `ANSIBLE_VAULT_PASSWORD`, `ANSIBLE_VAULT_PASSWORD_FILE`, or `--ask-vault-pass` / `--vault-password-file`.

## Vault password configuration

The plugin uses the same vault password sources as Ansible (in order of precedence):

1. **`ANSIBLE_VAULT_PASSWORD_FILE`** – Path to a file containing the vault password (one line).
2. **`ANSIBLE_VAULT_PASSWORD`** – The vault password string (e.g. in CI).
3. **`vault_password_file` in ansible.cfg** – Set in your project’s `ansible.cfg`, e.g.:
   ```ini
   [defaults]
   vault_password_file = .vault_pass.txt
   ```

**Security**

- **Do not commit** the vault password or the password file to version control.  
  Add entries like `.vault_pass.txt` and `.vault_pass` to `.gitignore` (the project already ignores common patterns).
- Restrict permissions on the password file: `chmod 600 .vault_pass.txt`.
- In CI, use a secret (e.g. `ANSIBLE_VAULT_PASSWORD`) stored in the CI secret store, not in the repo.

## Backward compatibility

- If you do **not** use `!vault`, the config is loaded and used as before; no vault password is required.
- Existing `splunk_config.yml` files without secret tags continue to work unchanged.

## Troubleshooting

**"Secret resolution failed: Failed to decrypt vault value"**

- Ensure the vault password is correct and matches the one used to encrypt the value.
- Ensure the password is available via one of: `ANSIBLE_VAULT_PASSWORD_FILE`, `ANSIBLE_VAULT_PASSWORD`, or `vault_password_file` in `ansible.cfg`.
- Ensure you are running from a directory where `ansible.cfg` is found (or set the env vars explicitly).

**Schema validation errors after adding `!vault`**

- Validation runs **after** secrets are resolved, so the schema always sees plain strings. If you see validation errors, they are about structure or allowed values, not about the tags. Fix the key path or value type as indicated by the error.

## Testing

Unit tests for secret resolution and the `spa_vault_decrypt` lookup live in `tests/test_secret_resolver.py` and `tests/test_spa_vault_decrypt.py`. Use the run script so the correct Ansible config and environment are used:

```bash
./tests/run_secret_resolver_tests.sh -v
```

The script uses `tests/ansible_test.cfg` so the project’s main config (and config directory) are not loaded during tests. See the script and `tests/ansible_test.cfg` for details.
