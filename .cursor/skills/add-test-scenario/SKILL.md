---
name: add-test-scenario
description: >-
  Create app scope scenario tests from a splunk_config.yml. Distills a source
  config into tests/configs/app_scope/<name>/, generates expected_scope.json,
  and adds optional assertions. Use when adding app scope/routing test coverage
  (deployer, CM, DS, direct). NOT for flat deployment test configs under
  tests/configs/*.yml — see "Deployment test configs" below.
---

# Add App Scope Test Scenario

## Two config types — pick the right one

| Type | Location | Test runner | Purpose |
|------|----------|-------------|---------|
| **App scope scenario** | `tests/configs/app_scope/<name>/splunk_config.yml` | `test_app_scope_scenarios.py` | Scope/routing logic only; no SSH, no AWS |
| **Deployment config** | `tests/configs/<name>.yml` (flat file) | `test_deployment.py` | Full pipeline on AWS (provision, install, deploy) |

This skill covers **app scope scenarios** only. A large config like
`config/splunk_config.yml` or `tests/configs/2site-idxc_shc_mc_ds_sh_hf_uf_itsi_apps.yml`
can be **distilled** into an app scope scenario, but that is optional — it does not
replace a deployment test config.

### Deployment test configs (out of scope for this skill)

To add a full deployment test:

1. Create `tests/configs/<config_name>.yml` (flat YAML at top level of `configs/`).
2. Run `./tests/run_deployment_tests.sh -k "<config_name>"`.
3. No `expected_scope.json`, no `debug_app_scope.yml`.

## Overview

App scope scenarios live under `tests/configs/app_scope/<scenario_name>/`. Each has:

- `splunk_config.yml` — distilled input config
- `expected_scope.json` — scope output snapshot (optional but recommended)

The test runner **auto-discovers** scenarios (subdirs containing `splunk_config.yml`).
No registration beyond creating the directory.

```
tests/configs/app_scope/
├── <scenario_name>/
│   ├── splunk_config.yml
│   └── expected_scope.json
├── output/                          # generated at test-time (gitignored)
│   └── <scenario_name>_scope.json
└── ...
```

Key files:

- `tests/test_app_scope_scenarios.py` — discovery, playbook runner, assertions, snapshots
- `tests/scope_assertions.py` — reusable assertion helpers
- `tests/run_app_scope_scenarios_tests.sh` — preferred way to run tests (sets up venv)
- `ansible/verification/debug_app_scope.yml` — scope playbook

## Workflow

### 1. Check existing coverage

Before adding a scenario, scan existing configs under `tests/configs/app_scope/`.
Each `splunk_config.yml` documents itself in the header comment:

```yaml
# Scenario: <scenario_name>
# <Topology and app mix.>
# Verifies: <what the test checks>.
```

Read a few headers (and optionally their `expected_scope.json`) to confirm the
pattern you need is **not already covered**. Compare against the source config and
focus on gaps in these categories:

| Pattern category | Examples |
|-----------------|----------|
| Deployment paths | deployer, CM, DS, direct |
| Filters | `shc_whitelist`, `shc_blacklist`, `idxc_whitelist`, `hosts_whitelist`, `sc_whitelist` |
| App features | `premium_app`, `itsi_content_pack`, `content_pack_apps`, `deployment_target: direct` |
| Multi-role apps | Same app targeting `search_head` + `indexer` + `heavy_forwarder` |
| Duplicate apps | Same app name with different `target_roles` / serverclass |
| Customizations | `local_configs`, `run_playbook`, `run_playbook_after_restart`, `extra_vars` |

### 2. Create the scenario config

Create `tests/configs/app_scope/<scenario_name>/splunk_config.yml`:

- Start with a YAML header comment: scenario name, topology summary, what it verifies.
- **Distill** the source config: keep only active parts relevant to the patterns.
  Remove vault-encrypted values and commented blocks.
- Keep infrastructure minimal but representative (e.g. 2 indexers, 3 SH per cluster).
- Use placeholder values for tokens/credentials (e.g. `test-hec-token-placeholder`).

Header format:

```yaml
---
# Scenario: <scenario_name>
# <One-line description of topology and app mix.>
# Verifies: <what the test checks>.
plugin: splunk-platform-automator
```

### 3. Generate the expected snapshot

**Option A — pytest auto-update (preferred after first run):**

```bash
./tests/run_app_scope_scenarios_tests.sh -k "<scenario_name>" -v
UPDATE_SCOPE_SNAPSHOTS=1 ./tests/run_app_scope_scenarios_tests.sh -k "snapshot and <scenario_name>" -v
```

This writes `tests/configs/app_scope/<scenario_name>/expected_scope.json` from
the normalized actual output. Review the diff before committing.

**Option B — manual playbook run (initial generation or debugging):**

```bash
mkdir -p tests/configs/app_scope/output/.ansible_tmp/remote

ANSIBLE_CONFIG="$(pwd)/ansible.cfg" \
ANSIBLE_LOCAL_TEMP="$(pwd)/tests/configs/app_scope/output/.ansible_tmp" \
ANSIBLE_REMOTE_TEMP="$(pwd)/tests/configs/app_scope/output/.ansible_tmp/remote" \
ansible-playbook ansible/verification/debug_app_scope.yml \
  -i tests/configs/app_scope/<scenario_name>/splunk_config.yml \
  -e run_scope_locally=true \
  -e "scope_output_path=$(pwd)/tests/configs/app_scope/output/<scenario_name>_scope.json" \
  -e assert_scope_invariants=true
```

Verify exit code is 0, then copy the output to
`tests/configs/app_scope/<scenario_name>/expected_scope.json`.

Note: when running via pytest, `_run_scope_playbook()` sets the Ansible temp dirs
automatically — manual env vars are only needed for standalone playbook runs.

### 4. Add scenario-specific assertions (optional but recommended)

Add an `elif scenario_name == "<name>":` block inside `test_scenario_scope_assertions`
in `tests/test_app_scope_scenarios.py`. Use helpers from `scope_assertions.py`:

| Helper | Purpose |
|--------|---------|
| `assert_deployers_entry(scope, host, apps, target_hosts)` | Specific deployer's apps and targets |
| `assert_deployer_apps(scope, apps)` | First deployer's app list |
| `assert_deployer_has_app_with_config(scope, app, state=, has_content_pack_apps=)` | Deployer app config details |
| `assert_deployer_target_hosts(scope, hosts)` | First deployer's target hosts |
| `assert_cluster_manager_apps(scope, apps)` | CM app list |
| `assert_cluster_manager_target_hosts(scope, hosts)` | CM target hosts |
| `assert_ds_app_count(scope, count)` | DS app count |
| `assert_ds_app_target_hosts(scope, app, hosts)` | DS app target hosts |
| `assert_ds_same_app_twice(scope, app, target_hosts_per_entry)` | Duplicate app entries on DS |
| `assert_direct_on_scope(scope, host, app, expected)` | Direct scope `on_scope` flag |
| `get_app_on_direct_for_host(scope, host, app)` | Direct scope entry for inspection |

Write assertions that validate **each deployment path** the scenario exercises.

Scenarios without a dedicated block fall through to generic structure checks
(`direct_scope`, `deployer`, `cluster_manager`, `deployment_server` are lists).
That is enough when `expected_scope.json` provides full coverage (see `sh_filters`).

### 5. Verify

Run from project root:

```bash
./tests/run_app_scope_scenarios_tests.sh -k "<scenario_name>" -v
```

The run script creates/activates `tests/.venv` and installs `ansible-core`,
`jmespath`, and `lxml` (required for the inventory plugin).

All applicable tests must pass:

- `test_scenario_scope_playbook_succeeds[<name>]` — playbook runs without error
- `test_scenario_scope_assertions[<name>]` — assertions pass (custom or generic fallback)
- `test_scenario_scope_matches_snapshot[<name>]` — only when `expected_scope.json` exists

To update snapshots after intentional scope changes:

```bash
UPDATE_SCOPE_SNAPSHOTS=1 ./tests/run_app_scope_scenarios_tests.sh -k "snapshot and <scenario_name>" -v
```

## Checklist

- [ ] Confirmed this is an **app scope** scenario, not a deployment config
- [ ] Pattern not already covered (checked `# Scenario:` headers under `tests/configs/app_scope/`)
- [ ] Directory created: `tests/configs/app_scope/<scenario_name>/`
- [ ] `splunk_config.yml` has header comment with scenario description
- [ ] Config distilled (no vault values, no commented blocks, minimal infra)
- [ ] Playbook ran successfully (exit code 0)
- [ ] `expected_scope.json` saved (via `UPDATE_SCOPE_SNAPSHOTS=1` or manual copy)
- [ ] Custom assertions added in `test_app_scope_scenarios.py` (if needed beyond snapshot)
- [ ] `./tests/run_app_scope_scenarios_tests.sh -k "<scenario_name>" -v` passes
