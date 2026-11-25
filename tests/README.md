# Splunk Platform Automator Testing Framework

Automated testing for Splunk Platform Automator. Local gates call pytest. Live AWS
deployments compose a provider-free topology with a suite overlay, then call `bin/spa`
only (`validate`, `deploy --yes`, `run verification/...`, `destroy --yes`).

## Overview

- **Local** (`@pytest.mark.local`) — schema, CLI, unit, and Ansible-job tests (`spa run`, plus the JSONL callback fixture). No AWS.
- **Live AWS** (`@pytest.mark.aws`) — one isolated `SPA_ENV_DIR` per topology. `SPA_HOME` is this checkout.
- **Incremental** — tests in `test_deployment.py` are sequential per topology; a failure skips later steps.
- **Suites** — `tests/deployment/suites/*.yml` pick topologies and OS. Live tests do not glob `tests/configs/*.yml`.

## Prerequisites

1. **Python 3.9+**
2. **AWS Credentials** (live suite only; report as set / not set, never print values):
   ```bash
   export AWS_ACCESS_KEY_ID
   export AWS_SECRET_ACCESS_KEY
   ```
3. **SSH Key**: the key named in `tests/deployment/providers/aws.yml` (default `~/.ssh/aws_key.pem`)
4. **Software Directory**: Enterprise and UF tarballs in `../Software/` (or `spa environment set --software-dir`). Clustered/D1 topologies need `Splunk_Enterprise.lic`. The ITSI topology also needs `Splunk_ITSI.lic` and Splunkbase env vars set.
5. Cluster passwords: `SPLUNK_IDXC_PASSWORD` and `SPLUNK_SHC_PASSWORD` (the harness copies `SPLUNK_ADMIN_PASSWORD` when those are unset)

## Directory Structure

```
tests/
├── deployment/                 # Live topologies × provider × suite (not globbed from configs/)
│   ├── topologies/            # Provider-free (hosts, clusters, apps, licenses)
│   │   ├── single_node.yml
│   │   ├── 2idx_sh_ds_hf_uf.yml
│   │   ├── cm_2idxc_3shc_ds.yml
│   │   └── 2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps.yml
│   ├── providers/             # Cloud/lab knobs; no hosts. No committed ami_id.
│   │   └── aws.yml
│   └── suites/
│       └── aws.yml            # which topologies, OS, extra UFs
├── deployment_compose.py      # Merge provider then topology, then the suite hook
├── deployment_provider.py     # AWS latest-ami hook (CCM/VirtualBox later)
├── configs/                   # Local fixtures only (not live AWS)
│   ├── app_deployment/        # Extra-vars fixtures for app deployment tests
│   └── app_scope/             # App scope scenario configs (no SSH)
├── conftest.py                # Pytest fixtures (isolated SPA_ENV_DIR per topology)
├── pytest.ini
├── test_deployment.py         # spa validate / deploy / verification / destroy
├── test_deployment_composer.py
├── test_verification.py       # spa run verification against an existing env (--local)
├── run_deployment_tests.sh    # Umbrella: every file in deployment/suites/
├── run_deployment_aws_tests.sh
├── run_verification_tests.sh
├── run_cli_tests.sh
├── run_ansible_tests.sh
├── run_unit_tests.sh
├── run_local_tests.sh
└── ...
```

## Test Phases

### Phase 1: Deployment (`test_deployment.py`)

Each topology is composed (provider YAML + topology YAML + suite OS hook), then `bin/spa` runs the operator path. Do not import `spa.api`. Do not pass `-v` (unredacted Ansible). Failure detail stays in `$SPA_ENV_DIR/logs`.

