"""Controller Software / baseconfig / local-app preflight for validate and deploy."""

from dataclasses import replace

import pytest

from spa.paths import resolve_spa_paths
from spa.preflight import (
    check_controller_data,
    local_app_source_path,
    required_splunk_archives,
    splunk_archive_glob,
)
from spa_testutil import PROJECT_ROOT, seed_baseconfig_dir, seed_software_dir

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _controller_dirs(tmp_path):
    return seed_software_dir(tmp_path), seed_baseconfig_dir(tmp_path)


def _paths(tmp_path, config, software=None, baseconfig=None, apps_dir=None):
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
    if baseconfig is not None:
        kwargs["baseconfig_dir"] = baseconfig
    if apps_dir is not None:
        kwargs["apps_dir"] = apps_dir
    return replace(base, **kwargs)


def test_missing_software_dir_fails(tmp_path):
    missing = tmp_path / "no-software"
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=missing, baseconfig=missing)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "Software directory not found" in state.reason
    assert "spa init --software-dir" in state.hint


def test_software_without_baseconfig_apps_fails(tmp_path):
    software = tmp_path / "Software"
    software.mkdir()
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=software)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "baseconfig apps" in state.reason
    assert "spa init --baseconfig-dir" in state.hint
    assert "spa init --software-dir" not in state.hint


def _baseconfig_software(tmp_path, names):
    software = tmp_path / "Software"
    for name in names:
        (software / "ps" / name).mkdir(parents=True)
    return software


def test_baseconfig_check_accepts_the_s2_indexer_indexes_app(tmp_path):
    software = _baseconfig_software(tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base"))
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=software)
    state = check_controller_data(paths)
    assert state.ok is True


def test_baseconfig_check_no_longer_accepts_only_the_ds_secure_server_app(tmp_path):
    software = _baseconfig_software(tmp_path, ("org_ds_secure_server", "org_cluster_manager_base"))
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=software)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "org_s2_indexer_indexes" in state.reason
    assert "org_ds_secure_server" not in state.reason


def test_seeded_software_without_local_apps_ok(tmp_path):
    software, baseconfig = _controller_dirs(tmp_path)
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=baseconfig)
    state = check_controller_data(paths)
    assert state.ok is True
    # No source: local apps, so apps_dir was never inspected.
    assert state.apps_checked is False


def test_validate_reports_one_ok_line_per_directory(tmp_path):
    from spa.validate import controller_data_message

    software, baseconfig = _controller_dirs(tmp_path)
    apps = tmp_path / "apps"
    (apps / "org_some_local_app").mkdir(parents=True)
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=apps)
    state = check_controller_data(paths)
    assert state.apps_checked is True
    assert controller_data_message(state).splitlines() == [
        "Software OK: %s" % software,
        "Baseconfig OK: %s" % baseconfig,
        "Local apps OK: %s" % apps,
        "Custom playbooks OK: none configured",
    ]

    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=baseconfig)
    without_apps = controller_data_message(check_controller_data(paths)).splitlines()
    assert without_apps[2] == "Local apps OK: none configured"


def test_validate_reports_the_default_custom_playbook_dir(tmp_path):
    from spa.playbooks import DEFAULT_ENV_PLAYBOOK_DIR, custom_playbook_dir_state
    from spa.validate import controller_data_message

    software, baseconfig = _controller_dirs(tmp_path)
    playbooks = tmp_path / DEFAULT_ENV_PLAYBOOK_DIR
    playbooks.mkdir()
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=baseconfig)

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
    software, baseconfig = _controller_dirs(tmp_path)
    missing_apps = tmp_path / "no-apps"
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=missing_apps)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "org_some_local_app" in state.reason
    assert "spa init --apps-dir" in state.hint


def test_local_app_file_must_exist(tmp_path):
    software, baseconfig = _controller_dirs(tmp_path)
    apps = tmp_path / "apps"
    apps.mkdir()
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=apps)
    state = check_controller_data(paths)
    assert state.ok is False
    assert "Local app source not found" in state.reason
    assert str(apps / "org_some_local_app") in state.reason


