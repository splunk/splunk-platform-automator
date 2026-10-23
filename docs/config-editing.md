# Configuration editing contract

This document is the normative contributor contract for commands that read or
change `config/splunk_config.yml`. Operator syntax is generated in
[commands.md](commands.md), and schema fields are generated in
[config.md](config.md). Catalog snippets are examples; no editing command
applies them implicitly. A copy-paste operator example is in
[config-walkthrough.md](config-walkthrough.md); it is not part of this contract.

Every behavior change in this document follows
[test-driven development](architecture.md#test-driven-development), updates its
contract ID and mapped test in the same change, and passes the
[feature completion review](architecture.md#feature-completion-review).

## Command and agent contract

### CFG-CLI-001 — command ownership

`spa config` has one parser per action: `explain`, `search`, `get`,
`templates`, `keys`, `schema`, `set`, `add`, `unset`, `merge`, `topology`,
and `provider`. `explain` and `search` are the schema walk. `templates` is
the read-only shipped fragment catalog. `keys` is the maintainer coverage
check. `schema --markdown` is the human settings dump. `spa config add`
appends one non-app identity-list entry. `spa apps` owns app and content-pack
entries; there is no `spa config app`. Operators and agents call `bin/spa`
and never import `spa.api`.

### CFG-CLI-002 — result and status contract

Usage errors exit 2. Runtime, validation, and transaction failures exit 1.
Success exits 0. Agent mode emits one compact JSON object. Agent failures have
`ok`, `schema_version`, and `error`, and no `data`. Successful mutations report
`changed`, revisions, redacted operations, warnings, omitted defaults, and
validation readiness; they never include the configuration body or rendered
snippets.

### CFG-CLI-003 — confirmation boundary

Humans are prompted before every write unless `--yes` is present. `--dry-run`
never prompts. Agent-mode config edits and `apps add` or `apps remove` are
idempotent and may write without `--yes`; `--yes` remains accepted. Provision,
deploy, destroy, suspend, resume, environment removal, venv rebuild or
reinstall, skill removal, app download, and mutating, destructive, or
unspecified-risk playbooks still require `--yes` in agent mode.

### CFG-CLI-004 — bounded discovery

Agent mode is selected by `--agent`, `--json`, or the established agent
environment variables; `--no-agent` overrides detection. Pathless agent
`config get` returns only the revision, top-level keys, and object identities.
`--full` is explicit. `spa config explain` and `spa config search` return the
same structure to a human page, an agent, and a future GUI. They do not apply
a snippet or a value.

## Paths, values, and reads

### CFG-PATH-001 — schema-aware values

`config set` accepts `PATH VALUE`. Strings preserve their text. Boolean,
integer, number, null, list, and map values use strict JSON of the schema type.
`--value-file` accepts JSON or YAML 1.2. Missing mapping parents may be created,
but catalog paths that are not schema-backed are rejected.

### CFG-PATH-002 — stable selectors

Mutations select list items by stable identity, never by numeric index:
indexer clusters by `idxc_name`, search-head clusters by `shc_name`, hosts by
`name` or `iter.prefix`, environments by `splunk_env_name`, and apps by
`app_id` or by `name` for local apps. Bare `[]`, zero matches, and multiple
matches are errors for `config set` and `config unset`. `config add` is the
command that creates a missing identity.

### CFG-PATH-003 — exact assignment

`config set` replaces exactly the selected scalar, mapping, or list. It does
not deep-merge the supplied value, does not create a missing identity, and
does not read a catalog snippet. Existing unrelated paths remain unchanged.

### CFG-PATH-004 — explicit removal

`config unset` removes only the named leaf, mapping, or selected item. A missing
path is an error. It cleans empty parents created solely for that leaf but
does not remove required roots or unrelated siblings. Unset is how authored
state returns to a schema default.

### CFG-PATH-005 — authored and effective reads

`config get PATH` distinguishes `explicit`, `schema_default`, and `unset`, with
separate authored and effective values. `--effective` reports an omit-safe
schema default when the path is absent. Human output is YAML; agent output uses
the normal envelope and includes the current content revision.

### CFG-PATH-006 — omit-safe defaults

An explicit assignment equal to a published schema default is omitted with a
warning and recorded in `omitted_defaults`. `--explicit-default` authors it.
An already-authored default is not removed by an unrelated command.

### CFG-PATH-007 — secret builders

A secret path rejects positional plaintext. `--from-env NAME` validates the
environment-variable name and authors an Ansible environment lookup. Reads
report only set or not set and never resolve the lookup.

## Identity append

### CFG-ADD-001 — new identity

`config add SELECTOR JSON_OBJECT` appends one entry to a non-app identity
list such as `splunk_hosts`, `splunk_idxclusters`, or `splunk_shclusters`.
The selector supplies the identity and writes that key into the object.
On `splunk_hosts`, `name`, `list`, or `iter` is written first.
`--value-file` accepts a JSON or YAML 1.2 object. The same transaction
supports dry-run, revision checks, dependency resolution, and confirmation.
`config set` remains an update of an existing path.

### CFG-ADD-002 — collision and selector rejection

An identity that already matches is an error, and the file is unchanged.
A selector value that disagrees with the same key in the object is an error.
Bare `[]`, a path that is not an identity list, and an identity key the list
does not use are errors. None of these write.

### CFG-ADD-003 — app ownership

App and content-pack list entries are rejected with `App entries use spa apps add`.
`config add` does not create or update those entries.

### CFG-ADD-004 — secret children

A secret field inside the new object rejects positional plaintext. Repeatable
`--from-env FIELD NAME` authors an Ansible environment lookup for that field
before the variable exists. `--from-env` on a field that is not a secret is
an error. Reads, diffs, and errors do not echo the secret value.

### CFG-ADD-005 — one feature command

Every configurable catalog feature produces exactly one command:
`spa config set` for a scalar or map, `spa config add` for a non-app
identity-list entry, `spa config topology` or `spa config provider` for a
layout, and `spa apps add` for an app record. Unsupported records stay
non-configurable and have no command. `spa config explain` prints that one
command for the selected node and does not apply it.

### CFG-CLI-005 — one-level explain

`spa config explain [PATH]` describes one node: its description, `WHEN` and
`WHEN NOT` when the catalog has that decision, then immediate identity forms
and shared fields. Host `name`, `list`, and `iter` are mutually exclusive.
`roles`, `os`, `terraform`, and the other host fields are shared. A deeper
level is a longer path. User paths omit empty `[]`. Mutation selectors still
use `splunk_hosts[name=NAME]`. When a setting exists both globally and on a
host, the selected node includes `SCOPE` with the other path. `os`,
`virtualbox`, `terraform`, and `custom` have host forms. Flattened
`splunk_defaults` fields such as `splunk_version` point at
`splunk_hosts.splunk_version`. List values under `os` and `custom` are added
to the global list. Other paired values replace the global value for that
host. A setting with no counterpart omits `SCOPE`. An immediate field line
names the other path in one clause. The selected node may include one command
and one example. Secrets use `--from-env` and have no literal example. Agent
JSON is that structure with empty values omitted. `schema --markdown` is
rejected in agent mode.

### CFG-CLI-006 — path search

`spa config search QUERY` returns paths and a one-line description. It does
not return a command. When a counterpart exists, that line says `All hosts`
or `Per-host` and names the other path. Agent results contain at most 10
matches plus `total_matches` and `truncated`.

## Fragment merge

### CFG-MERGE-001 — fragment sources

`config merge TEMPLATE` reads a shipped `examples/templates/TEMPLATE.yml`.
A local fragment is only `config merge --file FILE`, and stdin is
`config merge --file -`. A path in the template position is an error that
names `--file`. Passing a template and `--file` together is an error. Stdin
is limited to 1 MiB and files to 8 MiB. YAML uses YAML 1.2 round-trip parsing,
preserves strings such as `yes`, and rejects duplicate keys.

### CFG-MERGE-002 — mappings, scalars, and null

Mappings merge recursively. Current keys omitted by the fragment remain.
Fragment scalars replace current scalars. A null fragment value is skipped with
a warning; deletion requires `config unset`.

### CFG-MERGE-003 — identity lists

Known object lists merge by identity. A matching object merges recursively and
a new identity appends. An object missing the required identity is an error.
This covers hosts, clusters, environments, apps, VirtualBox synced folders by
`target`, and ITSI content-pack apps by `name` or `app_id`.

### CFG-MERGE-004 — additive lists

All other lists merge additively at their exact path. Existing order is kept,
then deeply unequal fragment values append. A scalar merged with a list of
scalars becomes that list, with the scalar kept in its original position.
Scalar equality is typed and exact.
This applies at global, provider, host, app, and arbitrary `custom` depth,
including host roles, packages, SSH keys, security groups, app roles and
filters, and license files. Global values are not copied into host overrides.
An empty fragment list removes nothing.

### CFG-MERGE-005 — unknown structured lists

For a structured list under an extra-allowed provider or `custom` key with no
declared identity, SPA does not guess an identity. It retains current items and
appends only fragment items that are not deeply equal. `config set` is the
explicit replacement and reorder operation.

### CFG-MERGE-006 — merge boundaries

`plugin`, when supplied, must equal `splunk-platform-automator`. A fragment
cannot switch topology or provider and never deletes omitted state. Fragment
comments are not copied. Existing document comments, quotes, and nested order
survive. Reapplying the same fragment is a no-op and does not rewrite the file.

## Transaction

### CFG-TXN-001 — lock and revision

Every mutation and dry-run acquires the same exclusive config lock, reads the
bytes once, and computes their SHA-256 revision. A mismatched
`--expect-revision` returns a conflict before evaluating the requested change.

### CFG-TXN-002 — one candidate

The requested operation, resolution values, deterministic dependency repairs,
canonical ordering, serialization, and Pydantic validation form one in-memory
candidate. No stage writes a partial candidate.

### CFG-TXN-003 — faithful dry-run

Dry-run and write use the same pipeline and produce the same structured
operation plan and redacted unified diff. Dry-run stops before replacement.
Human and agent output never exposes a secret value.

### CFG-TXN-004 — atomicity and rollback

SPA serializes to a sibling temporary file, validates it, preserves the target
mode, and replaces the target with `os.replace`. It refuses a symlink target.
Any failure removes the temporary file and leaves the original bytes unchanged.

### CFG-TXN-005 — idempotence

If authored state already equals the desired result, the command returns
success with `changed: false`, keeps the same revision, and does not rewrite the
file.

## Dependency closure

### CFG-DEP-001 — one declarative rule source

Cross-section dependency rules live beside the Pydantic models. One rule
definition supplies a stable ID, trigger, normalized facts, deterministic
repair, unresolved requirement, and final validation error. The planner and
Pydantic validation do not maintain separate dependency lists.

### CFG-DEP-002 — safe closure

The planner repeatedly applies only deterministic repairs until reaching a
fixpoint. It may link a manager or deployer to the sole existing compatible
cluster or scaffold a cluster identity explicitly named by the caller. It does
not invent hosts, topology, identities, placement, license paths, or external
resources. Cycles terminate as unresolved requirements.

### CFG-DEP-003 — unresolved result

Unresolved input is a successful, non-writing result with `ready: false` and
`changed: false`. Requirements carry rule ID, kind (`choice`, `value`,
`external_resource`, or `cardinality`), affected paths, safe summary, available
identities when applicable, and retry guidance. Deterministic repairs remain
planned only until every requirement is resolved.

### CFG-DEP-004 — resolution retry

Every mutation accepts repeatable `--resolve PATH VALUE` and
`--resolve-file FILE`. Resolutions use the same parsing, selectors, merge, and
secret rules and join the original operation in one transaction. Stdin is not
shared by both `--file -` and `--resolve-file -`.

### CFG-DEP-005 — topology cardinality

Member minimums and manager or deployer requirements are evaluated per named
cluster, not as totals across clusters. `name`, `list`, and `iter` host forms
produce equivalent normalized member counts. Explicitly documented
external-topology exceptions remain valid.

## Layout and serialization

### CFG-LAYOUT-001 — canonical root order

Writes order roots as: plugin; general and custom; OS; providers; indexer and
search-head clustering; defaults, directories, systemd, and environments;
hosts; apps. Unknown roots follow in their existing relative order. Nested
mapping and list order is not canonicalized.

### CFG-LAYOUT-002 — template resolution

Topology and provider feature IDs resolve through their catalog `template`
field. Example stems resolve through the same example resolver used by
`spa init`. Layout commands load those files and never consume snippets.

### CFG-LAYOUT-003 — topology replacement

`config topology` replaces hosts and replaces or removes cluster and
environment roots owned by the selected topology. It preserves provider, OS,
general, custom, defaults, and apps. Comment-only null defaults in a topology
do not erase authored defaults.

### CFG-LAYOUT-004 — provider replacement

`config provider aws` replaces Terraform provider configuration and removes
VirtualBox configuration. Selecting VirtualBox does the reverse. It preserves
all non-provider sections.

### CFG-LAYOUT-005 — compact clustered hosts

Cluster member ranges use `iter` with `prefix` and `numbers: 1..N`.
Singleton managers, standalone search heads, deployment servers, heavy
forwarders, and universal forwarders use `name`.

### CFG-LAYOUT-006 — blank-line separation

Blank lines are write formatting. `spa config` and `spa apps` insert one blank
line between top-level sections, and one blank line between entries of a
top-level list such as hosts, clusters, environments, and apps. `spa init`
uses the same formatting when it writes a new file. Comments directly above an
entry stay with it. Scalar lists such as `roles` and lists nested inside an
entry stay compact.

Schema validation, `spa validate`, inventory, provision, and deploy do not
read or require this spacing. A file with the blank lines removed, with extra
blank lines, or with added comments stays valid and is left unchanged until a
write command edits it.

## Applications

### CFG-APP-001 — one structured entry builder

App lookup and classification produce one structured entry shared by
`apps snippet` and `apps add`. Snippet renders that structure; add never parses
rendered YAML. App 5403 remains refused and directs the operator to ITSI 1841.

### CFG-APP-002 — app defaults and credentials

Omitted app `source` means `splunkbase` in schema and Ansible. Generated entries
omit `source: splunkbase`, `version: latest`, `state: installed`,
`deployment_target: auto`, and `update_mode: merge` unless an explicit-default
option applies. Local source stays explicit. The first Splunkbase app adds
environment lookup references for absent Splunkbase credentials without
overwriting or printing existing values.

### CFG-APP-003 — idempotent upsert and removal

Add upserts by `app_id`, or by `name` for a local app without an ID. Unspecified
fields on a matching app remain. An identical add is a no-op. Remove deletes
only authored configuration and states that deployed software is not
uninstalled.

### CFG-APP-004 — fields and filters

`--roles` supplies normal-app `target_roles`. Repeatable `--set FIELD VALUE`
accepts any other schema-backed app field, including nested values and all host
and cluster filters. It is exact replacement, not fragment merge. Classification
fields (`name`, `app_id`, and `premium_app`) and a field already owned by a
dedicated flag are rejected.

### CFG-APP-005 — app kinds

Normal apps require roles. ITSI 1841 writes `premium_app: itsi` and rejects
roles. A recognized single content pack writes `itsi_content_pack` and
`content_pack_api`, has no target roles, and does not use
`content_pack_apps`.

### CFG-APP-006 — content library policy

Content Library 5391 requires exactly one policy: install all packs or one or
more named packs. The policies are mutually exclusive and invalid for other
app kinds. Named packs append idempotently. An existing library cannot be
silently switched to the other policy. Removing one named pack leaves the
library and ITSI entries.

### CFG-APP-007 — deterministic ITSI dependency

Adding a content pack may add missing ITSI app 1841 in the same candidate.
Closure then reports unresolved search-head, indexer, license-manager,
license-file, or Java requirements instead of inventing them. Existing ITSI
configuration remains unchanged.

### CFG-APP-009 — singular ITSI search tier

An installed ITSI app resolves to exactly one search tier. One SHC with no
standalone search head, or one standalone search head with no SHC, needs no
filter. Multiple SHCs, multiple standalone search heads, or a mixture requires
`shc_whitelist` naming one existing SHC or `hosts_whitelist` naming one existing
standalone search head. A filter that still selects more than one placement
domain is invalid. `state: absent` is exempt. The dependency planner reports
`itsi.search_tier` with the legal identities and an exact `--resolve` retry,
and the transaction preserves the original file until that retry succeeds.

### CFG-APP-008 — command boundaries

Add and remove use the config transaction and support dry-run, revision checks,
and confirmation. Snippet and search remain read-only and snippet remains
usable without an initialized environment. App download retains its existing
confirmation requirement and writes only the app repository.

### CFG-APP-010 — content-pack discovery and add guidance

`spa apps content-packs list 5391` treats the selected Content Library archive
as authoritative. It reads bounded `DA-ITSI-CP-*/default/app.conf` members
without extracting the archive, then returns exact folder names,
label/description/version metadata, matching curated SPA automation, and one
legal add command per pack. `--archive` needs no environment. Otherwise SPA
uses the matching archive in `apps_dir` or a temporary authenticated download.
Unsafe, malformed, excessive, or empty archives fail without writing files or
printing credentials. `spa apps add --help` describes every option and the
normal-app, ITSI, Content Library, and independently published pack forms; it
states that add edits config and does not deploy.

## Security

### CFG-SEC-001 — secret containment

Secret values in config mutations are references from validated environment
builders or a supported quoted vault reference. Literal secret values in
fragments fail without echo. Logs, errors, operations, diffs, reads, examples,
and agent envelopes never contain credential values, private keys, or
decrypted vault text.

### CFG-SEC-003 — required environment references

An explicit `{{ lookup('env', 'NAME') }}` requires `NAME` to be set to a
non-empty value before `spa validate`, `spa provision`, or `spa deploy`. Missing
and empty variables fail together, before inventory, confirmation, or provider
work. The error lists variable names and says to export each variable to a
non-empty value and rerun the command. It never includes the variable values.
`spa init` prints the same names as `set` or `not set` and still succeeds.
Omitting a password field can retain its schema default. A literal value in an
existing config remains valid. `spa config set --from-env` may author a
reference before the variable exists.

### CFG-SEC-002 — safe documentation

Examples and generated help contain no password, token, private key,
certificate, or other credential. If certificate files are ever introduced,
their expiration, validity start, public-key strength, signature algorithm,
and self-signed status must be verified before deployment.

## Verification index

Each contract ID maps to executable behavioral evidence:

- `CFG-CLI-001`: `tests/test_config_contract.py::TestCommandContract::test_bare_config_is_usage_error`
- `CFG-CLI-002`: `tests/test_config_contract.py::TestCommandContract::test_agent_set_writes_without_yes_and_returns_compact_envelope`
- `CFG-CLI-003`: `tests/test_config_contract.py::TestCommandContract::test_agent_set_writes_without_yes_and_returns_compact_envelope`
- `CFG-CLI-004`: `tests/test_config_contract.py::TestCommandContract::test_agent_get_without_path_is_outline_not_document`
- `CFG-CLI-005`: `tests/test_config_contract.py::TestExplainContract::test_explain_is_one_level_for_humans_and_agents`
- `CFG-CLI-006`: `tests/test_config_contract.py::TestExplainContract::test_search_returns_paths_without_commands`
- `CFG-PATH-001`: `tests/test_config_contract.py::TestPathContract::test_set_requires_strict_json_for_list`
- `CFG-PATH-002`: `tests/test_config_contract.py::TestPathContract::test_bare_or_missing_selector_is_rejected_without_write`
- `CFG-PATH-003`: `tests/test_config_contract.py::TestPathContract::test_set_preserves_comments_and_changes_only_the_path`
- `CFG-PATH-004`: `tests/test_config_contract.py::TestPathContract::test_unset_selected_item_removes_only_that_item`
- `CFG-PATH-005`: `tests/test_config_contract.py::TestPathContract::test_selector_get_set_and_unset_use_stable_identity`
- `CFG-PATH-006`: `tests/test_config_contract.py::TestPathContract::test_schema_default_is_omitted_unless_explicit`
- `CFG-PATH-007`: `tests/test_config_contract.py::TestPathContract::test_from_env_authors_lookup_and_get_redacts_secret`
- `CFG-ADD-001`: `tests/test_config_contract.py::TestAddContract::test_add_appends_a_new_identity_and_injects_the_selector`
- `CFG-ADD-002`: `tests/test_config_contract.py::TestAddContract::test_add_rejects_collisions_mismatches_and_bare_selectors`
- `CFG-ADD-003`: `tests/test_config_contract.py::TestAddContract::test_add_refuses_app_entries`
- `CFG-ADD-004`: `tests/test_config_contract.py::TestAddContract::test_add_secret_fields_require_an_environment_lookup`
- `CFG-ADD-005`: `tests/test_config_contract.py::TestAddContract::test_every_configurable_feature_has_one_command`
- `CFG-MERGE-001`: `tests/test_config_contract.py::TestMergeContract::test_merge_yaml_12_keeps_yes_as_string_and_json_works`
- `CFG-MERGE-002`: `tests/test_config_contract.py::TestMergeContract::test_merge_skips_null_and_is_idempotent`
- `CFG-MERGE-003`: `tests/test_config_contract.py::TestMergeContract::test_merge_nested_content_pack_items_by_identity`
- `CFG-MERGE-004`: `tests/test_config_contract.py::TestMergeContract::test_merge_unions_lists_in_provider_host_app_and_custom_scopes`
- `CFG-MERGE-005`: `tests/test_config_contract.py::TestMergeContract::test_merge_unions_lists_in_provider_host_app_and_custom_scopes`
- `CFG-MERGE-006`: `tests/test_config_contract.py::TestMergeContract::test_merge_omits_defaults_and_fragment_comments`
- `CFG-TXN-001`: `tests/test_config_contract.py::TestTransactionContract::test_lock_serializes_write_and_dry_run`
- `CFG-TXN-002`: `tests/test_config_contract.py::TestTransactionContract::test_validation_fault_cleans_temp_and_preserves_mode`
- `CFG-TXN-003`: `tests/test_config_contract.py::TestTransactionContract::test_dry_run_and_write_have_identical_operations`
- `CFG-TXN-004`: `tests/test_config_contract.py::TestTransactionContract::test_validation_fault_cleans_temp_and_preserves_mode`
- `CFG-TXN-005`: `tests/test_config_contract.py::TestMergeContract::test_merge_skips_null_and_is_idempotent`
- `CFG-DEP-001`: `tests/test_config_contract.py::TestDependencyContract::test_declarative_rule_registry_has_stable_unique_ids`
- `CFG-DEP-002`: `tests/test_config_contract.py::TestDependencyContract::test_dependency_planner_reaches_fixpoint_after_scaffolding_cluster`
- `CFG-DEP-003`: `tests/test_config_contract.py::TestCommandContract::test_human_unresolved_edit_prints_requirements_and_no_write`
- `CFG-DEP-004`: `tests/test_config_contract.py::TestDependencyContract::test_inline_resolution_refuses_literal_secret`
- `CFG-DEP-005`: `tests/test_config_contract.py::TestDependencyContract::test_final_validation_enforces_member_minimum_per_cluster`
- `CFG-LAYOUT-001`: `tests/test_config_contract.py::TestLayoutContract::test_canonical_order_puts_clustering_before_defaults`
- `CFG-LAYOUT-002`: `tests/test_config_contract.py::TestLayoutContract::test_layout_feature_ids_resolve_through_template`
- `CFG-LAYOUT-003`: `tests/test_config_contract.py::TestLayoutContract::test_topology_switch_replaces_owned_sections_and_keeps_defaults`
- `CFG-LAYOUT-004`: `tests/test_config_contract.py::TestLayoutContract::test_provider_switch_replaces_only_provider_sections`
- `CFG-LAYOUT-005`: `tests/test_config_contract.py::TestLayoutContract::test_all_clustered_topology_examples_use_iter_for_member_ranges`
- `CFG-LAYOUT-006`: `tests/test_config_contract.py::TestLayoutContract::test_written_config_separates_sections_and_list_items`
- `CFG-APP-001`: `tests/test_config_contract.py::TestAppContract::test_builder_omits_splunkbase_defaults_and_requires_ta_roles`
- `CFG-APP-002`: `tests/test_config_contract.py::TestAppContract::test_app_add_upserts_credentials_and_is_idempotent`
- `CFG-APP-003`: `tests/test_config_contract.py::TestAppContract::test_app_add_upserts_credentials_and_is_idempotent`
- `CFG-APP-004`: `tests/test_config_contract.py::TestAppContract::test_snippet_and_add_share_typed_schema_backed_set_fields`
- `CFG-APP-005`: `tests/test_config_contract.py::TestAppContract::test_builder_omits_splunkbase_defaults_and_requires_ta_roles`
- `CFG-APP-006`: `tests/test_config_contract.py::TestAppContract::test_content_pack_adds_itsi_dependency_and_remove_pack_keeps_itsi`
- `CFG-APP-007`: `tests/test_config_contract.py::TestAppContract::test_content_pack_adds_itsi_dependency_and_remove_pack_keeps_itsi`
- `CFG-APP-008`: `tests/test_config_contract.py::TestAppContract::test_app_add_and_remove_use_transaction_controls`
- `CFG-APP-009`: `tests/test_config_contract.py::TestDependencyContract::test_ambiguous_itsi_search_tier_preserves_bytes_until_one_filter`
- `CFG-APP-010`: `tests/test_config_contract.py::TestAppContract::test_content_pack_discovery_and_add_help_are_actionable`
- `CFG-SEC-001`: `tests/test_config_contract.py::TestPathContract::test_from_env_authors_lookup_and_get_redacts_secret`
- `CFG-SEC-002`: `tests/test_config_contract.py::TestSecurityContract::test_catalog_and_documentation_examples_are_credential_and_certificate_safe`
- `CFG-SEC-003`: `tests/test_config_contract.py::TestSecurityContract::test_explicit_env_lookup_requires_a_non_empty_value`
