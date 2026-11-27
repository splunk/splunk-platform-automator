# Apps

Apps are part of `splunk_config.yml`. First-time install is `spa deploy`. After the lab is up, apply apps with `spa run splunk_apps_deploy --yes`. Use the live catalog for the schema and examples:

```bash
spa config explain splunk_app_deployment
spa config explain splunk_app_deployment.apps.customizations.remove
spa apps search QUERY
spa apps snippet APP_ID
```

Sources can be Splunkbase, a local app repository, or a configured URL. Pin versions for controlled environments. `spa apps download APP_ID --yes` downloads to `apps_dir`; `--extract` expands folder-backed apps. Download never edits config.

Splunkbase downloads need a Splunk.com account. Sign in at [https://splunkbase.splunk.com/](https://splunkbase.splunk.com/), then export `SPLUNKBASE_USERNAME` and `SPLUNKBASE_PASSWORD` in the shell. Report them as **set / not set**; never paste them in chat. YAML stays `lookup('env', ...)`. Local archives in `apps_dir` skip Splunkbase.

## HTTP Event Collector baseconfig

HEC is not a `splunk_app_deployment` row. Add a top-level `splunk_hec` identity and point a host at it with `hec:`, the same way `idxcluster` selects a cluster. The source folder under the PS tree is always `org_all_hec_inputs`. The installed dest name is `{splunk_app_prefix}_{idx|hf|sh|app_infix}_hec_inputs` (example `splk_idx_hec_inputs`), not `org_…`. A custom `app_infix` replaces `idx` / `hf` / `sh` on every host that selects that row. SPA updates `local/inputs.conf` in place like other baseconfig apps (comments from the PS file stay). The sample `[http://hec_input]` stanza is renamed when the input has another name. Every input needs `index`; when `indexes` is omitted, deploy writes `indexes` equal to `index`. Omit `token` to generate a UUID (`spa config add`, or at deploy when the conf has none). Other files the PS template ships stay as `install_app` copies them.

In an indexer cluster the cluster manager stages one dest app for every peer; in an SHC the deployer does the same. A deployment server stages one dest app per (`hec_name`, infix) pair and a server class whose whitelist is only those clients. Two `splunk_hec` rows whose DS clients share a role (for example two standalone indexers with different `hec:`) would share one app name, so `spa validate` asks for a distinct `app_infix` on each row. Combined indexer + search head (S1) installs once, as `idx`.

## Choose where an app goes

Normal apps require `target_roles`. SPA then selects the distribution mechanism from the target topology:

| Target | SPA stages the app on | Splunk distributes it with |
| --- | --- | --- |
| Deployment clients | Deployment server | Server class |
| Indexer cluster peers | Cluster manager | Indexer bundle |
| Search head cluster members | Deployer | SHC bundle |
| Standalone or explicit direct target | Target host | Direct install |

`deployment_target: direct` bypasses cluster or deployment-server routing. Use it deliberately: central distribution is normally safer for clustered tiers.

Schema uniqueness for `serverclass` follows the same table: only rows that would actually get a deployment-server serverclass are compared. With no deployment server, `auto` installs non-IDXC and non-SHC targets directly, so those rows have no serverclass and do not collide with each other on class name. Clustered indexer copies go through the cluster manager and clustered search-head copies through the deployer, so they do not collide with a UF serverclass of the same app name.

The app `name` must match the directory produced by the archive for folder-backed apps. Bundle-backed entries such as ITSI can contain several app directories; describe those through the premium-app shape from the catalog rather than guessing archive contents.

## Filter targets

- `hosts_whitelist` / `hosts_blacklist` select standalone search hosts. Cluster members must use cluster filters.
- `shc_whitelist` / `shc_blacklist` select named search head clusters.
- `idxc_whitelist` / `idxc_blacklist` select named indexer clusters.
- `sc_whitelist` / `sc_blacklist` directly control deployment-server server-class patterns.
- Premium apps may use either a host whitelist or SHC whitelist, not both; they do not support blacklists.

With no `sc_whitelist`, SPA calculates server-class clients from roles and filters. `deploymentclient_check: true` (default) confirms phone-home clients with `btool`; set it false only for bootstrap cases where the inventory-only heuristic is intentional. An empty target set skips deployment rather than widening it.

## Install, update, and remove

`state: present` installs or updates an entry; `state: absent` removes it through the same routing path. The default `update_mode: merge` preserves files not present in the new archive, including local customization. `clean` replaces the app directory. Backups are off by default; when `backup_apps_before_update` is enabled, the default location is `/tmp/splunk_app_backups`.

By default the controller downloads each Splunkbase archive once. `target_download: true` makes each target download it and therefore requires outbound Splunkbase access from those hosts.

After editing app config on an already-running lab:

```bash
spa apps add APP_ID --roles ROLE --yes
spa validate
spa hosts check
spa run splunk_apps_deploy --yes
```

First-time install is still `spa deploy --yes` (it creates hosts, installs Splunk, then imports the same apps playbook). Adding a host still uses `spa deploy`.

Limit a rollout with `--hosts`, but remember that cluster-managed apps are staged on their manager or deployer. The playbook needs root, so `spa hosts check` comes first. Confirm in chat, then `--yes`. Do not pass `-v`.

If `apps add 1841` returns Java 21 (`os.java.search_heads`), set that with `spa config set`, then `spa run setup_common --yes` before `splunk_apps_deploy`. OS follow-ups are not apps; do not fall back to full deploy just because ITSI was added.

`spa apps remove` does not uninstall files already on hosts. Uninstall is `state: absent` plus `spa run splunk_apps_remove` (or the same apps playbook).

On CCM, adding apps on a live lab is this `spa run` path. Adding hosts still does not work on a live CCM deployment.

`spa apps add --help` separates the four legal forms: a normal app requires
`--roles`; ITSI 1841 rejects roles; Content Library 5391 requires named packs
or the all-packs policy; and a recognized independently published pack uses
its own app ID. The help also documents local lookup, strict-JSON `--set`,
curated customization, dry-run, revision checks, dependency resolution, and
confirmation. `apps add` only edits config—it never runs deploy.

## Customize an app

Per-app `customizations` can remove files, write `local/` configuration, update index paths, or invoke a task file or role. The same app can appear more than once with different roles and customizations.

Execution is: extract, remove files, write local config, update indexes, run `run_playbook` or `run_role`, then notify the appropriate restart/reload/bundle handler. `run_playbook_after_restart` runs in a follow-up play and is supported for direct deployment. A custom task that changes content must set `update_needed: true` so SPA triggers the handler.

Force controls are exceptional:

- `force_local_configs`
- `force_run_playbook`
- `force_run_playbook_after_restart`
- `force_install` for ITSI and ITSI content packs

Remove force flags after the corrective run or every later deploy will repeat the work.

Curated task files under `ansible/apps_playbooks/` declare `# spa-app:` metadata. `spa apps snippet` advertises matching customizations. Inspect or rerun one without a full deploy:

```bash
spa run splunk_apps_playbook_run --help
spa run splunk_apps_playbook_run --apps-playbook STEM --hosts ROLE --yes
```

Environment-local task files can be addressed by an env-relative path configured for `spa run`.

## ITSI and content packs

Use the catalog instead of hand-building premium YAML:

```bash
spa config explain splunk_app_deployment.apps.app_id
spa config explain splunk_app_deployment.apps.content_pack_apps
spa apps content-packs list 5391
```

ITSI defaults to Splunkbase app ID 1841. Premium targets are determined by the premium role, not `target_roles`. Content-pack archives may be single-app, explicitly list `content_pack_apps`, or use `install_all_apps`. Listed packs are registered through the ITSI API unless `content_pack_install: false`.

The Content Library's Splunkbase page describes app 5391 but does not list the
pack folders bundled in each release. `content-packs list` inspects the selected
archive and reports each exact `DA-ITSI-CP-*` folder, its app label,
description and version when present, and any matching SPA post-install
automation. It first uses `--archive`, then a matching archive in `apps_dir`. Otherwise it uses an install archive already at `splunk_app_deployment.temp_dir` (default `/tmp/splunk_apps/content_pack_<app name>/content_pack_<app name>_<version>.tgz`, where the app name is the 5391 entry or `DA-ITSI-ContentLibrary`) and leaves that file in place. If that archive is absent, it reads cached `DA-ITSI-CP-*/default/app.conf` files under `content_pack_app_confs/<version>`. The stored cache also keeps the library folder and applies the same archive limits as a direct inspection. `--version` selects that release and must be a single version name; the default `latest` checks Splunkbase and replaces the `app.conf` cache when a newer release is current. An archive this command downloads is not kept. A download prints a notice before it starts. Inspect a file directly, without an environment or
credentials, with:

```bash
spa apps content-packs list 5391 --archive /path/to/content-library.tgz
```

Each row prints its `spa apps add 5391 --content-pack NAME --yes` command.
Use `--install-all-content-packs` instead when every bundled pack is intended.
An independently published single-pack app has its own Splunkbase app ID and
is added by that ID; it is not a `--content-pack` name under 5391.

For an SHC, SPA waits for service readiness and any rolling restart before content-pack API and post-restart work. API/config tasks run once on the first SHC member. A 404 from the installed check or install endpoint is reported and processing continues because endpoint behavior differs across ITSI versions.

## Enterprise Security

Use the catalog instead of hand-building premium YAML:

```bash
spa config explain splunk_app_deployment.apps.ssl_enablement
spa apps snippet 263
spa apps add 263 --yes
```

ES is Splunkbase app ID 263 (`premium_app: es`). Premium targets come from the premium role, not `target_roles`. `spa apps add 263` writes that shape and rejects `--roles`. Pair Enterprise plus ES license files and a `license_manager` role. Java 21 is ITSI-only; do not add it for ES.

Install is `splunk install app` plus `| essinstall` (search head, or `--deployment_type shc_deployer` on the SHC deployer). Do not skip `essinstall`. CIM comes from the ES bundle; do **not** add Splunkbase CIM (`1603`) as a sibling row.

`spa apps add 263` omits `version:` (schema default `latest`; `spa apps snippet 263` writes the same shape). Leave `version: latest` (or omit the key) and `spa deploy --yes` upgrades ES with `splunk install app -update 1` then `| essinstall`. Raise a pinned `version:` the same way; a pin does not move until the operator changes it. Each `| essinstall` refreshes the SPA stamp, so `spa run verification/verify_es` after an upgrade only reports installer ERRORs from that upgrade run.

Pin ES to a dedicated search head or a dedicated SHC in one site. Do not install ES on a stretched SHC (members with more than one distinct `site`). ES targets exactly one search tier (one SHC **or** one standalone search head) and one indexer layer (one IDXC **or** one standalone indexer). When both an SHC and a standalone search head exist, set exactly one of `hosts_whitelist` or `shc_whitelist`.

`essinstall` defaults to `ssl_enablement=strict`, which fails when Splunk Web SSL is off. If `splunk_ssl.web.enable` is on for the ES search head, omit the flag (strict). Otherwise SPA passes `--ssl_enablement ignore`. Optional app key `ssl_enablement: ignore|strict|auto`; `auto` is invalid when the target is an SHC.

SPA-owned apps:

- `spa_es_indexes` — ES index definitions on the cluster manager (`etc/manager-apps`) or standalone indexer (`etc/apps`). Removal deletes this app only; it never touches index data.
- `spa_es_shc_limits` — deployer copy of the SHC upload limit. Members also get `max_content_length` in `etc/system/local/server.conf`, because a bundle-delivered `[httpServer]` setting does not take effect.

Bundled `TA-*` apps and **Splunk_TA_ForIndexers** are follow-ons, not part of `premium_app: es`. Extra TAs stay normal `target_roles` apps. The lab file and CCM ES topologies include Splunk_TA_nix (833), Splunk_TA_windows (742), Splunk_TA_cisco-asa (1620), Splunk_TA_microsoft_sysmon (5709), and Splunk_TA_paloalto_networks (7523) on the ES search head. ESCU / content updates are also out of this feature; install them later as a normal app pinned to the ES search head.

Production ES wants 16 CPU / 32 GB. A single-node lab is a compromise. For a full lab copy or merge [examples/single_node_es.yml](../examples/single_node_es.yml); that file is not a spa init --example topology.

To convert a legacy `app_id: 263` row that still has `target_roles`, remove it and add it as premium:

```bash
spa apps remove 263 --yes
spa apps add 263 --yes
```

Or edit the existing row with `spa config set` / `spa config unset` so it has `premium_app: es` and no `target_roles`. Do not hand-edit `splunk_config.yml`. There is no silent migration.

## Verify and troubleshoot

```bash
spa run verification/verify_app_deployment --help
spa run verification/verify_es --help
spa run verification/debug_app_scope --help
```

Verification checks expected presence and version where credentials/source metadata allow it. Strict CI can pass `-e fail_on_mismatch=true` after `--`. Scope debugging shows routing before hosts are changed.

When an app goes to the wrong place, check `target_roles`, cluster membership, `deployment_target`, and filters in that order. When a bundle does not move, inspect the manager/deployer handler output and cluster health. Use Splunk's administration documentation for bundle and server-class internals; SPA owns only the mapping above.

Contributors: app-scope scenarios and test commands are in [tests/README.md](../tests/README.md).