def test_local_app_present_ok(tmp_path):
    software, baseconfig = _controller_dirs(tmp_path)
    apps = tmp_path / "apps"
    (apps / "org_some_local_app").mkdir(parents=True)
    config = """
splunk_app_deployment:
  apps:
    - name: org_some_local_app
      source: local
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=apps)
    assert check_controller_data(paths).ok is True


def test_splunkbase_apps_do_not_require_apps_dir(tmp_path):
    software, baseconfig = _controller_dirs(tmp_path)
    missing_apps = tmp_path / "no-apps"
    config = """
splunk_app_deployment:
  apps:
    - name: splunk_secure_gateway
      source: splunkbase
      app_id: 3205
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=missing_apps)
    assert check_controller_data(paths).ok is True


def test_default_source_is_splunkbase(tmp_path):
    """CFG-APP-002: omitted source does not require a local app folder."""
    software, baseconfig = _controller_dirs(tmp_path)
    apps = tmp_path / "apps"
    apps.mkdir()
    config = """
splunk_app_deployment:
  apps:
    - name: org_implicit
      target_roles: [search_head]
"""
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=apps)
    state = check_controller_data(paths)
    assert state.ok is True


def test_local_path_override(tmp_path):
    software, baseconfig = _controller_dirs(tmp_path)
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
    paths = _paths(tmp_path, config, software=software, baseconfig=baseconfig, apps_dir=apps)
    assert check_controller_data(paths).ok is True
    assert local_app_source_path({"local_path": str(other)}, apps) == other


def test_config_software_dir_override(tmp_path, monkeypatch):
    monkeypatch.delenv("SPA_SOFTWARE_DIR", raising=False)
    monkeypatch.delenv("SPA_BASECONFIG_DIR", raising=False)
    real_sw, real_bc = _controller_dirs(tmp_path / "real")
    empty = tmp_path / "empty-sw"
    empty.mkdir()
    config = """
splunk_dirs:
  splunk_software_dir: %s
  splunk_baseconfig_dir: %s
splunk_hosts:
  - name: idx1
""" % (real_sw, real_bc)
    paths = _paths(tmp_path, config, software=empty, baseconfig=empty)
    assert check_controller_data(paths).ok is True


def test_splunk_archive_glob_strings():
    assert splunk_archive_glob("splunk", "latest", "amd64") == "splunk-*-*-?inux-amd64.tgz"
    assert splunk_archive_glob("splunk", "10.1.0", "amd64") == "splunk-10.1.0-*-?inux-amd64.tgz"
    assert (
        splunk_archive_glob("splunkforwarder", "latest", "arm64")
        == "splunkforwarder-*-*-?inux-arm64.tgz"
    )
    assert (
        splunk_archive_glob("windowsforwarder", "latest", "amd64")
        == "splunkforwarder-*-*-x64-release.msi"
    )
    assert (
        splunk_archive_glob("windowsforwarder", "9.3.2", "amd64")
        == "splunkforwarder-9.3.2-*-x64-release.msi"
    )


def test_role_host_without_archive_fails_after_baseconfig(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    paths = _paths(
        tmp_path,
        "splunk_hosts:\n  - name: idx1\n    roles: [search_head]\n",
        software=software,
        baseconfig=software,
    )
    state = check_controller_data(paths)
    assert state.ok is False
    assert "baseconfig" not in state.reason.lower()
    assert "splunk-*-*-?inux-amd64.tgz" in state.reason
    assert "latest" in state.reason
    assert "amd64" in state.reason
    assert str(software) in state.reason
    assert "cannot be guessed" in state.reason
    assert "https://www.splunk.com/en_us/download/splunk-enterprise.html" in state.reason


def _touch_archive(software, arch_type="splunk", version="9.3.2", architecture="amd64"):
    if arch_type == "windowsforwarder":
        name = "splunkforwarder-%s-000000000000-x64-release.msi" % version
    else:
        name = "%s-%s-000000000000-linux-%s.tgz" % (arch_type, version, architecture)
    path = software / name
    path.write_bytes(b"dummy")
    return path


def test_splunk_download_true_still_requires_the_archive(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    config = """
splunk_defaults:
  splunk_download:
    splunk: true
splunk_hosts:
  - name: idx1
    roles: [search_head]
"""
    state = check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software))
    assert state.ok is False
    assert "splunk-*-*-?inux-amd64.tgz" in state.reason


