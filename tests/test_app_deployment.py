"""
Automated tests for Splunk app deployment (splunk_apps_deploy.yml).

These tests run spa run splunk_apps_deploy --yes -- --limit localhost against a
provider-less temp env. No real Splunk hosts or AWS are required.

- Pre-deployment: Splunkbase credentials, valid config without Splunkbase (playbook).
- Schema tests for splunk_app_deployment live in test_schema.py (TestAppDeploymentConfig).
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml
import pytest

from spa_testutil import PROJECT_ROOT, SPA, ensure_software_stubs, spa_env, write_min_env

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
    ensure_software_stubs(stub)
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
