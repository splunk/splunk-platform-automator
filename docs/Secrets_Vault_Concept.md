# Concept: Secrets and Vault Support for splunk_config.yml

**Status: Implemented.** See [Secrets_and_Vault.md](Secrets_and_Vault.md) for user documentation and usage.

## 1. Goal

Allow passwords and other secrets required in `config/splunk_config.yml` to be stored securely instead of in plain text. The implementation should:

- Support **Ansible Vault** as a first-class option (encrypted `!vault` in YAML).
- Remain **open for other vault backends** (e.g. env vars, HashiCorp Vault, or custom resolvers) so teams can plug in their preferred secret store.
- Avoid hardcoding credentials in source (see workspace rule: no hardcoded credentials).
- Use a single, clear place where config is loaded and secrets are resolved, so the rest of the plugin always sees decrypted values.

---

## 2. Current State and the Old Patch

### 2.1 Where secrets appear today

From the schema and examples, sensitive values can appear in:

| Location | Example keys |
|----------|----------------|
| `splunk_defaults` | `splunk_admin_password`, `splunk_ssl.inputs.config.password` |
| `splunk_idxclusters[]` | `idxc_password`, `idxc_discovery_password` |
| `splunk_shclusters[]` | `shc_password` |
| `splunk_hosts[].custom` | Arbitrary keys (e.g. connection secrets) |
| `splunk_environments[]` | `splunk_admin_password` (per env) |
| `aws` | `access_key_id`, `secret_access_key` (if not from env) |
| `terraform.aws` | Same as above when provided in config |

So secrets are both in known, structured keys and in free-form sections like `custom`.

### 2.2 What the old patch did (`ansible_vault_patch.txt`)

- **ansible.cfg**: Set `vault_password_file=../.vault_pass.txt` so Ansible has a vault password.
- **Inventory plugin** (`_set_virtualization`):
  - If `DEFAULT_VAULT_PASSWORD_FILE` is set, created a `VaultLib` and a custom YAML `!vault` constructor that wraps encrypted strings in a `VaultString` class.
  - Re-opened the config file, loaded with `yaml.safe_load()` and the custom constructor, then ran a **hardcoded** function `vault_translate_string()` that:
    - Checked specific paths (`splunk_defaults.splunk_admin_password`, `splunk_ssl.inputs.config.password`, `splunk_idxclusters[].idxc_password`, `splunk_shclusters[].shc_password`, `splunk_hosts[].custom.*`).
    - Used `str(type(...)).split('.')[-1].startswith('VaultString')` to detect vault-wrapped values and called `.decrypt()` on them.

### 2.3 Limitations of the old patch

1. **Decrypted config is never used**  
   Decryption happens in `_set_virtualization()` and only updates a **local** `splunk_config` variable. The plugin’s real data comes from `get_option(section)` (filled by Ansible’s loader from the same file). So the rest of the code never sees the decrypted values unless Ansible’s loader also decrypts `!vault` (which depends on loader context).

2. **Hardcoded secret paths**  
   Every secret location is listed manually in `vault_translate_string()`. Adding a new secret (e.g. under `terraform`, or a new nested key) requires code changes and is easy to forget.

3. **Fragile type check**  
   Using `str(type(...)).startswith('VaultString')` is brittle (e.g. with subclasses or different loaders).

4. **Single backend**  
   Only Ansible Vault is supported; no hook for env vars, external vaults, or other schemes.

5. **Vault password file path**  
   `../.vault_pass.txt` in ansible.cfg is relative and may be wrong depending on CWD; vault password in a file must be handled carefully (permissions, no commit).

6. **Schema validation**  
   Schema validation runs on raw YAML (`yaml.safe_load`). With `!vault`, those values are either opaque strings or custom types; validation might need to accept “secret reference” types or run after resolution.

---

## 3. Proposed Direction: Pluggable Secret Resolution

### 3.1 Principles