| Step | Test | Command |
|------|------|---------|
| 1 | `test_01_prepare_config` | Compose config, inject Software paths and SplunkEnvID, `spa validate` |
| 2 | `test_02_deploy` | `spa deploy --yes` |
| 3 | `test_03_wait_for_splunk` | `spa run verification/wait_for_splunk` |
| 4 | `test_04_wait_for_bucket_fixup` | `spa run verification/wait_for_bucket_fixup` (skip without `cluster_manager`) |
| 5 | `test_05_check_idxc_health` | `spa run verification/check_idxc_health` (skip without `cluster_manager`) |
| 6 | `test_06_wait_for_shc_captain` | `spa run verification/wait_for_shc_captain` (skip without `deployer`) |
| 7 | `test_07_check_shc_health` | `spa run verification/check_shc_health` (skip without `deployer`) |
| 8 | `test_08_verify_data_flow` | `spa run verification/verify_data_flow` |
| 9 | `test_09_verify_hec` | `spa run verification/verify_hec --yes` (playbook skips when no host has `hec:`) |
| 10 | `test_10_verify_app_deployment` | `spa run verification/verify_app_deployment -- -e fail_on_mismatch=true` |

Teardown (fixture): `spa destroy --yes`.

AWS suite topologies (29 hosts when run together):

| id | Notes | Suite OS |
|----|--------|----------|
| `single_node` | S1, combined SH+IDX | Ubuntu |
| `2idx_sh_ds_hf_uf` | D1 standalone indexers, SH+MC+LM, DS, HF, UF; extra UFs Ubuntu+RHEL | Amazon Linux |
| `cm_2idxc_3shc_ds` | C3, integer RF/SF, no site | RHEL |
| `2site_idxc_shc_mc_ds_sh_hf_uf_itsi_apps` | Kitchen sink, `idxc_rf: 2`, ITSI apps | RHEL |

One guest family for every Enterprise host in a composed config (including HF). Only extra **UF** hosts from the suite may differ.

### Legacy: Standalone Verification (`test_verification.py`)

For standalone verification against existing infrastructure:

| Test | Description | Condition |
|------|-------------|-----------|
| `test_01_verify_data_flow` | Check _internal index | Always |
| `test_02_check_idxc_health` | Indexer cluster health | `cluster_manager` role |
| `test_03_check_shc_health` | Search head cluster health | `deployer` role |
| `test_07_verify_hec` | Ingest and search one HEC event per token | Always (playbook skips when no host has `hec:`) |

### Schema Validation (`test_schema.py`)

Unit tests for YAML configuration schema validation using Pydantic. These tests run **without infrastructure** and validate the `splunk_config.yml` structure before Ansible processing.

| Category | Tests | Description |
|----------|-------|-------------|
| Valid Configs | 10 | Minimal, full, all roles, clusters |
| Invalid Configs | 16 | Missing fields, wrong types, business rule violations |
| Cluster Configs | 3 | IDXC and SHC configurations |
| Multi-Role Hosts | 2 | Hosts with multiple roles |

**Run schema tests:**
```bash
./tests/run_schema_tests.sh
./tests/run_schema_tests.sh -v          # Verbose output
./tests/run_schema_tests.sh -k "invalid" # Only invalid config tests
```

**Key validations:**
- `plugin` must be `splunk-platform-automator`
- `splunk_hosts` required with at least one host
- Valid roles: `cluster_manager`, `deployer`, `deployment_server`, `heavy_forwarder`, `indexer`, `license_manager`, `monitoring_console`, `search_head`, `universal_forwarder`, `universal_forwarder_windows`
- `cluster_manager` requires `idxcluster`
- `site` only allowed for `indexer`, `search_head`, `cluster_manager`
- `TestAppDeploymentConfig`: valid/optional/empty `splunk_app_deployment`; top-level booleans such as `deploymentclient_check` (default `true`) validated when present

### App deployment tests (`test_app_deployment.py`)

Automated tests for app deployment **without real Splunk hosts or AWS**. Pre-deployment checks run `spa run splunk_apps_deploy --yes -- --limit localhost`:

| Test | Description |
|------|-------------|
| `test_same_app_name_multiple_entries_with_different_target_roles_valid` | Same app with different target_roles validates (deployment target calculated from roles) |
| `test_valid_config_no_splunkbase_passes_pre_deployment` | Pre-deployment passes with valid config and no Splunkbase apps |
| `test_splunkbase_app_without_credentials_fails` | Playbook fails when Splunkbase app is present and credentials are unset |

Fixtures (extra-vars) live in `tests/configs/app_deployment/*.yml`. Schema tests for `splunk_app_deployment` are in `test_schema.py` (`TestAppDeploymentConfig`).

