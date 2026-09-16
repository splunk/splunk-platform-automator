# Basic apps questionnaire

**No Splunkbase catalog search** — user supplies `app_id` and folder `name` from Splunkbase. Merge YAML from `spa --json features show ID`.

Deep customization: [docs/App_Deployment_Customizations.md](docs/App_Deployment_Customizations.md) and `spa --json features show setting.apps.customizations`.

## 1. Deploy apps?

If no → omit `splunk_app_deployment` entirely.

## 2. Credentials

Prefer environment variables on controller — see [secrets-handling.md](secrets-handling.md):

- `SPLUNKBASE_USERNAME` — **set / not set** only in chat; never display the value
- `SPLUNKBASE_PASSWORD` — **set / not set** only in chat; never display the value

In `splunk_config.yml` use lookups only (never hardcode):

```yaml
splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
```

See [docs/App_Deployment.md](docs/App_Deployment.md). Optional vault in config. Do not verify with `echo $SPLUNKBASE_*`.

## 3. App sources

- `splunkbase` — requires credentials and `app_id`
- `local` — `path` to tarball/spl on controller apps dir

## 4. Target roles

For **normal** apps, `target_roles`: `search_head`, `indexer`, `universal_forwarder`, `heavy_forwarder` (maps to deployer/CM/DS/direct per SPA).

Do **not** set `target_roles` on `premium_app: itsi` or `itsi_content_pack: true` entries.

## 5. Premium ITSI?

If yes: merge `spa --json features show setting.apps.premium.itsi` (no `target_roles`).

- Main app: `name`, `source: splunkbase`, `app_id: 1841`, `premium_app: itsi`
- Licenses: run `spa licenses --config …` after adding ITSI — proposes `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` from `../Software`; see [licenses.md](licenses.md)
- **Java 21 max** on the search/ITSI host `splunk_hosts[].os.packages` (not the global `os:` block) — see [aws-os-matrix.md](aws-os-matrix.md)
- Full lab (not `spa init --example`): `examples/single_node_itsi.yml`

## 6. ITSI content packs?

Merge `spa --json features show setting.apps.premium.itsi.content_pack` for DA-ITSI-ContentLibrary. Per pack in `content_pack_apps`: `content_pack_install`, `content_pack_api` (`install_all`, `enabled`, `saved_search_action`, `backfill`, `resolution`, `prefix`), and `customizations.run_playbook_after_restart` / `force_run_playbook_after_restart`. Merge `spa --json features show setting.apps.premium.itsi.content_pack.single` for one pack that is its own folder (those API keys at top level; no `content_pack_apps`).

- Requires a sibling `premium_app: itsi` entry with the same `state`
- Do not set `premium_app` or `target_roles` on the pack entry
- **Folder `name` must match on-disk app name** inside the spl/tgz
- Do not invent Splunkbase IDs

## 7. Other Splunkbase apps

Merge `spa --json features show setting.apps`. Per app: `name` (folder name), `app_id`, optional `version: latest`, `target_roles`.

## 8. Local org apps

`source: local`, `path` under the shared apps dir (`.spa.yml` `apps_dir` / `SPA_APPS_DIR` / `$SPA_HOME/apps`). Override per lab with `splunk_app_deployment.local_app_repo_path`.

## Minimal block sketch

Normal TA (not ITSI):

```yaml
splunk_app_deployment:
  splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
  splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
  apps:
    - name: Splunk_TA_nix
      source: splunkbase
      app_id: 833
      target_roles:
        - search_head
        - indexer
```

ITSI premium (no `target_roles`): use the `setting.apps.premium.itsi` snippet.

## Out of scope

- ES full prerequisite matrix (`premium_app: es` is not valid)
- Splunkbase search CLI (future #59/#68)
- Custom `run_playbook` graphs unless user explicitly needs them (`setting.apps.customizations`)