- **Single load + resolve**: Load the config once, resolve all secret references in one step, then use the resolved config everywhere (options, virtualization, populate).
- **Backend-agnostic**: Introduce a small “secret resolver” abstraction. Ansible Vault is one implementation; others can be added (env, HashiCorp Vault, file-based, etc.).
- **No hardcoded credential values** in code; only resolution logic and optional paths to password files or env var names (no actual secrets in repo).
- **Declarative secret locations (optional)**: Either mark known secret keys in schema/config so resolution is automatic, or use a convention (e.g. `!vault`) so any value can be a secret reference without listing every path. For environment variables, use Ansible’s built-in `lookup('env', 'VAR')` in playbooks or set env vars and omit secrets from config.

### 3.2 High-level flow

```
┌─────────────────────────────────────────────────────────────────┐
│  parse(path)                                                    │
│  1. Read raw YAML from path (with optional custom constructors  │
│     for !vault so values are “secret refs”)       │
│  2. [Optional] Validate schema (may allow SecretRef types)       │
│  3. Resolve secrets: walk config, replace every secret ref      │
│     with plain string using the configured SecretResolver       │
│  4. set self.configfiles from resolved config (not get_option)   │
│  5. _set_virtualization(resolved_config)                        │
│  6. _populate_defaults() ; _populate()  (unchanged)              │
└─────────────────────────────────────────────────────────────────┘
```

So the plugin **owns** loading the file and resolving secrets, then builds `configfiles` from the resolved dict. This avoids relying on Ansible’s loader to decrypt and keeps one source of truth.

### 3.3 Secret resolver abstraction

Small interface that the plugin uses to “resolve” a secret reference to a string:

- **Input**: Something that represents a secret (e.g. Ansible vault ciphertext, or an env var name, or a vault path).
- **Output**: Plain string (the secret value), or raise if resolution fails.

Possible backends:

| Backend | Description | Config / activation |
|--------|-------------|---------------------|
| **Ansible Vault** | Decrypt `!vault` blocks. Password from `vault_password_file` (ansible.cfg) or `ANSIBLE_VAULT_PASSWORD_FILE` / `ANSIBLE_VAULT_PASSWORD`. | Use when vault password is available; register custom YAML tag `!vault`. |
| **No-op / plain** | No encryption; value is used as-is. | Default when no vault is configured. |

Environment variables are not a backend in the plugin; use Ansible’s `lookup('env', 'VAR_NAME')` in playbooks or set env vars (e.g. `AWS_ACCESS_KEY_ID`) and omit those keys from config.

Later (out of scope for first version): HashiCorp Vault, AWS Secrets Manager, etc., by implementing the same “resolve(ref) → str” contract.

### 3.4 Where to resolve: convention over hardcoding

Two complementary approaches:

**A) YAML tags (recommended)**  
- Users put `!vault` in the YAML. Any key can hold a secret reference.  
- No need to enumerate paths in code; the loader produces “secret ref” objects, then a **generic recursive walk** replaces every ref with its resolved string.  
- Matches the old patch’s use of `!vault` and is familiar to Ansible users.

**B) Known secret keys (optional)**  
- Maintain a set of key names (and maybe key paths) that are “sensitive” (e.g. `splunk_admin_password`, `idxc_password`, `password`, `secret_access_key`).  
- Used for: documentation, optional validation (e.g. “warn if this key is plain text in repo”), or as a fallback if we ever support “auto-wrap” of plain values.  
- Does **not** replace tag-based resolution; it can sit in schema or a small constant set.

Recommendation: implement **A** as the main mechanism (tags + recursive resolve). Optionally use **B** in schema/docs only (no hardcoded paths in resolution logic).

### 3.5 Integration with Ansible

- **Vault password**: Prefer existing Ansible mechanisms (`vault_password_file` in ansible.cfg, or `ANSIBLE_VAULT_PASSWORD_FILE` / `ANSIBLE_VAULT_PASSWORD`). The plugin can use `ansible.constants` / `ansible.parsing.vault` when available, and only enable Ansible Vault resolution when a password is actually provided (no hardcoded path to a specific `.vault_pass.txt` in code).
- **ansible.cfg**: Document that users may set `vault_password_file` (or use env) for `!vault`; path should be project-appropriate and not commit the file (e.g. in `.gitignore`).
- **Schema validation**: Run validation either (1) on raw YAML and allow string or “secret ref” types for known secret fields, or (2) after resolution so validation sees only plain strings. (1) is simpler and keeps validation independent of vault availability.