def test_host_with_no_roles_does_not_require_an_archive(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    paths = _paths(tmp_path, "splunk_hosts:\n  - name: idx1\n", software=software, baseconfig=software)
    assert check_controller_data(paths).ok is True


def test_required_archives_one_glob_per_distinct_combo():
    config = {
        "splunk_defaults": {"splunk_version": "10.1.0", "splunk_architecture": "amd64"},
        "splunk_hosts": [
            {"name": "sh1", "roles": ["search_head"]},
            {"name": "idx1", "roles": ["indexer"]},
            {
                "name": "uf1",
                "roles": ["universal_forwarder"],
                "splunk_architecture": "arm64",
            },
        ],
    }
    assert required_splunk_archives(config) == (
        ("splunk", "10.1.0", "amd64"),
        ("splunkforwarder", "10.1.0", "arm64"),
    )


def test_uf_only_config_does_not_require_enterprise(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, "splunkforwarder")
    config = """
splunk_hosts:
  - name: uf1
    roles: [universal_forwarder]
"""
    assert check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software)).ok is True


def test_enterprise_only_config_does_not_require_uf(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, "splunk")
    config = """
splunk_hosts:
  - name: idx1
    roles: [indexer]
"""
    assert check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software)).ok is True


def test_dummy_linux_tarball_makes_a_role_host_ok(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software)
    config = """
splunk_hosts:
  - name: idx1
    roles: [search_head]
"""
    assert check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software)).ok is True


@pytest.mark.parametrize(
    "provider_yaml",
    ["virtualbox: {}\n", "terraform:\n  aws:\n    region: eu-central-1\n"],
)
def test_omitted_architecture_globs_amd64(tmp_path, provider_yaml):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    config = provider_yaml + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n"
    state = check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software))
    assert state.ok is False
    assert "splunk-*-*-?inux-amd64.tgz" in state.reason


def test_config_arm64_globs_arm64(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    config = """
splunk_defaults:
  splunk_architecture: arm64
splunk_hosts:
  - name: idx1
    roles: [indexer]
"""
    state = check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software))
    assert state.ok is False
    assert "splunk-*-*-?inux-arm64.tgz" in state.reason
    assert "amd64" not in state.reason


def test_pinned_version_globs_that_version_only(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, version="9.3.2")
    config = """
splunk_defaults:
  splunk_version: 10.1.0
splunk_hosts:
  - name: idx1
    roles: [indexer]
"""
    state = check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software))
    assert state.ok is False
    assert "splunk-10.1.0-*-?inux-amd64.tgz" in state.reason


def test_latest_versions_must_match_across_types(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, "splunk", "9.3.2")
    _touch_archive(software, "splunkforwarder", "9.2.0")
    config = """
splunk_defaults:
  splunk_version: latest
splunk_hosts:
  - name: idx1
    roles: [indexer]
  - name: uf1
    roles: [universal_forwarder]
"""
    state = check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software))
    assert state.ok is False
    assert "9.3.2" in state.reason
    assert "9.2.0" in state.reason


def test_latest_versions_ok_when_types_match(tmp_path):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, "splunk", "9.3.2")
    _touch_archive(software, "splunkforwarder", "9.3.2")
    config = """
splunk_defaults:
  splunk_version: latest
splunk_hosts:
  - name: idx1
    roles: [indexer]
  - name: uf1
    roles: [universal_forwarder]
"""
    assert check_controller_data(_paths(tmp_path, config, software=software, baseconfig=software)).ok is True


