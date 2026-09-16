---
name: spa-apps
description: >-
  Search Splunkbase and print SPA apps[] snippets or download archives. Use when
  adding Splunkbase TAs, ITSI (1841), or ITSI content packs to a lab. Invoke from
  spa-create-config during the apps phase, or with /spa-apps.
license: Proprietary
compatibility: Requires SPA_HOME. spa apps search and snippet work without an env dir. spa apps download needs an env (apps_dir).
metadata:
  product: splunk-platform-automator
  version: "1.0.0"
---

# spa-apps — Splunkbase search and snippets

Agents call `bin/spa` only. Never auto-run `spa deploy`. Do not edit `splunk_config.yml` here; merge the printed snippet (later `spa config`, [#76](https://github.com/splunk/splunk-platform-automator/issues/76)).

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

1. `spa --json apps search QUERY` with technology keywords. Optional `--type app|addon` and `--kind ta|premium_itsi|itsi_content_library|itsi_content_pack_single|es_not_premium`. An `itsi` query pins **1841** first; `es` pins **263**. Do **not** open splunkbase.com first.
2. Pick one `app_id` from the compact rows (`app_id`, `name`, `title`, `type`, `kind`, `version`, `summary`). No full description on search. Default 10 hits; tighten QUERY if the page is wrong.
3. `spa --json apps snippet APP_ID` **without** `--customize`. Merge that YAML under `splunk_app_deployment.apps`.
4. If `playbooks` is non-empty (or the snippet comment says “pass --customize”), **ask** whether to add the curated playbook. Do not assume yes. If they agree: `spa --json apps snippet APP_ID --customize` and merge that YAML. Required extra_vars secrets: report env vars as **set / not set** only.
5. Local source: `spa apps snippet APP_ID --local --roles ...` (`--local` is short for `--source local`). It looks up the app folder or archive in `apps_dir` and uses whichever it finds, folder first. Nothing there → download first (`spa apps download APP_ID --extract --yes` for a normal folder-backed app; `--extract` removes the archive once unpacked. Add `--overwrite` to replace an existing folder. ITSI/content packs deploy from the archive, so omit `--extract`). Download never prints YAML.
6. Custom local app (not Splunkbase): put its folder or archive in `apps_dir`, then `spa apps snippet FOLDER_NAME --local --roles ...`. This does not contact Splunkbase.
7. `spa validate`. Deploy only if the operator asked (`spa deploy --yes`). Standalone configure: `spa run splunk_apps_playbook_run --help` then `--apps-playbook STEM --hosts ROLE --yes`. Env-dir custom files: `--apps-playbook ancustom/my_custom_playbook` (not listed).

ITSI / ITE Work → **app_id 1841** (`premium_app: itsi`). Do not use 5403.

Content packs need a sibling 1841 entry. Library is 5391; single packs use `itsi_content_pack: true` without `target_roles`.

`--roles` only for TA `kind`. Fill `target_roles` before validate.
