---
name: spa-apps
description: >-
  Search Splunkbase, add SPA app entries, or download archives. Use when
  adding Splunkbase TAs, ITSI (1841), or ITSI content packs to a lab. Invoke from
  spa-create-config during the apps phase, or with /spa-apps.
license: Proprietary
compatibility: Requires SPA_HOME. spa apps search and snippet work without an env dir. add, remove, and download need an env.
metadata:
  product: splunk-platform-automator
  version: "1.0.0"
---

# spa-apps — Splunkbase search and config entries

Agents call `bin/spa` only. Never auto-run `spa deploy`. Use `spa --agent apps add` and `spa --agent apps remove`; do not patch YAML or parse a rendered snippet.

## When to use

- User wants a TA for a technology (`unix`, `cisco asa`, `windows event`, `aws`)
- User wants ITSI or an ITSI content pack
- User wants a `source: local` archive in `apps_dir`

## When not to use

- Greenfield topology / AWS / licenses → [spa-create-config](../spa-create-config/SKILL.md) (this skill is the apps phase only)
- Single-app deploy/remove on hosts → not shipped yet (#68)
- `premium_app: es` → not valid (#60)

## Secrets

Follow [secrets-handling.md](../spa-create-config/references/secrets-handling.md). Report Splunkbase env vars as **set** / **not set**. Never print passwords. YAML creds stay `lookup('env', ...)`.

`spa apps download` reads `splunk_app_deployment.splunkbase_username` / `splunkbase_password` from `splunk_config.yml` first (a `lookup('env', 'NAME')` value resolves that env var; a vault ref falls back), then `SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD`.

## Workflow (token-cheap)

1. `spa --agent apps search QUERY` with technology keywords. Optional `--type app|addon` and `--kind ta|premium_itsi|itsi_content_library|itsi_content_pack_single|es_not_premium`. An `itsi` query pins **1841** first; `es` pins **263**. Do **not** open splunkbase.com first.
2. Pick one `app_id` from the compact rows (`app_id`, `name`, `title`, `type`, `kind`, `version`, `summary`). No full description on search. Default 10 hits; tighten QUERY if the page is wrong.
3. For a normal app, use one transaction: `spa --agent apps add APP_ID --roles ROLE[,ROLE]`. Add schema-backed fields with repeatable `--set FIELD VALUE`; lists and maps use strict JSON.
4. If search reports curated playbooks, **ask** whether to add the customization. Do not assume yes. If agreed, add `--customize` to the same `apps add` command. Required extra-vars secrets are reported as **set / not set** only.
5. Local source: `spa --agent apps add APP_ID --local --roles ...`. It selects the app folder or archive in `apps_dir`, folder first. Nothing there → download first (`spa apps download APP_ID --extract --yes` for a normal folder-backed app; ITSI/content packs deploy from the archive, so omit `--extract`). A custom local app uses its folder name instead of an app ID.
6. Before selecting from Content Library 5391, run `spa --agent apps content-packs list 5391`. It uses `--archive`, a matching archive in `apps_dir`, an install archive already in the app temp directory, or cached pack `app.conf` files. An install archive is left in place. `--version` selects a release (default `latest`); a newer latest release replaces the `app.conf` cache. An archive this command downloads is not kept. Each row supplies the exact folder name, archive label/description/version, matching SPA automation, and legal add command. Use `--archive PATH` to inspect a local archive without an env or credentials. Content Library 5391 then requires either repeatable `--content-pack NAME` or `--install-all-content-packs`. A recognized single content pack has its own Splunkbase app ID and needs neither library flag. The add command adds missing ITSI 1841 deterministically and reports unresolved topology, license, or Java requirements without a partial write.
7. Use `spa --agent apps remove APP_ID_OR_NAME` to remove authored configuration; it does not uninstall deployed files. Use `--content-pack NAME` to remove one nested 5391 pack.
8. `spa --agent validate`. Deploy only if the operator asked (`spa deploy --yes`). Standalone configure: `spa run splunk_apps_playbook_run --help` then `--apps-playbook STEM --hosts ROLE --yes`. Env-dir custom files: `--apps-playbook ancustom/my_custom_playbook` (not listed).

ITSI / ITE Work → **app_id 1841** (`premium_app: itsi`). Do not use 5403.

Content packs need a sibling 1841 entry. Library is 5391; single packs use `itsi_content_pack: true` without `target_roles`.

`--roles` only for TA `kind`. Fill `target_roles` before validate.