Pre-deployment playbook tests use an isolated subprocess environment (no `SPLUNKBASE_*` inheritance), so they are safe to run in CI even when deployment secrets are exported globally. Splunkbase is not contacted — only the credential assert in the first play is exercised.

**Run app deployment tests:**
```bash
./tests/run_app_deployment_tests.sh
./tests/run_app_deployment_tests.sh -v
./tests/run_app_deployment_tests.sh -k "SchemaValidation"
```

Playbook tests run through `spa run` (ansible-core in the test venv).

### ITSI content pack tests (`test_itsi_content_pack.py`)

Static checks on `apps_itsi_content_pack` role tasks and defaults (single-app synthesis, `content_pack_install` default). Config validation: `test_schema.py` (`TestAppDeploymentConfig`, `-k itsi_content_pack`). Scope/routing: `test_app_scope_scenarios.py` (`itsi_content_pack`, `itsi_content_pack_single_app`, `itsi_standalone_sh`, `itsi_multi_shc`).

**Run:**
```bash
./tests/run_itsi_content_pack_tests.sh
./tests/run_itsi_content_pack_tests.sh -v
```

Or run suites individually:
```bash
pytest tests/test_itsi_content_pack.py -v
pytest tests/test_schema.py -k itsi_content_pack -v
pytest tests/test_app_scope_scenarios.py -k "itsi_content_pack or itsi_standalone_sh or itsi_multi_shc" -v
```

### App scope scenario tests (`test_app_scope_scenarios.py`)

Scenario-based tests for app scope (no SSH or real hosts). Each scenario under `tests/configs/app_scope/<name>/splunk_config.yml` runs `spa run verification/debug_app_scope -- -e run_scope_locally=true` and asserts on the produced scope JSON (direct_scope, deployer, cluster_manager, deployment_server). Scenarios: minimal_direct, ds_only, deployer_shc, ds_with_hosts_whitelist, itsi_content_pack, itsi_content_pack_single_app, state_absent.

**Run app scope scenario tests:**
```bash
./tests/run_app_scope_scenarios_tests.sh
./tests/run_app_scope_scenarios_tests.sh -v
./tests/run_app_scope_scenarios_tests.sh -k "minimal_direct"
```

Requires `ansible-core`, `jmespath`, and `lxml` in the test venv (installed by the run script). Output: `tests/configs/app_scope/output/<scenario>_scope.json`.

### Adding an app-scope scenario

App-scope scenarios live under `tests/configs/app_scope/<name>/`. Each has a distilled `splunk_config.yml` and usually `expected_scope.json`. Live AWS topologies live under `tests/deployment/topologies/`, not as a flat `tests/configs/*.yml` file.

1. Scan existing `# Scenario:` headers under `tests/configs/app_scope/` so the pattern is not already covered.
2. Create `tests/configs/app_scope/<name>/splunk_config.yml` with a header comment (scenario name, topology, what it verifies). Distill the source config: keep the active parts, remove vault values and commented blocks, and keep infrastructure minimal.
3. Run `./tests/run_app_scope_scenarios_tests.sh -k "<name>" -v`. After the first run, update the snapshot with `UPDATE_SCOPE_SNAPSHOTS=1 ./tests/run_app_scope_scenarios_tests.sh -k "snapshot and <name>" -v`. Review the diff before committing.
4. Add scenario-specific assertions in `test_app_scope_scenarios.py` when the snapshot is not enough.

## Running Tests

### When to run which runner

