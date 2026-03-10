# App Deployment Customizations

Per-app, per-role customizations: remove files from the app, add config files under the app’s `local/` folder, and run custom Ansible playbooks or roles. You can list the **same app multiple times** with different `target_roles` and different `customizations`.

## Overview

Add an optional `customizations` block to any app entry in `splunk_app_deployment.apps`. Customizations run **after** the app is deployed to the target (Deployment Server, Cluster Manager, Deployer, or direct). You can use any combination of:

- **`remove`** – Delete files or directories from the deployed app.
- **`local_configs`** – Create or update Splunk `.conf` files in the app’s `local/` folder (same structure as `splunk_conf` in `splunk_config.yml`).
- **`update_indexes`** – If the app has `default/indexes.conf`, copy it to `local/` and set `homePath`/`coldPath` from `splunk_volume_defaults` (same as ITSI indexer apps). Default is `false`.
- **`run_playbook`** / **`run_role`** – Run custom Ansible for that app on the host.
- **`run_playbook_after_restart`** – Register a task file to run **after** the deployment handler (e.g. Restart splunk) has run on that host. Use when the playbook must run once Splunk is back up (e.g. wait for port, then call REST or configure lookups). Supported for **direct deployment** only; the playbook runs in a follow-up play.

Entries without `customizations` are unchanged.

## Same app, different customizations per role

The same app (same `name`, same `source`/`app_id` or `path`) can appear in multiple entries with different `target_roles` and different `customizations`. Each host gets the app with the customizations for the matching entry.

**Example:** Splunk_TA_nix for search heads (remove indexes, enable inputs), for indexers (only remove inputs), and for heavy forwarders (custom playbook):

```yaml
splunk_app_deployment:
  apps:
    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles:
        - search_head
      customizations:
        remove:
          - default/indexes.conf
        local_configs:
          inputs.conf:
            "tcp://5514":
              disabled: 0

    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles:
        - indexer
      customizations:
        remove:
          - default/inputs.conf

    - name: "Splunk_TA_nix"
      source: splunkbase
      app_id: 833
      version: "latest"
      target_roles:
        - heavy_forwarder
      customizations:
        run_playbook: "ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml"
        extra_vars:
          app_path: "{{ app_path }}"
```

## Customization options

### `remove`

Delete files or directories from the app after deploy (paths relative to the app root).

```yaml
customizations:
  remove:
    - default/indexes.conf
    - default/inputs.conf
    - bin/optional_script.sh
```

### `local_configs`

Create or update Splunk config files in the app’s `local/` directory. Structure matches the `splunk_conf` section: **config file name** → **section (stanza) name** → **option key/value**. File names are without a `local/` prefix; files are always written under the app’s `local/` folder.

```yaml
customizations:
  local_configs:
    inputs.conf:
      "tcp://5514":
        disabled: 0
      "tcp://9997":
        disabled: 0
    indexes.conf:
      default:
        homePath: $SPLUNK_DB/default/db
        coldPath: $SPLUNK_DB/default/colddb
```

- **Key**: config file name only (e.g. `inputs.conf`, `indexes.conf`). File path is `{{ app_path }}/local/<key>`.
- **Value**: sections (stanza names), each with option names and values (strings or numbers as in Splunk .conf).

The `local/` directory is created if it does not exist.

### `update_indexes`

For **normal apps only** (not premium apps like ITSI): when `true`, if the app has a `default/indexes.conf` file, the framework copies it to the app’s `local/` folder and updates `homePath` and `coldPath` to use the volume names from `splunk_volume_defaults` (same behavior as ITSI indexer apps). Use this when you want the app’s indexes to use your configured index volumes without manually maintaining `local/indexes.conf`. Default is `false`.

```yaml
customizations:
  update_indexes: true
```

If the app does not have `default/indexes.conf`, nothing is done. The handler (Restart Splunk, Apply indexer cluster bundle, etc.) is triggered when changes are made, same as other customizations.

**Example – enable Splunk_TA_nix performance metrics (e.g. universal_forwarder):** use `local_configs` to enable script inputs and set the index (as in `config/splunk_config.yml`):

```yaml
customizations:
  local_configs:
    inputs.conf:
      "script://./bin/vmstat_metric.sh":
        disabled: 0
        index: itsi_im_metrics
      "script://./bin/iostat_metric.sh":
        disabled: 0
        index: itsi_im_metrics
      "script://./bin/ps_metric.sh":
        disabled: 0
        index: itsi_im_metrics
      "script://./bin/df_metric.sh":
        disabled: 0
        index: itsi_im_metrics
      "script://./bin/interfaces_metric.sh":
        disabled: 0
        index: itsi_im_metrics
      "script://./bin/cpu_metric.sh":
        disabled: 0
        index: itsi_im_metrics
```

### `run_playbook` / `run_role`

Run custom Ansible for this app on the host. Use when you need more than `remove` or `local_configs`.

| Option        | Description |
|---------------|-------------|
| `run_playbook` | Path to a task file from the **project root** (e.g. `ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml`). |
| `run_role`     | Fully qualified role name (e.g. `my_namespace.custom_app_setup`). |
| `extra_vars`   | Optional dict of variables; `app_name` and `app_path` are provided by the framework. |