def test_inventory_archive_check_uses_shared_missing_reason(tmp_path):
    import importlib.util

    from ansible.errors import AnsibleParserError

    from spa.preflight import missing_archive_reason

    plugin_path = PROJECT_ROOT / "ansible" / "plugins" / "inventory" / "splunk-platform-automator.py"
    spec = importlib.util.spec_from_file_location("spa_inventory_plugin", plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin = module.InventoryModule.__new__(module.InventoryModule)
    software = tmp_path / "Software"
    software.mkdir()
    expected = missing_archive_reason("splunk", "10.1.0", "amd64", str(software))
    with pytest.raises(AnsibleParserError, match="cannot be guessed") as caught:
        plugin._check_splunk_archive("splunk", "amd64", "10.1.0", str(software))
    assert expected in str(caught.value)


def _deploy_session(tmp_path, config, software):
    from spa.api import LocalSpaSession

    config_path = tmp_path / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config)
    inventory = tmp_path / "inventory"
    inventory.mkdir(exist_ok=True)
    (inventory / "hosts").write_text('idx1 ansible_host="10.0.0.8"\n')
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=inventory,
        roots_differ=True,
        software_dir=software,
        baseconfig_dir=software,
    )
    return LocalSpaSession(paths=paths)


def test_deploy_architecture_mismatch_does_not_start_ansible(tmp_path, monkeypatch):
    from spa.hosts import HostsError

    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, architecture="amd64")
    _touch_archive(software, architecture="arm64")
    session = _deploy_session(
        tmp_path,
        "schema_version: 1\n"
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_architecture: amd64\n"
        "splunk_hosts:\n"
        "  - name: idx1\n"
        "    roles: [indexer]\n",
        software,
    )
    called = []
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: (_ for _ in ()).throw(
            HostsError(
                "idx1 architecture mismatch: config amd64, host aarch64",
                rows=[
                    {
                        "name": "idx1",
                        "ok": False,
                        "expected_architecture": "amd64",
                        "architecture": "aarch64",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert "idx1 architecture mismatch: config amd64, host aarch64" in result.error
    assert "No archive found" not in result.error
    assert not called


def test_deploy_mismatch_appends_missing_guest_archive(tmp_path, monkeypatch):
    from spa.hosts import HostsError

    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    _touch_archive(software, architecture="amd64")
    session = _deploy_session(
        tmp_path,
        "schema_version: 1\n"
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_architecture: amd64\n"
        "splunk_hosts:\n"
        "  - name: idx1\n"
        "    roles: [indexer]\n",
        software,
    )
    called = []
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: (_ for _ in ()).throw(
            HostsError(
                "idx1 architecture mismatch: config amd64, host aarch64",
                rows=[
                    {
                        "name": "idx1",
                        "ok": False,
                        "expected_architecture": "amd64",
                        "architecture": "aarch64",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert "idx1 architecture mismatch: config amd64, host aarch64" in result.error
    assert "splunk-*-*-?inux-arm64.tgz" in result.error
    assert "https://www.splunk.com/en_us/download/splunk-enterprise.html" in result.error
    assert not called


def test_deploy_match_missing_tarball_does_not_start_ansible(tmp_path, monkeypatch):
    software = _baseconfig_software(
        tmp_path, ("org_s2_indexer_indexes", "org_cluster_manager_base")
    )
    session = _deploy_session(
        tmp_path,
        "schema_version: 1\n"
        "external: {}\n"
        "splunk_hosts:\n"
        "  - name: idx1\n"
        "    roles: [indexer]\n",
        software,
    )
    called = []
    pinged = []
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: pinged.append(True)
        or {
            "hosts": [
                {
                    "name": "idx1",
                    "ok": True,
                    "expected_architecture": "amd64",
                    "architecture": "x86_64",
                }
            ]
        },
    )
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    result = session.deploy(confirm=True)
    assert result.ok is False
    assert "splunk-*-*-?inux-amd64.tgz" in result.error
    assert not called