- While coding: the new test, then existing tests for every touched module. Standing tests are behavior and standards; TDD-only scaffolding does not ship.
- CLI surface (parser, help, routing, schema, session, or provider contracts): `./tests/run_cli_tests.sh` (`pytest -m "local and cli"`). Defaults to `-n auto`; pass `-n 1` for serial. That local command still runs both CLI tracks; CI sets `SPA_CLI_MARKEXPR` to `local and cli and not cli_runtime` (`CLI help`) or `local and cli and cli_runtime` (`CLI runtime`). `run_spa` / `spa_env` pin `SPA_VENV_DIR` to `tests/.venv` unless a test overrides it; `spa init` reuses that venv instead of cloning `SPA_HOME/.venv`.
- Playbook-spawning tests: `./tests/run_ansible_tests.sh` (`pytest -m "local and ansible"`). That local command still runs the full ansible track; CI sets `SPA_ANSIBLE_MARKEXPR` to `local and ansible and app_scope and not app_scope_b` (`Ansible app-scope`), `local and ansible and app_scope_b` (`Ansible app-scope B`), `local and ansible and env_scaffold` (`Ansible env-scaffold`), or `local and ansible and not app_scope and not app_scope_b and not env_scaffold` (`Ansible remaining`). The same four chunks run on Python 3.15. `test_spa_jsonl_callback.py` keeps a direct `ansible-playbook` of a fixture that is not a `spa run` catalog playbook.
- Other local tests (schema, docs, runlog, venv, paths, licenses, secrets, pack/install): `./tests/run_unit_tests.sh` (`pytest -m "local and not cli and not ansible"`).
- Optional before a PR: `./tests/run_local_tests.sh` (`pytest -m local`). Defaults to `-n auto`; pass `-n 1` for serial, or `--durations=25` to match CI durations.
- Merge gate: PR CI jobs `Syntax`, `Semgrep`, `CLI help`, `CLI runtime`, `Unit tests`, and the Ansible chunks on 3.11 and 3.15 (`Ansible app-scope`, `Ansible app-scope B`, `Ansible env-scaffold`, `Ansible remaining`, plus the `(3.15)` names). Each pytest job uses `-n auto --durations=25`. Push CI on `master` is background insurance. Local Semgrep (same flags as CI): `semgrep scan --config p/python --config p/security-audit --severity ERROR --error --metrics=off`.
- Contributor agents unsandbox `pytest` and `./tests/run_*.sh` (Shell `required_permissions: ["all"]` on the first attempt).

Live AWS (`@pytest.mark.aws`) and live CCM are not in PR CI. The CLI suite includes mocked CCM.

### Run SPA CLI Release Tests

```bash
./tests/run_cli_tests.sh
./tests/run_cli_tests.sh -v
# Equivalent after activating the test venv:
pytest -m "local and cli" tests/
```

This fast suite checks every public command and subcommand help surface, every
alias, the complete agent schema, argument routing, confirmation behavior, env
initialization, session calls, and mocked provider dispatch. It does not contact
AWS, SSH to hosts, or execute deployment playbooks.

### Run All Local Tests (no AWS)

```bash
./tests/run_local_tests.sh
./tests/run_local_tests.sh -v          # verbose test names
./tests/run_local_tests.sh -s          # show print/log output (no capture)
./tests/run_local_tests.sh -sv -k "deployer_shc_whitelist"
./tests/run_local_tests.sh --durations=25   # CI-shaped durations
./tests/run_local_tests.sh -n 1             # serial debug
```

Runs all tests marked `@pytest.mark.local` in a single pytest invocation (schema, secret resolver, app deployment, app scope scenarios, ITSI content pack). Does **not** run `@pytest.mark.aws` tests (deployment, verification). Local runners default to `-n auto`; pass `-n 1` for serial.

Or run directly (from project root):

```bash
pytest -m local tests/
pytest -m "local and itsi" tests/
pytest -m aws tests/          # deployment / verification only
```

### Run All Deployment Tests

The umbrella runs **every suite file** under `tests/deployment/suites/` (today only `aws.yml`). AWS-only is `run_deployment_aws_tests.sh`. Both default to `-n` matching the topology count and `--dist=loadgroup`.

```bash
./tests/run_deployment_tests.sh
./tests/run_deployment_aws_tests.sh
```

### Run Specific Topology Only
```bash
./tests/run_deployment_tests.sh -k "single_node"
```

### Run in Parallel (override workers)
```bash
./tests/run_deployment_tests.sh -n 2
```

### Run Verification Against Local Deployment

Run verification tests against an existing deployment (no workspace creation, no teardown):

```bash
./tests/run_verification_tests.sh --local -s
```

This mode:
- Uses `$SPA_ENV_DIR/config/splunk_config.yml` (or `config/` on the project root)
- Does NOT compose a suite topology or create a temp env
- Does NOT destroy infrastructure after tests
- Calls `bin/spa run verification/...`

### Run Standalone Verification Tests
```bash
./tests/run_verification_tests.sh
```

