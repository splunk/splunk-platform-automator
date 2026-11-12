"""Follow-ups, license env binding, validate gate, and nested omit-defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from spa_testutil import PROJECT_ROOT, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _next_ids(payload):
    return [item["id"] for item in (payload.get("next") or payload.get("data", {}).get("next") or [])]


def _hosts_config(*, license_file: bool = True):
    license_line = (
        "  splunk_license_file: Splunk_Enterprise.lic\n" if license_file else ""
    )
    return (
        "plugin: splunk-platform-automator\n"
        "splunk_defaults:\n"
        "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
        "%s"
        "splunk_hosts:\n"
        "  - name: sh\n"
        "    roles: [search_head]\n"
        "    os:\n"
        "      packages: [openjdk-21-jdk]\n"
        "  - name: idx\n"
        "    roles: [indexer]\n"
        "  - name: uf\n"
        "    roles: [universal_forwarder]\n"
        "  - name: hf\n"
        "    roles: [heavy_forwarder]\n"
        "  - name: lm\n"
        "    roles: [license_manager]\n"
    ) % license_line


def test_apps_add_itsi_includes_license_and_content_pack_next(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "test")
    from spa.apps import classify_kind
    from spa.cli import _run

    monkeypatch.setattr(
        "spa.apps.get_app",
        lambda app_id, client=None: {
            "uid": 1841,
            "appid": "itsi",
            "title": "Splunk IT Service Intelligence",
            "type": "app",
        },
    )
    assert classify_kind(1841) == "premium_itsi"
    rc = _run(["--agent", "--start-dir", str(env), "apps", "add", "1841"])
    payload = json.loads(capsys.readouterr().out)
    assert rc in {0, 1}, payload
    assert "data" in payload
    assert _next_ids(payload["data"])[:2] == ["licenses.list", "apps.content-packs.list"]
    licenses = payload["data"]["next"][0]
    packs = payload["data"]["next"][1]
    assert licenses["command"] == "spa --agent licenses list"
    assert licenses["required"] is False
    assert "essentials work" in licenses["ask"].lower() or "ite work" in licenses["ask"].lower()
    assert packs["command"] == "spa --agent apps content-packs list 5391"
    assert packs["argv"] == ["spa", "--agent", "apps", "content-packs", "list", "5391"]
    assert packs["choice"]["allowed"] == ["none", "list", "name"]
    assert "none" in packs["ask"].lower()
    assert "list" in packs["ask"].lower()
    assert "name" in packs["ask"].lower()
    assert "license" in licenses["ask"].lower()
    assert "content pack" in packs["ask"].lower()


def _library_app(app_id, client=None):
    if app_id == 5391:
        return {
            "uid": 5391,
            "appid": "DA-ITSI-ContentLibrary",
            "title": "Splunk IT Service Intelligence Content Library",
            "type": "app",
            "release": {
                "title": "2.0.0",
                "path": "https://splunkbase.splunk.com/app/5391/release/2.0.0/download",
            },
        }
    return {
        "uid": 1841,
        "appid": "itsi",
        "title": "Splunk IT Service Intelligence",
        "type": "app",
    }


def test_apps_add_content_pack_offers_customize_next(tmp_path, monkeypatch, capsys):
    """CFG-APP-011."""
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "test")
    monkeypatch.setattr("spa.apps.get_app", _library_app)
    from spa.cli import _run

    rc = _run(
        [
            "--agent",
            "--start-dir",
            str(env),
            "apps",
            "add",
            "5391",
            "--content-pack",
            "DA-ITSI-CP-nix",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    assert payload["ok"] is True
    assert _next_ids(payload["data"])[0] == "apps.customize"
    customize = payload["data"]["next"][0]
    assert customize["required"] is False
    assert customize["command"] == (
        "spa --agent apps add 5391 --content-pack DA-ITSI-CP-nix --customize --yes"
    )
    assert customize["argv"] == [
        "spa",
        "--agent",
        "apps",
        "add",
        "5391",
        "--content-pack",
        "DA-ITSI-CP-nix",
        "--customize",
        "--yes",
    ]
    authored = YAML(typ="safe").load(config.read_text(encoding="utf-8"))
    library = next(
        app
        for app in authored["splunk_app_deployment"]["apps"]
        if app.get("app_id") == 5391
    )
    assert library["content_pack_apps"] == [{"name": "DA-ITSI-CP-nix"}]


def test_apps_add_content_pack_customize_attaches_pack_playbook(
    tmp_path, monkeypatch, capsys
):
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "test")
    monkeypatch.setattr("spa.apps.get_app", _library_app)
    from spa.cli import _run

    rc = _run(
        [
            "--agent",
            "--start-dir",
            str(env),
            "apps",
            "add",
            "5391",
            "--content-pack",
            "DA-ITSI-CP-nix",
            "--customize",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    assert payload["ok"] is True
    assert "apps.customize" not in _next_ids(payload["data"])
    authored = YAML(typ="safe").load(config.read_text(encoding="utf-8"))
    library = next(
        app
        for app in authored["splunk_app_deployment"]["apps"]
        if app.get("app_id") == 5391
    )
    assert library["content_pack_apps"] == [
        {
            "name": "DA-ITSI-CP-nix",
            "customizations": {
                "run_playbook_after_restart": (
                    "ansible/apps_playbooks/DA-ITSI-CP-nix_configure.yml"
                ),
            },
        }
    ]


def test_apps_add_content_pack_customize_retry_updates_existing_pack(
    tmp_path, monkeypatch, capsys
):
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "test")
    monkeypatch.setattr("spa.apps.get_app", _library_app)
    from spa.cli import _run

    assert (
        _run(
            [
                "--agent",
                "--start-dir",
                str(env),
                "apps",
                "add",
                "5391",
                "--content-pack",
                "DA-ITSI-CP-nix",
            ]
        )
        == 0
    )
    capsys.readouterr()
    rc = _run(
        [
            "--agent",
            "--start-dir",
            str(env),
            "apps",
            "add",
            "5391",
            "--content-pack",
            "DA-ITSI-CP-nix",
            "--customize",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    authored = YAML(typ="safe").load(config.read_text(encoding="utf-8"))
    library = next(
        app
        for app in authored["splunk_app_deployment"]["apps"]
        if app.get("app_id") == 5391
    )
    assert library["content_pack_apps"][0]["customizations"][
        "run_playbook_after_restart"
    ].endswith("DA-ITSI-CP-nix_configure.yml")


def test_apps_add_content_pack_without_playbook_skips_customize_next(
    tmp_path, monkeypatch, capsys
):
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "test")
    monkeypatch.setattr("spa.apps.get_app", _library_app)
    from spa.cli import _run

    rc = _run(
        [
            "--agent",
            "--start-dir",
            str(env),
            "apps",
            "add",
            "5391",
            "--content-pack",
            "DA-ITSI-CP-unknown",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    assert payload["ok"] is True
    assert "apps.customize" not in _next_ids(payload["data"])
    assert _next_ids(payload["data"]) == ["apps.add.another"]


def test_apps_add_nix_without_roles_is_a_choice(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setattr(
        "spa.apps.get_app",
        lambda app_id, client=None: {
            "uid": 833,
            "appid": "Splunk_TA_nix",
            "title": "Splunk Add-on for Unix and Linux",
            "type": "addon",
        },
    )
    from spa.cli import _run

    before = config.read_bytes()
    rc = _run(["--agent", "--start-dir", str(env), "apps", "add", "833"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["ok"] is False
    assert payload["data"]["ready"] is False
    assert config.read_bytes() == before
    choice = next(item for item in payload["data"]["requirements"] if item["kind"] == "choice")
    assert set(choice["suggested"]) == {"universal_forwarder", "heavy_forwarder"}
    assert set(choice["suggested"]) <= set(choice["allowed"])
    assert "universal_forwarder" in choice["allowed"]
    assert "indexer" in choice["allowed"]
    assert "--roles" in choice["retry"]


def test_apps_search_labels_suggested_roles(monkeypatch):
    from spa.apps import search

    monkeypatch.setattr(
        "spa.apps.search_apps",
        lambda query, limit=10, client=None: [
            {
                "uid": 833,
                "appid": "Splunk_TA_nix",
                "title": "Splunk Add-on for Unix and Linux",
                "type": "addon",
                "description": "Unix TA",
            }
        ],
    )
    payload = search("unix", limit=5)
    row = payload["apps"][0]
    assert row["suggested_roles"] == ["universal_forwarder", "heavy_forwarder"]


def _write_license(path, *, license_type="enterprise", group_id="Enterprise", addons=()):
    addon_xml = "".join("<add_on>%s</add_on>" % addon for addon in addons)
    path.write_text(
        """<license>
  <payload>
    <type>%s</type>
    <group_id>%s</group_id>
    <creation_time>1700000000</creation_time>
    <expiration_time>4102444800</expiration_time>
    <add_ons>%s</add_ons>
  </payload>
