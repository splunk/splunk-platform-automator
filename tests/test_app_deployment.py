"""
Automated tests for Splunk app deployment (splunk_apps_deploy.yml).

These tests run spa run splunk_apps_deploy --yes -- --limit localhost against a
provider-less temp env. No real Splunk hosts or AWS are required.

- Schema: duplicate (name, deployment_target) and per-app validation (schema.py).
- Pre-deployment: Splunkbase credentials, valid config without Splunkbase (playbook).
- Schema tests for splunk_app_deployment structure live in test_schema.py (TestAppDeploymentConfig).
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml
import pytest

from spa_testutil import PROJECT_ROOT, SPA, spa_env, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.ansible]


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_deployment_config_path(name: str) -> str:
    return os.path.join(
        _project_root(), "tests", "configs", "app_deployment", f"{name}.yml"
    )


def test_ansible_app_roles_default_omitted_source_to_splunkbase():
    """CFG-APP-002: every deployment source lookup uses the Splunkbase default."""
    roles_dir = os.path.join(_project_root(), "ansible", "roles")
    text = "\n".join(
        open(os.path.join(root, name), encoding="utf-8").read()
        for root, _, names in os.walk(roles_dir)
        for name in names
        if name.endswith((".yml", ".yaml"))
        and os.path.relpath(root, roles_dir).split(os.sep, 1)[0].startswith("apps_")
    )
    assert "default('local')" not in text
    assert "{{ app_item.source }}" not in text
    assert "source | default('')" not in text
    deploy_playbook = open(
        os.path.join(_project_root(), "ansible", "splunk_apps_deploy.yml"),
        encoding="utf-8",
    ).read()
    assert "rejectattr('source', 'defined')" in deploy_playbook
    assert "selectattr('source', 'defined')" in deploy_playbook


def _ensure_software_stubs(stub_dir: Path) -> None:
    (stub_dir / "spa_ci_stub" / "org_s2_indexer_indexes").mkdir(parents=True, exist_ok=True)
    (stub_dir / "spa_ci_stub" / "org_cluster_manager_base").mkdir(parents=True, exist_ok=True)
    for name in (
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
        "splunk-9.4.0-ci-linux-amd64.tgz",
        "splunkforwarder-9.4.0-ci-linux-amd64.tgz",
    ):
        path = stub_dir / name
        if not path.exists():
            path.write_text("# CI stub\n", encoding="utf-8")


def _run_deploy_playbook(
    extra_vars_path: str,
    extra_vars_dict: dict | None = None,
    *,
    env_root: Path,
    expect_failure: bool = False,
    ansible_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run spa run splunk_apps_deploy --yes -- --limit localhost against a provider-less env."""
    dest = write_min_env(env_root)
    if extra_vars_dict is not None:
        payload = dict(extra_vars_dict)
    else:
        with open(extra_vars_path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    creds_check = bool(payload.pop("_splunkbase_credentials_check", False))
    config = {
        "plugin": "splunk-platform-automator",
        "splunk_defaults": {
            "splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
        },
        "splunk_hosts": [{"name": "h1", "roles": ["search_head", "indexer"]}],
        "splunk_app_deployment": payload["splunk_app_deployment"],
    }
    (dest / "config" / "splunk_config.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    stub = PROJECT_ROOT / "tests" / "fixtures" / "baseconfig"
    _ensure_software_stubs(stub)
    ansible_tmp = env_root / "ansible_tmp"
    ansible_tmp.mkdir(exist_ok=True)
    remote_tmp = ansible_tmp / "remote"
    remote_tmp.mkdir(exist_ok=True)
    env = spa_env(
        {
            "SPA_HOME": str(PROJECT_ROOT),
            "SPA_ENV_DIR": str(dest),
            "SPA_VENV_DIR": str(PROJECT_ROOT / "tests" / ".venv"),
            "SPA_SOFTWARE_DIR": str(stub),
            "SPA_BASECONFIG_DIR": str(stub),
            "SPLUNK_ADMIN_PASSWORD": "app-deploy-admin",
            "ANSIBLE_LOCAL_TEMP": str(ansible_tmp),
            "ANSIBLE_REMOTE_TEMP": str(remote_tmp),
        }
    )
    for key in list(env):
        if key.startswith("SPLUNKBASE_"):
            env.pop(key, None)
    cmd = [sys.executable, str(SPA), "run", "splunk_apps_deploy", "--yes"]
    if ansible_output:
        cmd.append("--ansible-output")
    # Plugin inventory has no localhost; -i localhost, keeps later role_* plays
    # from SSH while the pre-deployment play still has a host.
    cmd.extend(
        [
            "--",
            "--limit",
            "localhost",
            "-i",
            "localhost,",
            "-e",
            "@%s" % (dest / "config" / "splunk_config.yml"),
        ]
    )
    if creds_check:
        cmd.extend(["-e", "_splunkbase_credentials_check=true"])
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if result.returncode != 0 and not expect_failure:
        print("\n--- splunk_apps_deploy.yml output ---")
        print("STDOUT:", result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        print("STDERR:", result.stderr[-1500:] if len(result.stderr) > 1500 else result.stderr)
    return result


# -----------------------------------------------------------------------------
# Schema validation tests (duplicate and per-app checks in schema.py)
# -----------------------------------------------------------------------------


def _get_validate_config():
    """Import and return validate_config and ConfigValidationError from schema."""
    import sys
    inv_dir = os.path.join(_project_root(), "ansible", "plugins", "inventory")
    if inv_dir not in sys.path:
        sys.path.insert(0, inv_dir)
    from schema import validate_config, ConfigValidationError
    return validate_config, ConfigValidationError


def _validate_config_with_app_deployment(
    splunk_app_deployment: dict,
    splunk_hosts: list | None = None,
    splunk_defaults: dict | None = None,
) -> None:
    """Build minimal config and run schema validate_config; raises on failure."""
    validate_config, _ = _get_validate_config()
    defaults = dict(splunk_defaults or {})
    defaults.setdefault(
        "splunk_admin_password",
        "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}",
    )
    config = {
        "plugin": "splunk-platform-automator",
        "splunk_hosts": splunk_hosts or [{"name": "h1", "roles": ["indexer"]}],
        "splunk_app_deployment": splunk_app_deployment,
        "splunk_defaults": defaults,
    }
    validate_config(config)


def _normal_app(**overrides) -> dict:
    """Minimal valid normal app for schema tests (field under test can override)."""
    app = {"name": "MyApp", "source": "local", "target_roles": ["search_head"]}
    app.update(overrides)
    return app


def _itsi_splunk_hosts() -> list:
    return [{
        "name": "h1",
        "roles": ["search_head", "indexer", "license_manager"],
        "os": {"packages": ["java-21-openjdk"]},
    }]


def _itsi_splunk_defaults() -> dict:
    return {"splunk_license_file": ["Splunk_Enterprise.lic"]}


class TestAppDeploymentSchemaValidation:
    """Test app deployment validators in schema.py (per-app fields)."""

    def test_same_app_name_twice_via_deployment_server_raises(self):
        """Same app name twice when both are managed by the same deployment server must raise."""
        path = _app_deployment_config_path("duplicate_apps")
        assert os.path.isfile(path), f"Fixture missing: {path}"
        with open(path) as f:
            data = yaml.safe_load(f)
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment(
                data["splunk_app_deployment"],
                splunk_hosts=[
                    {"name": "ds", "roles": ["deployment_server"]},
                    {"name": "sh1", "roles": ["search_head"]},
                    {"name": "uf1", "roles": ["universal_forwarder"]},
                ],
            )
        assert "duplicate" in str(exc_info.value).lower()

    def test_same_app_name_one_direct_one_ds_allowed(self):
        """Same app name once via direct and once via deployment server (auto) is allowed."""
        _validate_config_with_app_deployment({
            "apps": [
                {"name": "Splunk_TA_nix", "source": "local", "deployment_target": "direct", "target_roles": ["search_head"]},
                {"name": "Splunk_TA_nix", "source": "local", "deployment_target": "auto", "target_roles": ["universal_forwarder"]},
            ]
        })  # must not raise

    def test_app_missing_name_raises(self):
        """Schema validation must raise when an app entry has no 'name'."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{"source": "local", "target_roles": ["search_head"]}]
            })
        assert "name" in str(exc_info.value).lower()

    def test_app_invalid_source_raises(self):
        """Schema validation must raise when source is not local or splunkbase."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(source="invalid")]
            })
        assert "source" in str(exc_info.value).lower()

    def test_splunkbase_app_without_app_id_raises(self):
        """Schema validation must raise when source is splunkbase but app_id is missing."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{"name": "MyApp", "source": "splunkbase", "target_roles": ["indexer"]}]
            })
        err_msg = str(exc_info.value).lower()
        assert "app_id" in err_msg and "splunkbase" in err_msg

    def test_omitted_source_defaults_to_splunkbase_and_requires_app_id(self):
        """CFG-APP-002: omitted source has Splunkbase validation semantics."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{"name": "MyApp", "target_roles": ["indexer"]}]
            })
        err_msg = str(exc_info.value).lower()
        assert "app_id" in err_msg and "splunkbase" in err_msg

    def test_splunkbase_app_with_non_numeric_app_id_raises(self):
        """Schema validation must raise when source is splunkbase but app_id is not a number."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{"name": "MyApp", "source": "splunkbase", "app_id": "not-a-number", "target_roles": ["indexer"]}]
            })
        err_msg = str(exc_info.value).lower()
        assert "app_id" in err_msg and ("number" in err_msg or "integer" in err_msg)

    def test_app_invalid_deployment_target_raises(self):
        """Schema validation must raise when deployment_target is not direct or auto."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(deployment_target="invalid")]
            })
        assert "deployment_target" in str(exc_info.value).lower()

    def test_app_invalid_state_raises(self):
        """Schema validation must raise when state is not installed or absent."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(state="remove")]
            })
        err_msg = str(exc_info.value).lower()
        assert "state" in err_msg and ("installed" in err_msg or "absent" in err_msg)

    def test_app_version_latest_valid(self):
        """Version 'latest' (any case) is valid."""
        _validate_config_with_app_deployment({
            "apps": [_normal_app(source="splunkbase", app_id=352, version="latest")]
        })
        _validate_config_with_app_deployment({
            "apps": [_normal_app(source="splunkbase", app_id=352, version="Latest")]
        })

    def test_app_version_number_valid(self):
        """Version as dotted number (e.g. 4.21.1, 10.1.0) is valid."""
        _validate_config_with_app_deployment({
            "apps": [_normal_app(source="splunkbase", app_id=352, version="4.21.1")]
        })
        _validate_config_with_app_deployment({
            "apps": [_normal_app(source="splunkbase", app_id=352, version="10.1.0")]
        })

    def test_app_version_invalid_raises(self):
        """Schema validation must raise when version is not 'latest' or a version number."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(source="splunkbase", app_id=352, version="dev")]
            })
        err_msg = str(exc_info.value).lower()
        assert "version" in err_msg

    def test_splunk_app_deployment_direct_vars_valid(self):
        """Valid top-level splunk_app_deployment vars (target_download, cache_downloads, etc.) pass."""
        _validate_config_with_app_deployment({
            "target_download": False,
            "cache_downloads": True,
            "backup_apps_before_update": False,
            "temp_dir": "/tmp/splunk_apps",
            "backup_location": "/tmp/backups",
            "download_timeout": 120,
            "retry_count": 3,
            "restart_timeout": 300,
            "apps": [_normal_app()],
        })

    def test_splunk_app_deployment_target_download_not_bool_raises(self):
        """splunk_app_deployment.target_download must be boolean when present."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "target_download": "yes",
                "apps": [_normal_app()],
            })
        assert "target_download" in str(exc_info.value).lower()

    def test_splunk_app_deployment_temp_dir_empty_raises(self):
        """splunk_app_deployment.temp_dir must be non-empty string when present."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "temp_dir": "   ",
                "apps": [_normal_app()],
            })
        assert "temp_dir" in str(exc_info.value).lower()

    def test_splunk_app_deployment_download_timeout_positive_raises(self):
        """splunk_app_deployment.download_timeout must be positive integer when present."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "download_timeout": 0,
                "apps": [_normal_app()],
            })
        assert "download_timeout" in str(exc_info.value).lower()

    def test_premium_app_itsi_valid_no_target_roles(self):
        """Premium app (premium_app: itsi) is valid without target_roles; deployment is role-based."""
        _validate_config_with_app_deployment({
            "apps": [{
                "name": "Splunk IT Service Intelligence",
                "source": "splunkbase",
                "app_id": 1841,
                "version": "4.21.1",
                "premium_app": "itsi",
            }]
        }, splunk_hosts=_itsi_splunk_hosts(), splunk_defaults=_itsi_splunk_defaults())

    def test_premium_app_invalid_raises(self):
        """Schema validation must raise when premium_app is not an allowed value (e.g. not itsi)."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{"name": "SomeApp", "source": "splunkbase", "app_id": 123, "premium_app": "other"}]
            })
        err_msg = str(exc_info.value).lower()
        assert "premium_app" in err_msg

    def test_premium_app_with_target_roles_raises(self):
        """Schema validation must raise when premium_app is set and target_roles is also set (target_roles not allowed on premium apps)."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{
                    "name": "Splunk IT Service Intelligence",
                    "source": "splunkbase",
                    "app_id": 1841,
                    "premium_app": "itsi",
                    "target_roles": ["search_head"],
                }]
            })
        err_msg = str(exc_info.value).lower()
        assert "target_roles" in err_msg and "premium_app" in err_msg

    def test_app_invalid_target_role_raises(self):
        """Schema validation must raise when target_roles contains an invalid role."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [{
                    "name": "MyApp",
                    "source": "local",
                    "target_roles": ["search_head", "invalid_role"],
                }]
            })
        err_msg = str(exc_info.value).lower()
        assert "target_roles" in err_msg or "invalid" in err_msg

    def test_customizations_valid_structure_passes(self):
        """Valid customizations (remove, local_configs, run_playbook, extra_vars) pass validation."""
        _validate_config_with_app_deployment({
            "apps": [{
                "name": "Splunk_TA_nix",
                "source": "splunkbase",
                "app_id": 833,
                "target_roles": ["search_head"],
                "customizations": {
                    "remove": ["default/indexes.conf"],
                    "local_configs": {
                        "inputs.conf": {"tcp://5514": {"disabled": 0}}
                    },
                    "run_playbook": "ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml",
                    "extra_vars": {"ta_nix_script_index": "main"},
                },
            }]
        })

    def test_customizations_not_dict_raises(self):
        """Schema validation must raise when customizations is not a dict."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(customizations=["remove", "local_configs"])]
            })
        assert "customizations" in str(exc_info.value).lower()

    def test_customizations_remove_not_list_raises(self):
        """Schema validation must raise when customizations.remove is not a list."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(customizations={"remove": "default/inputs.conf"})]
            })
        err_msg = str(exc_info.value).lower()
        assert "customizations" in err_msg and "remove" in err_msg

    def test_customizations_local_configs_sections_must_be_dict_raises(self):
        """Schema validation must raise when local_configs filename value is not section->options dict."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(customizations={"local_configs": {"inputs.conf": "not-a-dict"}})]
            })
        err_msg = str(exc_info.value).lower()
        assert "local_configs" in err_msg

    def test_customizations_run_playbook_and_run_role_both_set_raises(self):
        """Schema validation must raise when both run_playbook and run_role are set."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(customizations={
                    "run_playbook": "ansible/foo.yml",
                    "run_role": "my.role",
                })]
            })
        err_msg = str(exc_info.value).lower()
        assert "run_playbook" in err_msg and "run_role" in err_msg

    def test_customizations_extra_vars_not_dict_raises(self):
        """Schema validation must raise when customizations.extra_vars is not a dict."""
        _, ConfigValidationError = _get_validate_config()
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_config_with_app_deployment({
                "apps": [_normal_app(customizations={
                    "run_playbook": "ansible/foo.yml",
                    "extra_vars": ["a"],
                })]
            })
        assert "extra_vars" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# Playbook execution tests (pre-deployment checks only; later plays have no hosts)