### Show Output in Real-time
```bash
./tests/run_deployment_tests.sh -s
```

### Run with Verbose Output
```bash
./tests/run_deployment_tests.sh -v
```

### Run Specific Test Steps Only
Use `-k` with test names to run only specific steps:

```bash
# Run only test 1 (prepare config)
./tests/run_deployment_tests.sh -k "test_01"

# Run only tests 1 and 2 (compose+validate, then deploy)
./tests/run_deployment_tests.sh -k "test_01 or test_02"

# Run tests 1-3 for a specific topology
./tests/run_deployment_tests.sh -k "(test_01 or test_02 or test_03) and single_node"
```

### Combine Options
```bash
# Run tests 1-2 in parallel with verbose output
./tests/run_deployment_tests.sh -n 2 -v -k "test_01 or test_02"
```

### App deployment

`spa deploy --yes` deploys apps. **test_10** runs `spa run verification/verify_app_deployment`. Operator behavior and routing are summarized in [Apps](../docs/apps.md). Local ansible-marker tests also drive `create_linkpage`, `verification/debug_app_scope`, and `splunk_apps_deploy` through `spa run` ([#165](https://github.com/splunk/splunk-platform-automator/issues/165)). `test_spa_jsonl_callback.py` keeps a direct `ansible-playbook` of a fixture that is not a `spa run` catalog playbook.

## Live suite layout

Same merge order as `spa init --example TOPOLOGY --provider PROVIDER`: provider keys first, topology keys win, then the suite hook fills identity (AMI today; later CCM OS / VirtualBox box). Do **not** call `compose_example_config` on these files: spa init topologies forbid `splunk_app_deployment` and top-level `os`. The live composer forbids only provider roots on topologies (`terraform`, `ccm`, `virtualbox`, `aws`) and forbids `splunk_hosts` / cluster lists on provider files.

```yaml
# tests/deployment/suites/aws.yml
provider: aws
pytest_mark: aws
topologies:
  - id: single_node
    os: ubuntu
```

The AWS hook runs `spa --agent provider aws latest-ami --region REGION --os KEY` (or `--os all` when extra UFs need several guests). It writes `terraform.aws.ami_id` / `ssh_username` and `os.packages` (Ubuntu `[acl, policykit-1]`; RHEL/Amazon Linux `[acl, polkit]`). No committed `ami_id`.

### Adding a CCM or VirtualBox suite later

1. Add `tests/deployment/providers/ccm.yml` or `virtualbox.yml` (no hosts).
2. Add `tests/deployment/suites/ccm.yml` listing a subset of the same topology `id`s (VirtualBox can list only `single_node`).
3. Register a hook in `tests/deployment_provider.py` (`compose_identity`).
4. Optionally add `run_deployment_ccm_tests.sh` / `run_deployment_vbox_tests.sh`. The umbrella picks up new suite files automatically.

Do not put extra UFs on the topology YAML; they belong on the suite so CCM/VBox do not inherit three forwarder AMIs.

## Adding a live topology

1. Create `tests/deployment/topologies/<id>.yml` with hosts, clusters, apps, and licenses. No `terraform:` / `ccm:` / `virtualbox:`.
2. Add the `id` under the suite that should run it, with `os:` (and `extra_ufs:` only if mixed UF guests are required).
3. Keep one Enterprise guest family per composed config. Extra UF hosts from the suite may differ.

## Workspace Isolation

Each live topology gets:
- **Isolated `SPA_ENV_DIR`** in a temp directory (inventory + Terraform state + `splunk_config.yml`)
- **This checkout as `SPA_HOME`** (no per-test framework clone or venv)
- **Unique SplunkEnvID** for AWS resource tagging

Teardown runs `spa destroy --yes` and then removes the temp env dir.

## Troubleshooting

### Keep Workspace for Debugging
Comment out the cleanup in `conftest.py` to preserve temp env directories:
```python
# In WorkspaceManager.cleanup():
# shutil.rmtree(self._workspace_root, ignore_errors=True)
```

### View Test Output
```bash
./tests/run_deployment_tests.sh -s --tb=long
```

### Check AWS Resources
Look for resources tagged with `SplunkEnvID: test-<timestamp>-<uuid>`
