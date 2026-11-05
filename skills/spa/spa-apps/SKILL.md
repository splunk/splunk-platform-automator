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

## Config boundary (mandatory)

Never edit `config/splunk_config.yml` by hand for apps. `spa --agent apps add` and `spa --agent apps remove` write `splunk_app_deployment` for you. Any other setting (SVA, OS, AWS, licenses, the header) goes through `spa config` with [spa-create-config](../spa-create-config/SKILL.md). Validation, provision, and deploy stay in [/spa](../spa/SKILL.md), which waits for your yes.

## Secrets

Follow [secrets-handling.md](../spa-create-config/references/secrets-handling.md). Report Splunkbase env vars as **set** / **not set**. Never print passwords. YAML creds stay `lookup('env', ...)`.

**Splunkbase credentials check (before a Splunkbase add or download):** run the set / not-set loop from [secrets-handling.md](../spa-create-config/references/secrets-handling.md). Do not use `env | grep` or `printenv`. If either variable is not set, ask (AskQuestion if available):

1. **Export them in your shell, then restart the session.** Paste nothing into chat.
2. **Skip Splunkbase apps** and use a local archive in `apps_dir` (step 5), or stay trial-only.
3. **Show the setup docs**: [docs/apps.md](../../../docs/apps.md).

Re-run the set / not-set loop after the operator says it is done.

`spa apps download` reads `splunk_app_deployment.splunkbase_username` / `splunkbase_password` from `splunk_config.yml` first (a `lookup('env', 'NAME')` value resolves that env var; a vault ref falls back), then `SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD`.

## Workflow (token-cheap)

1. `spa --agent apps search QUERY` with technology keywords. Optional `--type app|addon` and `--kind ta|premium_itsi|itsi_content_library|itsi_content_pack_single|es_not_premium`. An `itsi` query pins **1841** first; `es` pins **263**. Do **not** open splunkbase.com first.
2. Pick one `app_id` from the compact rows (`app_id`, `name`, `title`, `type`, `kind`, `version`, `summary`). No full description on search. Default 10 hits; tighten QUERY if the page is wrong.
3. For a normal app, use one transaction: `spa --agent apps add APP_ID --roles ROLE[,ROLE]`. A second copy of the same `app_id` (different `target_roles`) is `spa --agent apps add APP_ID --new --roles ROLE[,ROLE]`. Add schema-backed fields with repeatable `--set FIELD VALUE`; lists and maps use strict JSON. Later edits use the compound selector `splunk_app_deployment.apps[app_id=APP_ID,target_roles=ROLE]`.
   - **Choosing roles (normal apps only):** follow `data.next` / `ready: false` on add. If add returns a roles `choice`, AskQuestion over `allowed` (pre-check `suggested` from search/snippet). `--roles` is required for normal apps and rejected for ITSI (1841) and content packs. ITSI (1841) and content packs never ask this question. SPA places TAs by role, not by host.
   - **Always ask.** Ask with AskQuestion which roles the app deploys to, even when the config has one host with one role; that role is then the option to confirm. With several roles or hosts, offer a checkbox list and "All roles on HOST" per host. Never pick roles silently. The answer becomes `target_roles`.
   - Check Splunkbase credentials before a Splunkbase add (see the check below).
4. If search reports curated playbooks, **ask** whether to add the customization. Do not assume yes. If agreed, add `--customize` to the same `apps add` command. Required extra-vars secrets are reported as **set / not set** only. `--customize` on Content Library 5391 is a no-op when `spa_automation` is already on the pack.
5. Local source: `spa --agent apps add APP_ID --local --roles ...`. It selects the app folder or archive in `apps_dir`, folder first. Nothing there → download first (`spa apps download APP_ID --extract --yes` for a normal folder-backed app; ITSI/content packs deploy from the archive, so omit `--extract`). A custom local app uses its folder name instead of an app ID.
6. **Pick the right ID.** `1841` is Core ITSI, the app itself. `5391` is the Content Library, which holds many packs. A single content pack has its own Splunkbase app ID. When the operator wants one pack, use that pack's own ID if it has one. Otherwise use `--content-pack NAME` on 5391. Present the choices in three groups so the choice is visible: "Core ITSI" (app 1841 from `spa --agent apps search itsi`), "Single content packs" (rows from search with `kind` `itsi_content_pack_single`), and "Content packs (Library 5391)". The library row comes from search (5391 is pinned for ITSI queries). Its packs come from `spa --agent apps content-packs list 5391`, not from search. Run that command before selecting from Content Library 5391. It uses `--archive`, a matching archive in `apps_dir`, an install archive already in the app temp directory, or cached pack `app.conf` files. An install archive is left in place. `--version` selects a release (default `latest`); a newer latest release replaces the `app.conf` cache. An archive this command downloads is not kept. Each row supplies the exact folder name, archive label/description/version, matching SPA automation, and legal add command. Use `--archive PATH` to inspect a local archive without an env or credentials. Content Library 5391 then requires either repeatable `--content-pack NAME` or `--install-all-content-packs`. A recognized single content pack has its own Splunkbase app ID and needs neither library flag. The add command adds missing ITSI 1841 deterministically and reports unresolved topology or Java requirements without a partial write. License files are not a write barrier; unlicensed ITSI is IT Essentials Work.
7. Use `spa --agent apps remove APP_ID_OR_NAME` to remove authored configuration; it does not uninstall deployed files. Use `--content-pack NAME` to remove one nested 5391 pack. When the app is defined twice, do not remove until `--roles` names one copy (the error lists each copy's roles).
8. **After every add, follow `data.next` in order.** Prefer `argv` when present; if a shell is used, copy `command` verbatim. Do not invent follow-ups the envelope omitted. Do not refuse `apps add 1841` for missing license files. If the add was ITSI 1841, licenses list is optional (skip = trial / IT Essentials Work), then AskQuestion `none` / `list` / `name` for content packs. On `list`, run `spa --agent apps content-packs list 5391` and present each pack `name` / `title` (and `spa_automation` when present) before picking. On `name`, wait for folder names. On `none`, skip. Do not hide the names behind a count. Then ask **Add another app?** Yes, add another / No, done. On yes, go back to step 1. On no, show `spa --agent config get splunk_app_deployment` and stop. When spa-create-config called this skill, return to its Phase 9 loop.
9. `spa --agent validate`. After every add or remove, inspect `changed` and `ready` (`ok: false` means nothing was written). `spa --agent config get` the app identity (`found`), then validate. Deploy only after the operator's yes in chat, then hand off to [/spa](../spa/SKILL.md), which runs `spa deploy --yes` under its own gate. Standalone configure: `spa run splunk_apps_playbook_run --help` then `--apps-playbook STEM --hosts ROLE --yes`. Env-dir custom files: `--apps-playbook ancustom/my_custom_playbook` (not listed).

ITSI / ITE Work → **app_id 1841** (`premium_app: itsi`). Do not use 5403.

Content packs need a sibling 1841 entry. Library is 5391; single packs use `itsi_content_pack: true` without `target_roles`.

`--roles` only for TA `kind`. Fill `target_roles` before validate.
