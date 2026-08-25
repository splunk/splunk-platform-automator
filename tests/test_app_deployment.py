"""
Automated tests for Splunk app deployment (deploy_splunk_apps.yml).

These tests run the app deployment playbook with static localhost inventory and
extra-vars fixtures. No real Splunk hosts or AWS are required.

- Schema: duplicate (name, deployment_target) and per-app validation (schema.py).
- Pre-deployment: Splunkbase credentials, valid config without Splunkbase (playbook).
- Schema tests for splunk_app_deployment structure live in test_schema.py (TestAppDeploymentConfig).
"""

import os
import json
import subprocess
import yaml
import pytest

pytestmark = pytest.mark.local


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_deployment_config_path(name: str) -> str:
    return os.path.join(
        _project_root(), "tests", "configs", "app_deployment", f"{name}.yml"
    )


def _run_deploy_playbook(
    extra_vars_path: str,
    env: dict | None = None,
    ansible_config: str | None = None,
    extra_vars_dict: dict | None = None,
    *,
    expect_failure: bool = False,
) -> subprocess.CompletedProcess:
    """Run ansible/deploy_splunk_apps.yml with -i localhost,. Extra vars from extra_vars_path (-e @file) unless extra_vars_dict is set (then -e json.dumps(extra_vars_dict))."""
    root = _project_root()
    playbook = os.path.join(root, "ansible", "deploy_splunk_apps.yml")
    if extra_vars_dict is not None:
        extra_args = ["-e", json.dumps(extra_vars_dict)]
    else:
        extra_args = ["-e", f"@{os.path.abspath(extra_vars_path)}"]
    cmd = [
        "ansible-playbook",
        playbook,
        "-i", "localhost,",
    ] + extra_args
    # When caller passes env, use it as the subprocess env base so omitted vars (e.g. SPLUNKBASE_*) are actually unset.
    ansible_env = (env.copy() if env is not None else os.environ.copy())
    cfg_path = os.path.abspath(ansible_config or _test_ansible_config_path())
    ansible_env["ANSIBLE_CONFIG"] = cfg_path
    tests_dir = os.path.join(root, "tests")
    ansible_env.setdefault("ANSIBLE_LOCAL_TMP", os.path.join(tests_dir, ".ansible_tmp"))
    os.makedirs(ansible_env["ANSIBLE_LOCAL_TMP"], exist_ok=True)
    result = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        env=ansible_env,
        timeout=60,
    )
    if result.returncode != 0 and not expect_failure:
        print("\n--- deploy_splunk_apps.yml output ---")
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
    config = {
        "plugin": "splunk-platform-automator",
        "splunk_hosts": splunk_hosts or [{"name": "h1", "roles": ["indexer"]}],
        "splunk_app_deployment": splunk_app_deployment,
    }
    if splunk_defaults is not None:
        config["splunk_defaults"] = splunk_defaults
    validate_config(config)


def _normal_app(**overrides) -> dict:
    """Minimal valid normal app for schema tests (field under test can override)."""
    app = {"name": "MyApp", "source": "local", "target_roles": ["search_head"]}
    app.update(overrides)
    return app


def _itsi_splunk_hosts() -> list:
    return [{"name": "h1", "roles": ["search_head", "indexer", "license_manager"]}]


def _itsi_splunk_defaults() -> dict:
    return {"splunk_license_file": ["Splunk_Enterprise.lic"]}


def _test_ansible_config_path() -> str:
    return os.path.abspath(
        os.path.join(_project_root(), "tests", "configs", "app_deployment", "ansible_app_deployment.cfg")
    )


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
            _validate_config_with_app_deployment(data["splunk_app_deployment"])
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
                "apps": [{"name": "MyApp", "target_roles": ["search_head", "invalid_role"]}]
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
    """Test pre-deployment check behaviour of deploy_splunk_apps.yml."""

    def test_valid_config_no_splunkbase_passes_pre_deployment(self):
        """Pre-deployment play passes when config is valid and no Splunkbase apps need creds."""
        path = _app_deployment_config_path("valid_no_splunkbase")
        assert os.path.isfile(path), f"Fixture missing: {path}"
        config_path = _test_ansible_config_path()
        assert os.path.isfile(config_path), f"Config missing: {config_path}"
        result = _run_deploy_playbook(path, ansible_config=config_path)
        assert result.returncode == 0, (
            "Pre-deployment should pass; later plays are skipped (no role_* hosts). "
            f"stdout: {result.stdout[-1500:]!r}"
        )

    def test_splunkbase_app_without_credentials_fails(self):
        """Playbook must fail when a Splunkbase app is present and credentials are not set."""
        path = _app_deployment_config_path("splunkbase_no_creds")
        assert os.path.isfile(path), f"Fixture missing: {path}"
        with open(path) as f:
            extra_vars = yaml.safe_load(f)
        # Force the playbook to run the Splunkbase credential check (avoids when-condition visibility issues with -e)
        extra_vars = {**(extra_vars or {}), "_splunkbase_credentials_check": True}
        config_path = _test_ansible_config_path()
        assert os.path.isfile(config_path), f"Config missing: {config_path}"
        # Pass extra vars as JSON so Ansible definitely receives splunk_app_deployment (avoids -e @file quirks)
        env = os.environ.copy()
        env.pop("SPLUNKBASE_USERNAME", None)
        env.pop("SPLUNKBASE_PASSWORD", None)
        result = _run_deploy_playbook(
            path,
            env=env,
            ansible_config=config_path,
            extra_vars_dict=extra_vars,
            expect_failure=True,
        )
        assert result.returncode != 0, "Playbook should fail when Splunkbase app has no credentials"
        combined = (result.stdout or "") + (result.stderr or "")
        assert "Splunkbase" in combined and ("credentials" in combined or "SPLUNKBASE" in combined)