### 3.6 Backward compatibility

- If no `!vault` (or other secret tag) is used and no vault password is configured, behavior stays as today: plain YAML, no resolution step.
- Existing configs without secrets remain valid. New secret support is opt-in via tags and optional vault password configuration.

---

## 4. Implementation Outline (for discussion)

1. **Secret resolver interface**  
   - Define a small module (e.g. under `ansible/plugins/inventory/`) with:
     - `SecretResolver` protocol or base: `resolve(value) -> str` (or identity if not a ref).
     - `resolve_config(config: dict) -> dict`: recursive walk; when a value is a “secret ref”, replace with `resolve(value)`.

2. **Ansible Vault backend**  
   - One resolver that uses `VaultLib` + password from Ansible constants/env.  
   - Register a custom YAML constructor for `!vault` that returns an object (e.g. `VaultEncrypted(str)`).  
   - In `resolve_config`, detect that type and call `VaultLib.decrypt()`.

3. **Config loading in the plugin**  
   - In `parse()`:
     - Open and load YAML with custom handling for quoted `!vault` (safe_load + resolve).  
     - Optionally run schema validation on the raw structure.  
     - Run `resolve_config(config)` to get a fully resolved dict.  
     - Build `self.configfiles` from this resolved dict (by section) instead of from `get_option()`.  
     - Call `_set_virtualization(path)` with the resolved config (or pass the dict) so virtualization detection uses the same data.  
   - Ensure `_populate_defaults()` and `_populate()` only see resolved config (they already use `self.configfiles`).

4. **Environment variables**  
   - Not implemented as a custom tag; use Ansible’s `lookup('env', 'VAR_NAME')` in playbooks or rely on default credential chain (e.g. `AWS_ACCESS_KEY_ID` for Terraform).

5. **Documentation and security**  
   - Document: how to use `!vault`, how to set vault password (file/env), that vault password file must not be committed.  
   - In docs, list typical secret keys (splunk_admin_password, idxc_password, etc.) for reference only, without hardcoding resolution paths.

6. **Tests**  
   - Unit tests: resolve_config with mock resolver; Ansible Vault resolver with a test vault password and encrypted string.  
   - Integration: inventory generation with a minimal `splunk_config.yml` containing one or two `!vault` values.

---

## 5. Open Points for Discussion

1. **Schema**: Validate before or after resolution? Allow “secret ref” type in schema or keep schema for structure only and treat secrets as strings?
2. **Default backend**: If `vault_password_file` is set, should we automatically enable Ansible Vault resolution, or require an explicit opt-in (e.g. a top-level `vault: ansible` in config)?
3. **Multiple backends**: Ship Ansible Vault only; env vars are handled by Ansible/playbooks.
4. **Vault password file path**: Keep it only in ansible.cfg (user responsibility) or allow override via env (e.g. `SPLUNK_VAULT_PASSWORD_FILE`) for the plugin?
5. **Error messages**: If decryption fails (wrong password, corrupted block), fail fast with a clear message and point to vault password configuration.

---

## 6. Summary

- **Problem**: Secrets in `splunk_config.yml` should not be stored in plain text; the old patch only decrypted in a dead code path and hardcoded every secret location.
- **Idea**: One config load, one resolution step with a pluggable “secret resolver,” and use only the resolved config everywhere. Rely on YAML tags (`!vault`, optionally `!env`) so any key can be a secret without hardcoding paths.
- **First step**: Ansible Vault as the primary backend; design the resolver interface so other backends (env, external vaults) can be added later without changing the plugin’s core flow.

This concept avoids hardcoded credentials in code (only resolution logic and documented env/file names), keeps the implementation open for multiple vault backends, and aligns with the existing use of `config/splunk_config.yml` and the inventory plugin.
