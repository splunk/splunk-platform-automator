# Apps

Apps are part of `splunk_config.yml` and are reconciled by `spa deploy`. Use the live catalog for the schema and examples:

```bash
spa features show setting.apps --keys
spa features show setting.apps.customizations --keys
spa apps search QUERY
spa apps snippet APP_ID
```

Sources can be Splunkbase, a local app repository, or a configured URL. Pin versions for controlled environments. `spa apps download APP_ID --yes` downloads to `apps_dir`; `--extract` expands folder-backed apps. Download never edits config.

## Choose where an app goes

Normal apps require `target_roles`. SPA then selects the distribution mechanism from the target topology:

| Target | SPA stages the app on | Splunk distributes it with |
| --- | --- | --- |
| Deployment clients | Deployment server | Server class |
| Indexer cluster peers | Cluster manager | Indexer bundle |
| Search head cluster members | Deployer | SHC bundle |
| Standalone or explicit direct target | Target host | Direct install |

`deployment_target: direct` bypasses cluster or deployment-server routing. Use it deliberately: central distribution is normally safer for clustered tiers.

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

After editing app config:

```bash
spa validate
spa deploy --yes
```

Limit a rollout with `--hosts`, but remember that cluster-managed apps are staged on their manager or deployer.

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
spa features show setting.apps.premium.itsi --keys
spa features show setting.apps.premium.itsi.content_pack --keys
```

ITSI defaults to Splunkbase app ID 1841. Premium targets are determined by the premium role, not `target_roles`. Content-pack archives may be single-app, explicitly list `content_pack_apps`, or use `install_all_apps`. Listed packs are registered through the ITSI API unless `content_pack_install: false`.

For an SHC, SPA waits for service readiness and any rolling restart before content-pack API and post-restart work. API/config tasks run once on the first SHC member. A 404 from the installed check or install endpoint is reported and processing continues because endpoint behavior differs across ITSI versions.

## Verify and troubleshoot

```bash
spa run verification/verify_app_deployment --help
spa run verification/debug_app_scope --help
```

Verification checks expected presence and version where credentials/source metadata allow it. Strict CI can pass `-e fail_on_mismatch=true` after `--`. Scope debugging shows routing before hosts are changed.

When an app goes to the wrong place, check `target_roles`, cluster membership, `deployment_target`, and filters in that order. When a bundle does not move, inspect the manager/deployer handler output and cluster health. Use Splunk's administration documentation for bundle and server-class internals; SPA owns only the mapping above.

Contributors: app-scope scenarios and test commands are in [tests/README.md](../tests/README.md).
