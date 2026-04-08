# Running Apps Playbooks Standalone (Wrapper)

This document describes how to run **apps playbooks** (e.g. `*_configure.yml` under `ansible/apps_playbooks/`) in isolation using the wrapper playbook `run_apps_playbook.yml`. The same wrapper works for both **`run_playbook`** and **`run_playbook_after_restart`** playbooks.

## When playbooks run in the full deployment

| Customization | When it runs | Typical use |
|---------------|--------------|-------------|
| **`run_playbook`** | During app deployment, in **apply_customizations** (before the “Restart splunk” handler). | One-off config, local files, REST calls that don’t require Splunk to be restarted first. |
| **`run_playbook_after_restart`** | In a **follow-up play** in `deploy_splunk_apps.yml`, **after** the deployment handler (e.g. Restart splunk) has run on the host. | Config that must run once Splunk is back up (e.g. wait for port, then REST or lookups). |

Both types of playbooks receive the same variables when invoked by the framework: `app_path`, `app_name`, and optionally `customization_extra_vars` (from `extra_vars` in app customizations).

### Conditional execution: `force_run_playbook` / `force_run_playbook_after_restart`

By default, `run_playbook` and `run_playbook_after_restart` only execute when the app is being installed or updated during this run (`update_needed` is true). If the app is already installed at the expected version and nothing changed, the playbooks are skipped.

To force execution regardless of install status, set the corresponding force flag in `customizations`:

| Flag | Applies to | Default | Effect |
|------|-----------|---------|--------|
| **`force_run_playbook`** | `run_playbook` | `false` | When `true`, the playbook runs even if the app was already installed at the expected version. |
| **`force_run_playbook_after_restart`** | `run_playbook_after_restart` | `false` | When `true`, the post-restart playbook runs even if the app was already installed. Also applies to ITSI content pack apps. |

Example configuration:

```yaml
- name: "my_app"
  source: splunkbase
  app_id: 1234
  customizations:
    run_playbook: "ansible/apps_playbooks/my_app-configure.yml"
    force_run_playbook: true
    run_playbook_after_restart: "ansible/apps_playbooks/my_app-post-configure.yml"
    force_run_playbook_after_restart: false
```

## Wrapper: `run_apps_playbook.yml`

**`ansible/run_apps_playbook.yml`** runs a single apps playbook in isolation (no full app deployment). Use it to:

- Re-run a configure playbook after changing config or fixing an error.
- Test a playbook against a specific host or group.
- Run the same playbook that you use for `run_playbook` or `run_playbook_after_restart` without going through the full deploy.

It works for **both**:

- Playbooks intended as **`run_playbook`** (e.g. `Splunk_ML_Toolkit-configure.yml`, `Splunk_TA_nix-enable_perf_metrics.yml`).
- Playbooks intended as **`run_playbook_after_restart`** (e.g. `DA-ITSI-CP-monitoring-alerting_configure.yml`, `Splunk_SIM_addon-configure.yml`).

Required extra vars:

- **`apps_playbook`** – Path to the task file **under** `ansible/` (e.g. `apps_playbooks/DA-ITSI-CP-monitoring-alerting_configure.yml`).
- **`app_name`** – App name (e.g. `DA-ITSI-CP-monitoring-alerting`).

Optional:

- **`target_group`** – Inventory group (default: `role_search_head`).
- **`app_path_override`** – Override `app_path` (default: `{{ splunk_home }}/etc/apps/{{ app_name }}`).
- **`playbook_extra_vars`** – Dict passed to the playbook as `customization_extra_vars` (e.g. `'{"generic_alerts_index":"generic_alerts"}'`).

Use **`-l` / `--limit`** to restrict to specific hosts (e.g. `-l sh`, `-l searchhead1`). Run from the **repository root** so `ansible.cfg` (and thus inventory) is used.

### Examples (from repo root)

**Run a post-restart–style configure playbook on search heads:**

```bash
ansible-playbook ansible/run_apps_playbook.yml \
  -e "apps_playbook=apps_playbooks/DA-ITSI-CP-monitoring-alerting_configure.yml" \
  -e "app_name=DA-ITSI-CP-monitoring-alerting" \
  -l sh
```

**Run a `run_playbook`–style configure playbook:**

```bash
ansible-playbook ansible/run_apps_playbook.yml \
  -e "apps_playbook=apps_playbooks/Splunk_ML_Toolkit-configure.yml" \
  -e "app_name=Splunk_ML_Toolkit" \
  -l sh
```

**With extra vars for the playbook:**

```bash
ansible-playbook ansible/run_apps_playbook.yml \
  -e "apps_playbook=apps_playbooks/DA-ITSI-CP-monitoring-alerting_configure.yml" \
  -e "app_name=DA-ITSI-CP-monitoring-alerting" \
  -e 'playbook_extra_vars={"generic_alerts_index":"generic_alerts"}' \
  -l sh
```
