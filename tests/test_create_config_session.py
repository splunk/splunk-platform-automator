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


def _hosts_config():
    return (
        "plugin: splunk-platform-automator\n"
        "splunk_defaults:\n"
        "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
        "  splunk_license_file: Splunk_Enterprise.lic\n"
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
    )


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
    assert packs["command"] == "spa --agent apps content-packs list 5391"
    assert "license" in licenses["ask"].lower()
    assert "content pack" in packs["ask"].lower()


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


def test_default_validate_fails_itsi_without_itsi_capability():
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
    assert premium_entitlement_error(scan)


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


def test_provision_success_envelope_includes_hosts_check_then_deploy(
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
    rc = _run(["--agent", "--start-dir", str(env), "provision", "--yes"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert _next_ids(payload["data"]) == ["hosts.check", "deploy"]
    check, deploy = payload["data"]["next"]
    assert check["required"] is True
    assert check["command"] == "spa --agent hosts check"
    assert deploy["required"] is False
    assert deploy["command"] == "spa --agent deploy --yes"
    assert "Deploy" in deploy["ask"]