# -----------------------------------------------------------------------------


class TestAppDeploymentPreDeploymentChecks:
    """Test pre-deployment check behaviour of splunk_apps_deploy.yml.

    Subprocess env strips SPLUNKBASE_* so tests pass in CI even when deployment
    secrets are exported globally.
    """

    def test_valid_config_no_splunkbase_passes_pre_deployment(self, tmp_path):
        """Pre-deployment play passes when config is valid and no Splunkbase apps need creds."""
        path = _app_deployment_config_path("valid_no_splunkbase")
        assert os.path.isfile(path), f"Fixture missing: {path}"
        result = _run_deploy_playbook(path, env_root=tmp_path)
        assert result.returncode == 0, (
            "Pre-deployment should pass; later plays are skipped (--limit localhost). "
            f"stdout: {result.stdout[-1500:]!r} stderr: {result.stderr[-1500:]!r}"
        )

    def test_splunkbase_app_without_credentials_fails(self, tmp_path):
        """Playbook must fail when a Splunkbase app is present and credentials are not set."""
        path = _app_deployment_config_path("splunkbase_no_creds")
        assert os.path.isfile(path), f"Fixture missing: {path}"
        with open(path) as f:
            extra_vars = yaml.safe_load(f)
        # Force the playbook to run the Splunkbase credential check (avoids when-condition visibility issues with -e)
        extra_vars = {**(extra_vars or {}), "_splunkbase_credentials_check": True}
        result = _run_deploy_playbook(
            path,
            extra_vars_dict=extra_vars,
            env_root=tmp_path,
            expect_failure=True,
            ansible_output=True,
        )
        assert result.returncode != 0, "Playbook should fail when Splunkbase app has no credentials"
        combined = (result.stdout or "") + (result.stderr or "")
        assert "failed" in combined
        assert "Splunkbase" in combined and ("credentials" in combined or "SPLUNKBASE" in combined)