Use **one** of `run_playbook` or `run_role` per entry. For `run_playbook`, the path is relative to the **project root** (top of the repository).

**Triggering the deployment handler:** The framework does not know if your task file changed anything. To trigger the correct handler (Restart Splunk, Reload deploy-server, Push shcluster bundle, or Apply indexer cluster bundle) after your custom tasks run, set the fact `update_needed: true` when you make changes. The calling role will then run its “notify when update_needed” task and fire the right handler. In your task file, either set it when you have changes (e.g. register the task and then `set_fact: update_needed: true` when `result is changed`), or set it at the end if your playbook always modifies the app.

**Example – enable same performance metrics via playbook:** the repo includes `ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml`, which enables the same Splunk_TA_nix script inputs as the `local_configs` example above. Use it for roles where you prefer a task file (e.g. heavy_forwarder), with optional `ta_nix_script_index` in `extra_vars`:

```yaml
customizations:
  run_playbook: "ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml"
  extra_vars:
    ta_nix_script_index: "itsi_im_metrics"   # optional; default is itsi_im_metrics
```

Generic playbook example:

```yaml
customizations:
  run_playbook: "ansible/apps_playbooks/customize_my_ta.yml"
  extra_vars:
    my_option: "value"
```

or

```yaml
customizations:
  run_role: "my_namespace.custom_app_setup"
  extra_vars:
    app_path: "{{ app_path }}"
```

### `run_playbook_after_restart`

Run a task file **after** the deployment handler (e.g. Restart splunk) has run. Use this when your playbook needs Splunk to be up (e.g. wait for splunkd port, then call REST APIs or configure lookups). The framework runs customizations and notifies the handler; at the end of the play, Ansible runs handlers; a **follow-up play** then runs your task file on each host that registered one.

- **Runs on the target host**: Registration happens only when the app is deployed **directly** to the host (via `apps_direct`). The playbook then runs on that same host in the follow-up play. If the app is deployed via Deployment Server, Deployer, or Cluster Manager, the playbook is **not** registered and **does not** run on the clients — only direct deployment is supported for this feature.
- **Path**: Same as `run_playbook` — path from project root to the task file (e.g. `ansible/apps_playbooks/Splunk_SIM_addon-configure.yml`).
- **Vars**: `app_path`, `app_name`, and `customization_extra_vars` (including `extra_vars` from the app config) are passed into the included tasks.

You can use both `run_playbook` (runs before the handler) and `run_playbook_after_restart` (runs after) for the same app if needed.

**Example – SIM Add-on (configure after restart):**

```yaml
customizations:
  run_playbook_after_restart: "ansible/apps_playbooks/Splunk_SIM_addon-configure.yml"
  extra_vars:
    o11y_realm: "us1"
    o11y_org_id: "FLqQG3NA4AA"
    o11y_api_token: "{{ vaulted_o11y_api_token }}"   # use vault or var
```

## Execution order

For each host and each matching app entry, customizations run in this order:

1. **Deploy app** (existing logic).
2. **remove** – delete listed files/dirs under the app.
3. **local_configs** – create/update each config file in the app’s `local/` folder.
4. **update_indexes** – if enabled and the app has `default/indexes.conf`, copy to `local/` and set `homePath`/`coldPath`.
5. **run_playbook** or **run_role** – run custom Ansible with `app_path` (and `app_name`) available.
6. **run_playbook_after_restart** – not run here; the app is added to a per-host list. After the play finishes, Ansible runs handlers (e.g. Restart splunk). A **follow-up play** (“Run post-restart playbooks”) then runs each registered task file on that host with `app_path`, `app_name`, and `extra_vars`.

So you can remove default config, then add local configs, then run a playbook that does more.

## Full `customizations` reference

```yaml
customizations:
  remove:
    - default/indexes.conf
    - default/inputs.conf

  local_configs:
    inputs.conf:
      "tcp://5514":
        disabled: 0
    indexes.conf:
      default:
        homePath: $SPLUNK_DB/default/db

  update_indexes: false   # optional; when true, copy default/indexes.conf to local/ and set homePath/coldPath

  run_playbook: "ansible/apps_playbooks/customize_my_ta.yml"
  # OR
  run_role: "my_namespace.custom_app_setup"
  # OR run a task file after the Restart splunk (etc.) handler has run (direct deployment only):
  run_playbook_after_restart: "ansible/apps_playbooks/Splunk_SIM_addon-configure.yml"

  extra_vars:
    app_name: "{{ app_name }}"
    app_path: "{{ app_path }}"
```

- **Modular**: Use only `remove`, only `local_configs`, only `update_indexes`, only `run_playbook`/`run_role`, only `run_playbook_after_restart`, or any combination.
- **Per entry**: Each app entry has its own `customizations`; the same app in multiple entries can have different customizations for different roles.

## Related documentation

- [App Deployment](App_Deployment.md) – main documentation
- [App Deployment Guide](App_Deployment_Guide.md) – configuration and deployment methods
- [App Deployment Verification](App_Deployment_Verification.md) – verify deployed apps
- **Running playbooks standalone:** To run a `run_playbook` or `run_playbook_after_restart` task file manually (e.g. to re-run a configure playbook), use the wrapper `ansible/run_apps_playbook.yml`. See [App Deployment Apps Playbooks](App_Deployment_Apps_Playbooks.md).
