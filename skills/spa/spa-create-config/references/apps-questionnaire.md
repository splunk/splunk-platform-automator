# Basic apps questionnaire

Load [spa-apps](../../spa-apps/SKILL.md) for this phase. Search Splunkbase with `spa --agent apps search QUERY` (technology keywords), then use one `spa --agent apps add APP_ID` transaction. If curated `playbooks` are available or `data.next` includes `apps.customize`, ask before adding `--customize`. Do not assume yes. `--customize` with `--content-pack NAME` attaches that pack's playbook. Do not guess `app_id`, patch YAML, or open splunkbase.com first. Finish with `spa --agent validate`.

Deep customization: [docs/apps.md](../../../../docs/apps.md#customize-an-app) and `spa --agent config explain splunk_app_deployment.apps.customizations.remove`.

## 1. Deploy apps?

If no → omit `splunk_app_deployment` entirely.

## 2. Credentials

Check Splunkbase with `spa apps auth check`. Report **set / not set** only in chat; never display the values. Prefer environment variables on controller — see [secrets-handling.md](secrets-handling.md). If not set: create a Splunk.com account at https://splunkbase.splunk.com/, export both variables, paste nothing in chat.

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

When search-row `placement_confidence` is `high`, take roles from that row. Otherwise read `install_docs_url` (Unix TA: https://splunk.github.io/splunk-add-on-for-unix-and-linux/Install/).

For **normal** apps, `target_roles`: `search_head`, `indexer`, `universal_forwarder`, `heavy_forwarder` (maps to deployer/CM/DS/direct per SPA). SPA places TAs by role, not by host. Follow `data.next` after each add. If add returns `ready: false` with a roles choice, AskQuestion over `allowed` (pre-check `suggested`), then retry with `--roles`. Do not guess.

Do **not** set `target_roles` on `premium_app: itsi` or `itsi_content_pack: true` entries. Do not ask for roles on those entries.

## 5. Premium ITSI?

ITSI / ITE Work → Splunkbase **1841** only. Not 5403. Minimal ITSI is `spa config merge itsi-minimal`. After the operator accepts that merge, ask once about Java on the search host via `spa config set` on that host's `os.packages` (`java-21-openjdk` on Amazon Linux/RHEL, `openjdk-21-jdk` on Ubuntu) — see [aws-os-matrix.md](aws-os-matrix.md).

Discover license paths with `spa --agent config explain PATH`, then set chosen values with `spa --agent config set PATH VALUE`.

- Main app: `premium_app: itsi`, no `target_roles`
- Licenses: follow `data.next` after adding ITSI (`spa --env NAME --agent licenses list`) — proposes `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` from Software; see [licenses.md](licenses.md)
- Full lab (not `spa init --example`): `examples/single_node_itsi.yml`

## 6. ITSI content packs?

`spa apps search "content pack"` then `spa --agent apps add 5391 --content-pack NAME` (library) or add a single-pack id. Sibling **1841** is added when missing.

- Do not set `premium_app` or `target_roles` on the pack entry
- **Folder `name` must match on-disk app name** inside the spl/tgz

## 7. Other Splunkbase apps

`spa --agent apps search QUERY` then `spa --agent apps add APP_ID --roles ROLE[,ROLE]`. A second copy of the same `app_id` uses `--new` plus different `--roles`.

## 8. Local org apps

`source: local`, `path` under the shared apps dir (`.spa.yml` `apps_dir` / `SPA_APPS_DIR` / `$SPA_HOME/apps`). Override per lab with `splunk_app_deployment.local_app_repo_path`.

## Out of scope

- ES full prerequisite matrix (`premium_app: es` is not valid)
- Auto-deploy without approval
- Host uninstall remains out of scope; `apps remove` removes only authored config. Two copies need `--roles` to say which row to remove.
