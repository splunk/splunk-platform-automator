# App Deployment Customizations

Per-app, per-role customizations: remove files from the app, add config files under the app’s `local/` folder, and run custom Ansible playbooks or roles. You can list the **same app multiple times** with different `target_roles` and different `customizations`.

## Overview

Add an optional `customizations` block to any app entry in `splunk_app_deployment.apps`. Customizations run **after** the app is deployed to the target (Deployment Server, Cluster Manager, Deployer, or direct). You can use any combination of:

- **`remove`** – Delete files or directories from the deployed app.
- **`local_configs`** – Create or update Splunk `.conf` files in the app’s `local/` folder (same structure as `splunk_conf` in `splunk_config.yml`).
- **`run_playbook`** / **`run_role`** – Run custom Ansible for that app on the host.

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

## Execution order

For each host and each matching app entry, customizations run in this order:

1. **Deploy app** (existing logic).
2. **remove** – delete listed files/dirs under the app.
3. **local_configs** – create/update each config file in the app’s `local/` folder.
4. **run_playbook** or **run_role** – run custom Ansible with `app_path` (and `app_name`) available.

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

  run_playbook: "ansible/apps_playbooks/customize_my_ta.yml"
  # OR
  run_role: "my_namespace.custom_app_setup"

  extra_vars:
    app_name: "{{ app_name }}"
    app_path: "{{ app_path }}"
```

- **Modular**: Use only `remove`, only `local_configs`, only `run_playbook`/`run_role`, or any combination.
- **Per entry**: Each app entry has its own `customizations`; the same app in multiple entries can have different customizations for different roles.

## Related documentation

- [App Deployment](App_Deployment.md) – main documentation
- [App Deployment Guide](App_Deployment_Guide.md) – configuration and deployment methods
- [App Deployment Verification](App_Deployment_Verification.md) – verify deployed apps
