# Basic apps questionnaire

Load [spa-apps](../../spa-apps/SKILL.md) for this phase. Search Splunkbase with `spa --agent apps search QUERY` (technology keywords), then use one `spa --agent apps add APP_ID` transaction. If curated `playbooks` are available, ask before adding `--customize`. Do not guess `app_id`, patch YAML, or open splunkbase.com first. Finish with `spa --agent validate`.

Deep customization: [docs/apps.md](../../../../docs/apps.md#customize-an-app) and `spa --agent config explain splunk_app_deployment.apps.customizations.remove`.

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

See [docs/apps.md](../../../../docs/apps.md). Optional vault in config. Do not verify with `echo $SPLUNKBASE_*`.

## 3. App sources

- `splunkbase` — `spa --agent apps add APP_ID`; requires credentials at deploy
- `local` — `spa --agent apps add APP_ID --local` resolves the folder or archive already in `apps_dir`. Nothing there → `spa apps download APP_ID --extract --yes` first. For a custom app, use `spa --agent apps add FOLDER_NAME --local`. Download does not edit config.

## 4. Target roles

For **normal** apps, `target_roles`: `search_head`, `indexer`, `universal_forwarder`, `heavy_forwarder` (maps to deployer/CM/DS/direct per SPA). Pass `--roles` to `apps add`.

Do **not** set `target_roles` on `premium_app: itsi` or `itsi_content_pack: true` entries.

## 5. Premium ITSI?

ITSI / ITE Work → Splunkbase **1841** only (`spa --agent apps add 1841`). Not 5403.

Discover Java and license paths with `spa --agent config explain PATH`, then set chosen values with `spa --agent config set PATH VALUE`.

- Main app: `premium_app: itsi`, no `target_roles`
- Licenses: run `spa licenses --config …` after adding ITSI — proposes `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` from Software; see [licenses.md](licenses.md)
- **Java 21 max** on the search/ITSI host `splunk_hosts[].os.packages` (not the global `os:` block) — see [aws-os-matrix.md](aws-os-matrix.md)
- Full lab (not `spa init --example`): `examples/single_node_itsi.yml`

## 6. ITSI content packs?

`spa apps search "content pack"` then `spa --agent apps add 5391 --content-pack NAME` (library) or add a single-pack id. Sibling **1841** is added when missing.

- Do not set `premium_app` or `target_roles` on the pack entry
- **Folder `name` must match on-disk app name** inside the spl/tgz

## 7. Other Splunkbase apps

`spa --agent apps search QUERY` then `spa --agent apps add APP_ID --roles ROLE[,ROLE]`.

## 8. Local org apps

`source: local`, `path` under the shared apps dir (`.spa.yml` `apps_dir` / `SPA_APPS_DIR` / `$SPA_HOME/apps`). Override per lab with `splunk_app_deployment.local_app_repo_path`.

## Out of scope

- ES full prerequisite matrix (`premium_app: es` is not valid)
- Auto-deploy without approval
- Host uninstall remains out of scope; `apps remove` removes only authored config.