</license>
"""
        % (license_type, group_id, addon_xml)
    )
    return path


def test_licenses_list_reads_env_config_and_proposes_itsi(tmp_path, monkeypatch):
    from spa.api import open_session
    from spa.paths import resolve_spa_paths

    env = write_min_env(tmp_path / "env")
    software = tmp_path / "Software"
    software.mkdir()
    _write_license(software / "Splunk_Enterprise.lic")
    _write_license(
        software / "Splunk_ITSI.lic",
        license_type="addon",
        group_id="ITSI",
        addons=("itsi",),
    )
    config = env / "config" / "splunk_config.yml"
    config.write_text(
        _hosts_config()
        + "splunk_app_deployment:\n"
        "  apps:\n"
        "    - name: Splunk IT Service Intelligence\n"
        "      app_id: 1841\n"
        "      premium_app: itsi\n",
        encoding="utf-8",
    )
    (env / ".spa.yml").write_text(
        "spa_home: %s\nsplunk_software_dir: %s\n" % (PROJECT_ROOT, software),
        encoding="utf-8",
    )
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.delenv("SPA_SOFTWARE_DIR", raising=False)
    session = open_session(paths=resolve_spa_paths(start_dir=env))
    result = session.licenses(software_dir=str(software))
    assert result.ok is True
    proposed = result.data["proposed_splunk_license_file"]
    assert "Splunk_Enterprise.lic" in proposed
    assert "Splunk_ITSI.lic" in proposed
    ids = _next_ids(result.data)
    assert "config.set.license_file" in ids
    write = next(item for item in result.data["next"] if item["id"] == "config.set.license_file")
    assert "Splunk_ITSI.lic" in write["command"]
    assert "Splunk_Enterprise.lic" in write["command"]
    listed = json.dumps(proposed, separators=(",", ":"))
    assert write["argv"] == [
        "spa",
        "--agent",
        "config",
        "set",
        "splunk_defaults.splunk_license_file",
        listed,
        "--yes",
    ]
    placement = next(
        item for item in result.data["next"] if item["id"] == "license_manager.placement"
    )
    assert placement["argv"] == [
        "spa",
        "--agent",
        "config",
        "add",
        "splunk_hosts[name=mc]",
        '{"roles":["monitoring_console","license_manager"]}',
        "--yes",
    ]


def test_compact_license_rows_include_capabilities():
    from spa.licenses import _compact_license_row

    row = _compact_license_row(
        {
            "basename": "Splunk_ITSI.lic",
            "status": "valid",
            "expires_at": "2099-01-01",
            "capabilities": ["enterprise", "itsi"],
            "path": "/tmp/Software/Splunk_ITSI.lic",
        }
    )
    assert row == {
        "basename": "Splunk_ITSI.lic",
        "status": "valid",
        "expiration": "2099-01-01",
        "capabilities": ["enterprise", "itsi"],
    }


def test_default_validate_warns_itsi_without_itsi_capability():
    from spa.validate import license_summary, premium_entitlement_error

    scan = {
        "itsi_in_config": True,
        "es_in_config": False,
        "configured_splunk_license_file": ["Splunk_Enterprise.lic"],
        "license_manager_in_config": True,
        "discovered_files": [{"basename": "Splunk_Enterprise.lic"}],
        "proposed_splunk_license_file": ["Splunk_Enterprise.lic", "Splunk_ITSI.lic"],
        "unsatisfied_requirements": ["itsi"],
        "license_validation": {
            "errors": ["ITSI is in config but no ITSI-capable license is set"],
            "warnings": [],
        },
    }
    summary = license_summary(scan)
    assert summary["proposed_splunk_license_file"] == [
        "Splunk_Enterprise.lic",
        "Splunk_ITSI.lic",
    ]
    assert summary["unsatisfied_requirements"] == ["itsi"]
    assert premium_entitlement_error(scan) is None


def test_default_validate_fails_es_without_es_capability():
    from spa.validate import premium_entitlement_error

    scan = {
        "itsi_in_config": False,
        "es_in_config": True,
        "configured_splunk_license_file": ["Splunk_Enterprise.lic"],
        "license_manager_in_config": True,
        "unsatisfied_requirements": ["es"],
        "license_validation": {
            "errors": ["ES is in config but no ES-capable license is set"],
            "warnings": [],
        },
    }
    assert premium_entitlement_error(scan)


def test_evaluate_license_role_allows_lm_and_unlicensed_itsi():
    from spa.validate import evaluate_license_role

    lm_only = evaluate_license_role(
        {
            "license_manager_in_config": True,
            "configured_splunk_license_file": None,
            "itsi_in_config": False,
            "es_in_config": False,
            "unsatisfied_requirements": [],
        }
    )
    assert lm_only["ok"] is True
    assert {item["id"] for item in lm_only["warnings"]} == {"license_manager.license_file"}

    unlicensed_itsi = evaluate_license_role(
        {
            "license_manager_in_config": True,
            "configured_splunk_license_file": ["Splunk_Enterprise.lic"],
            "itsi_in_config": True,
            "es_in_config": False,
            "unsatisfied_requirements": ["itsi"],
            "license_validation": {"errors": [], "warnings": []},
        }
    )
    assert unlicensed_itsi["ok"] is True
    assert {item["id"] for item in unlicensed_itsi["warnings"]} == {"itsi.license_file"}

    files_without_lm = evaluate_license_role(
        {
            "license_manager_in_config": False,
            "configured_splunk_license_file": ["Splunk_Enterprise.lic"],
            "itsi_in_config": False,
            "es_in_config": False,
        }
    )
    assert files_without_lm["ok"] is False


def test_apps_add_1841_writes_without_license_files(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(_hosts_config(license_file=False), encoding="utf-8")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPLUNK_ADMIN_PASSWORD", "test")
    from spa.cli import _run

    monkeypatch.setattr(
        "spa.apps.get_app",
        lambda app_id, client=None: {
            "uid": 1841,
            "appid": "itsi",
            "title": "Splunk IT Service Intelligence",
            "type": "app",
        },
    )
    rc = _run(["--agent", "--start-dir", str(env), "apps", "add", "1841"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    assert payload["ok"] is True
    assert payload["data"]["ready"] is True
    authored = YAML(typ="safe").load(config.read_text(encoding="utf-8"))
    assert any(app.get("app_id") == 1841 for app in authored["splunk_app_deployment"]["apps"])
    warning_ids = {
        item["id"]
        for item in payload["data"].get("warnings") or []
        if isinstance(item, dict)
    }
    assert "itsi.license_file" in warning_ids or "license_manager.license_file" in warning_ids
    licenses = next(item for item in payload["data"]["next"] if item["id"] == "licenses.list")
    assert licenses["required"] is False
    assert "essentials work" in licenses["ask"].lower() or "ite work" in licenses["ask"].lower()


def test_config_add_license_manager_without_files_writes_and_returns_next(tmp_path):
    from spa.config_edit import config_add

    env = write_min_env(tmp_path / "env")
    path = env / "config" / "splunk_config.yml"
    path.write_text(
        "plugin: splunk-platform-automator\n"
        "splunk_defaults:\n"
        "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
        "splunk_hosts:\n"
        "  - name: sh\n"
        "    roles: [search_head]\n",
        encoding="utf-8",
    )
    result = config_add(
        path,
        PROJECT_ROOT,
        "splunk_hosts[name=lm]",
        '{"roles":["license_manager"]}',
    )
    assert result["ready"] is True
    assert result["changed"] is True
    authored = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    assert any(
        host.get("name") == "lm" and "license_manager" in (host.get("roles") or [])
        for host in authored["splunk_hosts"]
    )
    warning_ids = {
        item["id"]
        for item in result.get("warnings") or []
        if isinstance(item, dict)
    }
    assert "license_manager.license_file" in warning_ids
    assert result["next"][0]["id"] == "config.set.license_file"
    assert result["next"][0]["required"] is False
    assert result["next"][0]["command"] == "spa --agent licenses list"


def test_config_set_os_map_omits_schema_default_booleans(tmp_path):
    from spa.config_edit import config_set

    env = write_min_env(tmp_path / "env")
    path = env / "config" / "splunk_config.yml"
    path.write_text(
        "plugin: splunk-platform-automator\n"
        "splunk_defaults:\n"
        "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
        "splunk_hosts:\n"
        "  - name: sh\n"
        "    roles: [search_head]\n",
        encoding="utf-8",
    )
    result = config_set(
        path,
        PROJECT_ROOT,
        "os",
        '{"disable_selinux": true, "update_hosts_file": true, "packages": ["acl"]}',
    )
    authored = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    assert authored["os"] == {"packages": ["acl"]}
    omitted = {item["path"] for item in result["omitted_defaults"]}
    assert "os.disable_selinux" in omitted
    assert "os.update_hosts_file" in omitted


def test_explain_os_children_show_schema_defaults():
    from spa.config_tree import explain_config

    data = explain_config("os")
    selinux = next(item for item in data["fields"] if item["name"] == "disable_selinux")
    assert selinux["default"] is True
    cron = next(item for item in data["fields"] if item["name"] == "enable_time_sync_cron")
    assert cron["default"] is False


def test_hosts_provision_envelope_next_is_deploy_not_hosts_check(
    tmp_path, monkeypatch, capsys
):
    from spa_testutil import satisfy_env_lookups, write_min_env
    from spa.cli import _run

    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    satisfy_env_lookups(monkeypatch, start_dir=env)

    class FakeProvider:
        name = "test"

        def provision(self, extra, **_kwargs):
            return 0

    monkeypatch.setattr("spa.providers.get_provider", lambda paths: FakeProvider())
    rc = _run(["--agent", "--start-dir", str(env), "hosts", "provision", "--yes"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert _next_ids(payload["data"]) == ["logs.follow", "deploy"]
    follow, deploy = payload["data"]["next"]
    assert follow["required"] is False
    assert follow["command"] == (
        "spa --env %s logs --follow --wait --ansible-output --color" % env.name
    )
    assert follow["argv"][1] == "--env"
    assert follow["argv"][2] == env.name
    assert deploy["required"] is False
    assert deploy["command"] == "spa --agent deploy --yes"
    assert "Deploy" in deploy["ask"]
    encoded = json.dumps(payload["data"]["next"])
    assert "hosts check" not in encoded
    assert "hosts.check" not in encoded
