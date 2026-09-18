"""Controller Software / baseconfig / local-app preflight for validate and deploy."""

from dataclasses import replace

import pytest

from spa.paths import resolve_spa_paths
from spa.preflight import check_controller_data, local_app_source_path
from spa_testutil import PROJECT_ROOT, seed_software_dir

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _paths(tmp_path, config, software=None, apps_dir=None):
    config_path = tmp_path / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    kwargs = dict(
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=tmp_path / "inventory",
        terraform_state_dir=tmp_path / "terraform" / "aws",
        roots_differ=True,
    )
    if software is not None:
        kwargs["software_dir"] = software
        kwargs["baseconfig_dir"] = software
    if apps_dir is not None:
        kwargs["apps_dir"] = apps_dir
    return replace(base, **kwargs)


def test_missing_software_dir_fails(tmp_path):
    missing = tmp_path / "no-software"
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=missing)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "Software directory not found" in state.reason
    assert "spa init --software-dir" in state.hint


def test_software_without_baseconfig_apps_fails(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "baseconfig apps" in state.reason


def test_seeded_software_without_local_apps_ok(tmp_path):
    software = seed_software_dir(tmp_path)
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software)
    state = check_controller_data(paths)
    assert state.ok is True
    # No source: local apps, so apps_dir was never inspected.
    assert state.apps_checked is False


def test_validate_reports_one_ok_line_per_directory(tmp_path):
    from spa.validate import controller_data_message

    software = seed_software_dir(tmp_path)
    apps = tmp_path / "apps"
    (apps / "org_some_local_app").mkdir(parents=True)
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, apps_dir=apps)
    state = check_controller_data(paths)
    assert state.apps_checked is True
    assert controller_data_message(state).splitlines() == [
        "Software OK: %s" % software,
        "Baseconfig OK: %s" % software,
        "Local apps OK: %s" % apps,
        "Custom playbooks OK: none configured",
    ]

    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software)
    without_apps = controller_data_message(check_controller_data(paths)).splitlines()
    assert without_apps[2] == "Local apps OK: none configured"


def test_validate_reports_the_default_custom_playbook_dir(tmp_path):
    from spa.playbooks import DEFAULT_ENV_PLAYBOOK_DIR, custom_playbook_dir_state
    from spa.validate import controller_data_message

    software = seed_software_dir(tmp_path)
    playbooks = tmp_path / DEFAULT_ENV_PLAYBOOK_DIR
    playbooks.mkdir()
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software)

    # No .spa.yml entry needed, and an empty folder is not an error.
    rows = custom_playbook_dir_state(tmp_path)
    assert [(row["dir"], row["ok"], row["playbooks"]) for row in rows] == [
        (DEFAULT_ENV_PLAYBOOK_DIR, True, 0)
    ]
    message = controller_data_message(check_controller_data(paths), rows)
    assert message.splitlines()[-1] == "Custom playbooks OK: %s (empty)" % playbooks

    (playbooks / "my_playbook.yml").write_text("---\n- hosts: all\n")
    rows = custom_playbook_dir_state(tmp_path)
    message = controller_data_message(check_controller_data(paths), rows)
    assert message.splitlines()[-1] == "Custom playbooks OK: %s (1 playbook)" % playbooks


def test_validate_reports_configured_custom_playbook_dirs(tmp_path):
    from spa.playbooks import custom_playbook_dir_state, list_env_stems

    extra = tmp_path / "playbooks"
    extra.mkdir()
    (extra / "my_playbook.yml").write_text("---\n- hosts: all\n")
    (tmp_path / ".spa.yml").write_text("playbook_dirs:\n  - playbooks\n")

    rows = custom_playbook_dir_state(tmp_path)
    assert [(row["dir"], row["ok"], row["playbooks"]) for row in rows] == [("playbooks", True, 1)]
    assert [stem for stem, _, _ in list_env_stems(tmp_path)] == ["playbooks/my_playbook"]


def test_validate_flags_a_missing_custom_playbook_dir(tmp_path):
    from spa.playbooks import custom_playbook_dir_state
    from spa.validate import custom_playbook_dirs_error

    (tmp_path / ".spa.yml").write_text("playbook_dirs:\n  - typo\n  - ../escape\n")
    rows = custom_playbook_dir_state(tmp_path)
    assert [(row["dir"], row["ok"]) for row in rows] == [("typo", False), ("../escape", False)]

    message = custom_playbook_dirs_error(rows, tmp_path)
    assert "typo directory not found" in message
    assert "outside the environment directory" in message
    assert "playbook_dirs in %s/.spa.yml" % tmp_path in message


def test_local_apps_need_apps_dir(tmp_path):
    software = seed_software_dir(tmp_path)
    missing_apps = tmp_path / "no-apps"
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, apps_dir=missing_apps)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "org_some_local_app" in state.reason
    assert "spa init --apps-dir" in state.hint


def test_local_app_file_must_exist(tmp_path):
    software = seed_software_dir(tmp_path)
    apps = tmp_path / "apps"
    apps.mkdir()
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, apps_dir=apps)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "Local app source not found" in state.reason
    assert str(apps / "org_some_local_app") in state.reason


def test_local_app_present_ok(tmp_path):
    software = seed_software_dir(tmp_path)
    apps = tmp_path / "apps"
    (apps / "org_some_local_app").mkdir(parents=True)
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, apps_dir=apps)
    assert check_controller_data(paths).ok is True


def test_splunkbase_apps_do_not_require_apps_dir(tmp_path):
    software = seed_software_dir(tmp_path)
    missing_apps = tmp_path / "no-apps"
    config = """
splunk_app_deployment:
  apps:
    - name: splunk_secure_gateway
      source: splunkbase
      app_id: 3205
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, apps_dir=missing_apps)
    assert check_controller_data(paths).ok is True


def test_default_source_is_local(tmp_path):
    software = seed_software_dir(tmp_path)
    apps = tmp_path / "apps"
    apps.mkdir()
    config = """
splunk_app_deployment:
  apps:
    - name: org_implicit
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, apps_dir=apps)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "org_implicit" in state.reason or str(apps / "org_implicit") in state.reason


def test_local_path_override(tmp_path):
    software = seed_software_dir(tmp_path)
    apps = tmp_path / "apps"
    apps.mkdir()
    other = tmp_path / "elsewhere" / "custom_app"
    other.mkdir(parents=True)
    config = """
splunk_app_deployment:
  apps:
    - name: org_custom
      source: local
      local_path: %s
      target_roles: [search_head]
""" % other
    paths = _paths(tmp_path, config, software=software, apps_dir=apps)
    assert check_controller_data(paths).ok is True
    assert local_app_source_path({"local_path": str(other)}, apps) == other


def test_config_software_dir_override(tmp_path, monkeypatch):
    monkeypatch.delenv("SPA_SOFTWARE_DIR", raising=False)
    monkeypatch.delenv("SPA_BASECONFIG_DIR", raising=False)
    real = seed_software_dir(tmp_path / "real")
    empty = tmp_path / "empty-sw"
    empty.mkdir()
    config = """
splunk_dirs:
  splunk_software_dir: %s
  splunk_baseconfig_dir: %s
splunk_hosts:
  - name: idx1
""" % (real, real)
    paths = _paths(tmp_path, config, software=empty)
    assert check_controller_data(paths).ok is True
