# Basic apps questionnaire

Load [spa-apps](../../spa-apps/SKILL.md) for this phase. Search Splunkbase with `spa --json apps search QUERY` (technology keywords), then **one** `spa --json apps snippet APP_ID` without `--customize`. If `playbooks` is set, ask before `snippet --customize`. Merge the printed snippet into `splunk_config.yml` (until `spa config`, #76). Do not guess `app_id`. Do not open splunkbase.com first.

Deep customization: [docs/App_Deployment_Customizations.md](../../../../docs/App_Deployment_Customizations.md) and `spa --json features show setting.apps.customizations`.

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

See [docs/App_Deployment.md](../../../../docs/App_Deployment.md). Optional vault in config. Do not verify with `echo $SPLUNKBASE_*`.

## 3. App sources

- `splunkbase` — snippet from `spa apps snippet`; requires credentials at deploy
- `local` — `spa apps snippet APP_ID --local` (short for `--source local`) resolves the folder or archive already in `apps_dir`. Nothing there → `spa apps download APP_ID --extract --yes` first (`--extract` deletes the archive after unpacking; `--overwrite` replaces an existing folder; ITSI/content packs deploy from the archive, so omit `--extract`). For a custom app, use `spa apps snippet FOLDER_NAME --local`. Download does not print YAML.

## 4. Target roles

For **normal** apps, `target_roles`: `search_head`, `indexer`, `universal_forwarder`, `heavy_forwarder` (maps to deployer/CM/DS/direct per SPA). Pass `--roles` on `snippet` for TAs.

Do **not** set `target_roles` on `premium_app: itsi` or `itsi_content_pack: true` entries.

## 5. Premium ITSI?

ITSI / ITE Work → Splunkbase **1841** only (`spa apps snippet 1841`). Not 5403.

Merge `spa --json features show setting.apps.premium.itsi` for Java 21 and license files; the apps[] slice also comes from `spa apps snippet 1841`.

- Main app: `premium_app: itsi`, no `target_roles`
- Licenses: run `spa licenses --config …` after adding ITSI — proposes `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` from `../Software`; see [licenses.md](licenses.md)
- **Java 21 max** on the search/ITSI host `splunk_hosts[].os.packages` (not the global `os:` block) — see [aws-os-matrix.md](aws-os-matrix.md)
- Full lab (not `spa init --example`): `examples/single_node_itsi.yml`

## 6. ITSI content packs?

`spa apps search "content pack"` / `snippet` 5391 (library) or a single-pack id. Sibling **1841** is required. See catalog `setting.apps.premium.itsi.content_pack` and `.single`.

- Do not set `premium_app` or `target_roles` on the pack entry
- **Folder `name` must match on-disk app name** inside the spl/tgz

## 7. Other Splunkbase apps

`spa --json apps search QUERY` then `snippet APP_ID`. Fill `target_roles`.

## 8. Local org apps

`source: local`, `path` under the shared apps dir (`.spa.yml` `apps_dir` / `SPA_APPS_DIR` / `$SPA_HOME/apps`). Override per lab with `splunk_app_deployment.local_app_repo_path`.

## Out of scope

- ES full prerequisite matrix (`premium_app: es` is not valid)
- Auto-deploy without approval
- `spa apps add` / `remove` (that is #76 / #68)
