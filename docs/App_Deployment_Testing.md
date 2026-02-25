# Testing App Deployment

Recommendations for testing the Splunk app deployment feature (deployment server, direct, ITSI, cache, and related logic).

## Automated tests (no infrastructure)

Run the dedicated app deployment test suite from the project root:

```bash
./tests/run_app_deployment_tests.sh
```

This runs:

- **test_app_deployment.py** – Pre-deployment checks by running `deploy_splunk_apps.yml` with static inventory `localhost,` and extra-vars from `tests/configs/app_deployment/`:
  - Same app name may appear multiple times with different `target_roles`/customizations (deployment target is calculated from roles).
  - Valid config with no Splunkbase apps → first play passes.
  - Splunkbase app without credentials → playbook must fail (Splunkbase credentials message).
- **test_schema.py** – `TestAppDeploymentConfig`: valid/optional/empty `splunk_app_deployment` in the config schema.

No real Splunk hosts or AWS are required. Playbook tests need `ansible-playbook` on PATH.

---

## 1. Pre-flight checks (no inventory needed)

Run these before deploying to catch config issues early.

### Multiple entries for the same app

The same app (e.g. Splunk_TA_nix) can be defined multiple times with different `target_roles` and customizations (e.g. one for indexer cluster, one for universal_forwarder). The deployment target (DS, CM, deployer, direct) is calculated from roles and inventory at deploy time.

### Schema validation (optional)

If you use the schema tests, run them so config structure and roles are valid:

```bash
./tests/run_schema_tests.sh
```

---

## 2. Quick local test (existing inventory)

Use your current `config/splunk_config.yml` and inventory. No AWS required if you already have hosts.

### Deploy apps

```bash
ansible-playbook ansible/deploy_splunk_apps.yml -i config/splunk_config.yml -v
```

Watch for:
- Pre-deployment checks (Splunkbase credentials if needed).
- Step order: Deployment Server → Cluster Manager → Deployer → Direct.
- Handlers (e.g. Restart splunk, Reload deploy-server) when apps change.

### Verify deployment

Run the verification playbook after deploy. Report-only (default):

```bash
ansible-playbook ansible/verification/verify_app_deployment.yml -i config/splunk_config.yml
```

Strict (fail on mismatch, e.g. for CI):

```bash
ansible-playbook ansible/verification/verify_app_deployment.yml -i config/splunk_config.yml -e fail_on_mismatch=true
```

---

## 3. Scenarios worth testing manually

Cover these paths so deployment server vs direct, ITSI, and cleanup behave as expected.

| Scenario | What to do | What to check |
|---------|------------|----------------|
| **Deployment Server (DS) used for normal apps** | `splunk_app_deployment` with DS in inventory, app has `target_roles` (e.g. search_head, indexer), no `deployment_target: direct`. | Apps appear under DS `deployment-apps/`; serverclass whitelist includes sh/idx (or intended hosts); no duplicate direct deploy of same app on those hosts. |
| **Direct only (no DS)** | Remove or limit DS from inventory, or use `deployment_target: direct` for the app. | Apps go to `etc/apps` on the right hosts. |
| **ITSI install** | One app with `premium_app: itsi`, `source: splunkbase`, version set. | ITSI apps on LM, SH, standalone indexer (and deployer/CM if used); combined SH+indexer or SH+LM only gets ITSI once (SH path). |
| **ITSI remove** | Set `state: absent` for the ITSI app. | ITSI removed from LM, SH, indexer; with `cache_downloads: false`, archive and `itsi_app_confs/<version>` removed (controller or target as configured). |
| **cache_downloads: false** | Set `cache_downloads: false` under `splunk_app_deployment`. | After install/remove, temp archive and (for ITSI) `itsi_app_confs/<version>` are removed on controller/target as designed. |
| **target_download: true** | Set `target_download: true`. | Resolve/download and unarchive run on target; no upload of archive from controller. |
| **Same app, different target_roles** | Two entries for same app name with different `target_roles` (e.g. indexer vs universal_forwarder). | Both entries valid; deployment target calculated per entry from roles. |
| **backup_apps_before_update** | Set `backup_apps_before_update: true`, then update an existing app. | Backup tarball under `backup_location` before update. Default `false`: no backup. |

---

## 4. Full deployment test suite (AWS)

The existing deployment tests already run app deploy and app verification.

1. **Configure**: AWS credentials, SSH key, `tests/configs/` config (with `splunk_app_deployment` and apps if you want app coverage).
2. **Run**:
   ```bash
   ./tests/run_deployment_tests.sh
   ```
3. **Relevant steps**:
   - **test_11_deploy_splunk_apps** – runs `ansible/deploy_splunk_apps.yml`.
   - **test_17_verify_app_deployment** – runs `ansible/verification/verify_app_deployment.yml`.

To run only app deploy + verify (after Splunk is installed and configured):

```bash
./tests/run_deployment_tests.sh -k "test_11 or test_17"
```

Use a test config that defines `splunk_app_deployment.apps` so DS, deployer, and direct paths are exercised.

---

## 5. One-off verification against running deployment

If you already have a running deployment and only want to verify apps (no deploy, no teardown):

```bash
./tests/run_verification_tests.sh --local -s
```

This uses `config/splunk_config.yml` from the project root and does not create a workspace or destroy infrastructure.

---

## 6. Checklist before release

- [ ] Deploy with DS present: normal apps go via DS to intended hosts; serverclass has correct whitelist.
- [ ] Deploy with no DS: same apps go direct to standalone SH/indexer (and LM if applicable).
- [ ] ITSI install: correct roles get ITSI; combined SH+indexer / SH+LM only once (SH path).
- [ ] ITSI remove: all ITSI app dirs removed; with `cache_downloads: false`, archive and itsi_app_confs cleaned up.
- [ ] Same app with different target_roles/customizations deploys to correct targets (DS vs CM vs direct).
- [ ] `verify_app_deployment.yml` passes (report or strict) after a successful deploy.
