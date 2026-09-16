"""spa apps search / snippet / download (mocked Splunkbase HTTP)."""

from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from spa_testutil import LIB, PROJECT_ROOT, run_spa, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.api import open_session  # noqa: E402
from spa.apps import (  # noqa: E402
    AppsError,
    ITE_WORK_ERROR,
    download,
    format_search_text,
    search,
    snippet,
    summarize,
)
from spa.splunkbase import SplunkbaseError  # noqa: E402


def _ta(uid=833, **extra):
    row = {
        "uid": uid,
        "appid": "Splunk_TA_nix",
        "title": "Splunk Add-on for Unix and Linux",
        "type": "addon",
        "description": (
            "The Splunk Add-on for Unix and Linux works with the Splunk App "
            "for Unix and Linux to provide rapid insights."
        ),
        "release": {
            "title": "10.3.4",
            "path": "https://splunkbase.splunk.com/app/833/release/10.3.4/download/",
        },
        "releases": [
            {
                "title": "10.3.4",
                "path": "https://splunkbase.splunk.com/app/833/release/10.3.4/download/",
            }
        ],
    }
    row.update(extra)
    return row


def _itsi():
    return {
        "uid": 1841,
        "appid": "itsi",
        "title": "Splunk IT Service Intelligence",
        "type": "app",
        "description": "ITSI is a premium monitoring product.",
        "release": {
            "title": "4.21.0",
            "path": "https://splunkbase.splunk.com/app/1841/release/4.21.0/download/",
        },
    }


def _library():
    return {
        "uid": 5391,
        "appid": "DA-ITSI-ContentLibrary",
        "title": "Splunk Content Pack for ITSI Content Library",
        "type": "app",
        "description": "ITSI content library archive.",
        "release": {
            "title": "2.0.0",
            "path": "https://splunkbase.splunk.com/app/5391/release/2.0.0/download/",
        },
    }


def _pack():
    return {
        "uid": 7294,
        "appid": "DA-ITSI-CP-CUST-ATLAS-AWS-EBS",
        "title": "Content Pack for AWS EBS",
        "type": "app",
        "description": "Single ITSI content pack.",
        "release": {
            "title": "1.0.0",
            "path": "https://splunkbase.splunk.com/app/7294/release/1.0.0/download/",
        },
    }


def _es():
    return {
        "uid": 263,
        "appid": "SplunkEnterpriseSecuritySuite",
        "title": "Splunk Enterprise Security",
        "type": "app",
        "description": "ES premium app.",
        "release": {
            "title": "8.0.0",
            "path": "https://splunkbase.splunk.com/app/263/release/8.0.0/download/",
        },
    }


def _ite():
    return {
        "uid": 5403,
        "appid": "ae3c7fd6-577a-11eb-b94e-06add55d78f8",
        "title": "IT Essentials Work",
        "type": "app",
        "description": "ITE Work.",
        "release": {
            "title": "5.0.1",
            "path": "https://splunkbase.splunk.com/app/5403/release/5.0.1/download/",
        },
    }


def _uuid_app():
    return {
        "uid": 999001,
        "appid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "title": "Mystery UUID app",
        "type": "app",
        "description": "No folder name.",
        "release": {
            "title": "1.0",
            "path": "https://splunkbase.splunk.com/app/999001/release/1.0/download/",
        },
    }


class FakeClient:
    def __init__(
        self,
        apps: Optional[List[dict]] = None,
        by_id: Optional[Dict[int, dict]] = None,
        archive: bytes = b"tgz-bytes",
    ) -> None:
        self.apps = list(apps or [])
        self.by_id = dict(by_id or {})
        self.archive = archive
        self.search_urls: List[str] = []
        self.login_fields: List[Dict[str, str]] = []

    def get(self, url: str, headers=None) -> Tuple[int, str]:
        if "/app/?" in url:
            self.search_urls.append(url)
            return 200, json.dumps({"results": self.apps})
        for app_id, payload in self.by_id.items():
            if "/app/%s/" % app_id in url:
                return 200, json.dumps(payload)
        return 404, "{}"

    def post_form(self, url: str, fields, headers=None) -> Tuple[int, str]:
        assert "password" not in url
        self.login_fields.append(dict(fields))
        return 200, "<response><id>test-token</id></response>"

    def get_bytes(self, url: str, headers=None) -> Tuple[int, bytes]:
        assert headers and headers.get("X-Auth-Token") == "test-token"
        return 200, self.archive


def _tgz(name: str, *, unsafe_name: Optional[str] = None) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        path = unsafe_name or "%s/default/app.conf" % name
        payload = b"[launcher]\nversion = 1.0\n"
        member = tarfile.TarInfo(path)
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    return output.getvalue()


def test_summarize_truncates_without_html():
    text = "<p>" + ("word " * 80) + "</p>"
    out = summarize(text, limit=40)
    assert "<" not in out
    assert len(out) <= 40


def test_search_compact_fields_no_description():
    client = FakeClient(apps=[_ta(), _ite(), _itsi()])
    data = search("unix", limit=10, client=client)
    ids = [row["app_id"] for row in data["apps"]]
    assert 833 in ids
    assert 1841 in ids
    assert 5403 not in ids
    for row in data["apps"]:
        assert "description" not in row
        assert set(row) <= {"app_id", "name", "title", "type", "kind", "version", "summary"}
        assert len(row["summary"]) <= 100
    nix = next(row for row in data["apps"] if row["app_id"] == 833)
    assert nix["name"] == "Splunk_TA_nix"
    assert nix["type"] == "addon"
    assert nix["kind"] == "ta"
    assert nix["version"] == "10.3.4"


def test_search_requests_release_so_version_is_populated():
    """The list endpoint omits release unless include=release is requested."""
    client = FakeClient(apps=[_ta()])
    data = search("unix", limit=5, client=client)
    assert client.search_urls
    assert "include=release" in client.search_urls[0]
    assert data["apps"][0]["version"] == "10.3.4"


def test_search_omits_version_when_app_has_no_release():
    bare = _ta(uid=9100, appid="App_no_release")
    bare.pop("release")
    bare.pop("releases")
    data = search("unix", limit=5, client=FakeClient(apps=[bare]))
    row = data["apps"][0]
    assert "version" not in row
    assert row["app_id"] == 9100


def test_search_respects_limit():
    apps = [_ta(uid=8000 + i, appid="App_%s" % i, title="App %s" % i) for i in range(15)]
    data = search("app", limit=10, client=FakeClient(apps=apps))
    assert len(data["apps"]) == 10


def test_search_itsi_query_pins_1841_first():
    data = search(
        "itsi",
        limit=10,
        client=FakeClient(apps=[_library(), _pack(), _itsi()]),
    )
    assert [row["app_id"] for row in data["apps"]][0] == 1841
    assert data["apps"][0]["kind"] == "premium_itsi"


def test_search_itsi_fetches_1841_when_missing_from_page():
    client = FakeClient(apps=[_library(), _pack()], by_id={1841: _itsi()})
    data = search("itsi content", limit=5, client=client)
    assert data["apps"][0]["app_id"] == 1841
    assert [row["app_id"] for row in data["apps"]].count(1841) == 1


def test_search_unix_does_not_pin_itsi():
    data = search("unix", limit=10, client=FakeClient(apps=[_ta(), _itsi()]))
    assert [row["app_id"] for row in data["apps"]] == [833, 1841]


def test_search_es_query_pins_263_first():
    data = search("es", limit=10, client=FakeClient(apps=[_ta(), _es()]))
    assert [row["app_id"] for row in data["apps"]][0] == 263
    assert data["apps"][0]["kind"] == "es_not_premium"


def test_search_es_fetches_263_when_missing_from_page():
    client = FakeClient(apps=[_ta()], by_id={263: _es()})
    data = search("es notable", limit=5, client=client)
    assert data["apps"][0]["app_id"] == 263
    assert [row["app_id"] for row in data["apps"]].count(263) == 1


def test_search_elasticsearch_does_not_pin_es():
    data = search("elasticsearch", limit=10, client=FakeClient(apps=[_ta(), _es()]))
    assert [row["app_id"] for row in data["apps"]] == [833, 263]


def test_search_filters_type_and_kind():
    client = FakeClient(apps=[_ta(), _itsi(), _library(), _pack()])
    addons = search("itsi", limit=10, app_type="addon", client=client)
    assert all(row["type"] == "addon" for row in addons["apps"])
    assert 1841 not in [row["app_id"] for row in addons["apps"]]
    packs = search("itsi", limit=10, kind="itsi_content_library", client=client)
    assert [row["app_id"] for row in packs["apps"]] == [5391]


def test_search_rejects_unknown_filter():
    with pytest.raises(AppsError, match="--kind must be one of"):
        search("unix", kind="premium_es", client=FakeClient(apps=[_ta()]))


def test_search_human_text_pipes_meta_then_names_the_summary():
    text = format_search_text(
        "unix",
        [
            {
                "app_id": 833,
                "name": "Splunk_TA_nix",
                "title": "Splunk Add-on for Unix and Linux",
                "type": "addon",
                "kind": "ta",
                "version": "10.3.4",
                "summary": "The Splunk Add-on for Unix and Linux works with the Splunk App…",
            }
        ],
    )
    assert text.splitlines() == [
        "833 | Splunk_TA_nix | addon | ta | 10.3.4 | Splunk Add-on for Unix and Linux",
        "      The Splunk Add-on for Unix and Linux works with the Splunk App…",
    ]


def test_snippet_ta_comments_and_folder_name():
    data = snippet(833, roles=["search_head", "indexer"], client=FakeClient(by_id={833: _ta()}))
    text = data["snippet"]
    assert text.startswith("# Splunk Add-on for Unix and Linux")
    assert "works with the Splunk App" not in text
    assert "name: Splunk_TA_nix" in text
    assert "app_id: 833" in text
    assert "target_roles: [search_head, indexer]" in text
    assert data["kind"] == "ta"
    assert "password" not in text.lower()


def test_snippet_comment_is_title_only():
    data = snippet(833, client=FakeClient(by_id={833: _ta()}))
    comments = [line for line in data["snippet"].splitlines() if line.startswith("#")]
    assert comments == ["# Splunk Add-on for Unix and Linux"]
    assert "splunkbase.splunk.com" not in data["snippet"]
    assert "rapid insights" not in data["snippet"]


def test_snippet_itsi_premium_no_target_roles():
    data = snippet(1841, roles=["search_head"], client=FakeClient(by_id={1841: _itsi()}))
    text = data["snippet"]
    assert "premium_app: itsi" in text
    assert "  target_roles:" not in text
    assert "--roles is ignored" in text
    assert data["kind"] == "premium_itsi"
    assert data["name"] == "Splunk IT Service Intelligence"


def test_snippet_content_library():
    data = snippet(5391, client=FakeClient(by_id={5391: _library()}))
    assert "itsi_content_pack: true" in data["snippet"]
    assert "content_pack_apps: []" in data["snippet"]
    assert data["kind"] == "itsi_content_library"


def test_snippet_single_pack():
    data = snippet(7294, client=FakeClient(by_id={7294: _pack()}))
    assert data["kind"] == "itsi_content_pack_single"
    assert "content_pack_api:" in data["snippet"]
    assert "  target_roles:" not in data["snippet"]


def test_snippet_es_not_premium():
    data = snippet(263, client=FakeClient(by_id={263: _es()}))
    assert data["kind"] == "es_not_premium"
    assert "\n  premium_app: es" not in data["snippet"]
    assert "60" in data["snippet"]


def test_snippet_ite_work_errors():
    with pytest.raises(AppsError, match="1841"):
        snippet(5403, client=FakeClient(by_id={5403: _ite()}))
    assert "unlicensed" in ITE_WORK_ERROR


def test_snippet_uuid_without_override_fails():
    with pytest.raises(AppsError, match="folder-like"):
        snippet(999001, client=FakeClient(by_id={999001: _uuid_app()}))


def test_snippet_local_uses_extracted_folder(tmp_path):
    folder = tmp_path / "Splunk_TA_nix"
    folder.mkdir()
    data = snippet(
        833,
        source="local",
        apps_dir=tmp_path,
        roles=["indexer"],
        client=FakeClient(by_id={833: _ta()}),
    )
    assert data["source"] == "local"
    assert data["path"] == "Splunk_TA_nix"
    assert "  source: local" in data["snippet"]
    assert "  path: Splunk_TA_nix" in data["snippet"]
    assert "  app_id:" not in data["snippet"]


def test_snippet_local_custom_app_uses_folder_without_splunkbase(tmp_path):
    folder = tmp_path / "Acme_Custom_App"
    folder.mkdir()
    data = snippet(
        "Acme_Custom_App",
        source="local",
        apps_dir=tmp_path,
        roles=["search_head"],
        client=FakeClient(),
    )
    assert data["name"] == "Acme_Custom_App"
    assert "app_id" not in data
    assert data["path"] == "Acme_Custom_App"
    assert data["snippet"] == (
        "# Acme_Custom_App\n"
        "- name: Acme_Custom_App\n"
        "  source: local\n"
        "  path: Acme_Custom_App\n"
        "  target_roles: [search_head]\n"
    )


def test_snippet_local_custom_app_uses_bare_archive(tmp_path):
    (tmp_path / "Acme_Custom_App.tgz").write_bytes(b"archive")
    data = snippet(
        "Acme_Custom_App",
        source="local",
        apps_dir=tmp_path,
        roles=["search_head"],
        client=FakeClient(),
    )
    assert data["path"] == "Acme_Custom_App.tgz"
    assert "  path: Acme_Custom_App.tgz" in data["snippet"]
    assert "unpack it in apps_dir" in data["snippet"]


def test_snippet_local_custom_missing_explains_folder_requirement(tmp_path):
    with pytest.raises(AppsError, match=r"custom app.*place its folder or archive"):
        snippet(
            "Acme_Custom_App",
            source="local",
            apps_dir=tmp_path,
            client=FakeClient(),
        )


def test_snippet_local_premium_uses_archive(tmp_path):
    archive = tmp_path / "Splunk_IT_Service_Intelligence_4.21.0.tgz"
    archive.write_bytes(b"archive")
    data = snippet(
        1841,
        source="local",
        apps_dir=tmp_path,
        client=FakeClient(by_id={1841: _itsi()}),
    )
    assert data["path"] == archive.name
    assert "  path: %s" % archive.name in data["snippet"]
    assert "  premium_app: itsi" in data["snippet"]


def test_snippet_local_ta_archive_makes_snippet_with_extract_note(tmp_path):
    (tmp_path / "Splunk_TA_nix_10.3.4.tgz").write_bytes(b"archive")
    data = snippet(
        833,
        source="local",
        apps_dir=tmp_path,
        roles=["indexer"],
        client=FakeClient(by_id={833: _ta()}),
    )
    assert data["path"] == "Splunk_TA_nix_10.3.4.tgz"
    assert "  source: local" in data["snippet"]
    assert "  path: Splunk_TA_nix_10.3.4.tgz" in data["snippet"]
    assert "spa apps download 833 --extract --yes" in data["snippet"]
    assert "  target_roles: [indexer]" in data["snippet"]


def test_snippet_local_folder_wins_over_archive(tmp_path):
    (tmp_path / "Splunk_TA_nix_10.3.4.tgz").write_bytes(b"archive")
    (tmp_path / "Splunk_TA_nix").mkdir()
    data = snippet(
        833,
        source="local",
        apps_dir=tmp_path,
        client=FakeClient(by_id={833: _ta()}),
    )
    assert data["path"] == "Splunk_TA_nix"
    assert "--extract" not in data["snippet"]


def test_snippet_local_missing_says_download_first(tmp_path):
    with pytest.raises(AppsError, match=r"not found.*download 833 --extract --yes first"):
        snippet(
            833,
            source="local",
            apps_dir=tmp_path,
            client=FakeClient(by_id={833: _ta()}),
        )


def test_download_writes_archive_not_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "not-a-real-password")
    apps_dir = tmp_path / "apps"
    config = tmp_path / "config" / "splunk_config.yml"
    config.parent.mkdir()
    config.write_text("plugin: splunk-platform-automator\n")
    before = config.read_text()
    data = download(833, apps_dir, client=FakeClient(by_id={833: _ta()}))
    dest = Path(data["path"])
    assert dest.is_file()
    assert dest.read_bytes() == b"tgz-bytes"
    assert "snippet" not in data
    assert config.read_text() == before
    assert "not-a-real-password" not in str(data)


def test_download_extracts_folder_backed_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "not-a-real-password")
    client = FakeClient(by_id={833: _ta()}, archive=_tgz("Splunk_TA_nix"))
    data = download(833, tmp_path, extract=True, client=client)
    extracted = Path(data["extracted_path"])
    assert extracted == tmp_path / "Splunk_TA_nix"
    assert (extracted / "default" / "app.conf").is_file()
    assert data["path"] == str(extracted)
    assert data["archive_removed"] is True
    assert not list(tmp_path.glob("*.tgz"))


def test_download_extract_refuses_existing_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "not-a-real-password")
    existing = tmp_path / "Splunk_TA_nix"
    existing.mkdir()
    (existing / "keep.txt").write_text("old")
    with pytest.raises(AppsError, match=r"pass --overwrite"):
        download(
            833,
            tmp_path,
            extract=True,
            client=FakeClient(by_id={833: _ta()}, archive=_tgz("Splunk_TA_nix")),
        )
    assert (existing / "keep.txt").read_text() == "old"


def test_download_extract_overwrite_replaces_existing_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "not-a-real-password")
    existing = tmp_path / "Splunk_TA_nix"
    existing.mkdir()
    (existing / "keep.txt").write_text("old")
    data = download(
        833,
        tmp_path,
        extract=True,
        overwrite=True,
        client=FakeClient(by_id={833: _ta()}, archive=_tgz("Splunk_TA_nix")),
    )
    extracted = Path(data["extracted_path"])
    assert extracted == existing
    assert (extracted / "default" / "app.conf").is_file()
    assert not (extracted / "keep.txt").exists()
    assert not list(tmp_path.glob("*.tgz"))


def test_download_overwrite_requires_extract(tmp_path):
    with pytest.raises(AppsError, match=r"--overwrite requires --extract"):
        download(833, tmp_path, overwrite=True, client=FakeClient(by_id={833: _ta()}))
    assert not list(tmp_path.glob("*.tgz"))


def test_download_extract_refuses_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "not-a-real-password")
    client = FakeClient(by_id={833: _ta()}, archive=_tgz("ignored", unsafe_name="../escape"))
    with pytest.raises(AppsError, match="unsafe archive path"):
        download(833, tmp_path, extract=True, client=client)
    assert not (tmp_path.parent / "escape").exists()
    # A failed extract keeps the archive so the operator can retry or inspect it.
    assert list(tmp_path.glob("*.tgz"))


def test_download_prefers_config_credentials_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "env@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "env-not-a-real-password")
    client = FakeClient(by_id={833: _ta()})
    config = {
        "splunk_app_deployment": {
            "splunkbase_username": "config@example.com",
            "splunkbase_password": "config-not-a-real-password",
        }
    }
    download(833, tmp_path, config=config, client=client)
    assert client.login_fields[0]["username"] == "config@example.com"
    assert client.login_fields[0]["password"] == "config-not-a-real-password"


def test_download_resolves_config_env_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "env@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "env-not-a-real-password")
    monkeypatch.setenv("MY_SB_USER", "lookup@example.com")
    monkeypatch.setenv("MY_SB_PASSWORD", "lookup-not-a-real-password")
    client = FakeClient(by_id={833: _ta()})
    config = {
        "splunk_app_deployment": {
            "splunkbase_username": "{{ lookup('env', 'MY_SB_USER') }}",
            "splunkbase_password": "{{ lookup('env', 'MY_SB_PASSWORD') }}",
        }
    }
    download(833, tmp_path, config=config, client=client)
    assert client.login_fields[0]["username"] == "lookup@example.com"
    assert client.login_fields[0]["password"] == "lookup-not-a-real-password"


def test_download_falls_back_to_env_for_vault_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "env@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "env-not-a-real-password")
    client = FakeClient(by_id={833: _ta()})
    config = {
        "splunk_app_deployment": {
            "splunkbase_username": "{{ vault_splunkbase_username }}",
            "splunkbase_password": "{{ vault_splunkbase_password }}",
        }
    }
    download(833, tmp_path, config=config, client=client)
    assert client.login_fields[0]["username"] == "env@example.com"


def test_download_without_credentials_names_both_sources(tmp_path, monkeypatch):
    monkeypatch.delenv("SPLUNKBASE_USERNAME", raising=False)
    monkeypatch.delenv("SPLUNKBASE_PASSWORD", raising=False)
    with pytest.raises(SplunkbaseError) as excinfo:
        download(833, tmp_path, client=FakeClient(by_id={833: _ta()}))
    message = str(excinfo.value)
    assert "SPLUNKBASE_USERNAME: not set" in message
    assert "SPLUNKBASE_PASSWORD: not set" in message
    assert "splunk_app_deployment.splunkbase_username" in message


def test_download_extract_rejects_bundle_kind_before_download(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", "not-a-real-password")
    with pytest.raises(AppsError, match="folder-backed"):
        download(1841, tmp_path, extract=True, client=FakeClient(by_id={1841: _itsi()}))
    assert not list(tmp_path.glob("*.tgz"))


def test_session_search_and_agent_download_requires_yes(tmp_path, monkeypatch):
    env = write_min_env(tmp_path / "env")
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    session = open_session(start_dir=str(env))
    fake = FakeClient(apps=[_ta()], by_id={833: _ta()})

    monkeypatch.setattr(
        "spa.apps.search",
        lambda query, limit=10, client=None, app_type=None, kind=None: search(
            query, limit=limit, client=fake, app_type=app_type, kind=kind
        ),
    )
    result = session.apps(action="search", query="unix")
    assert result.ok
    assert "description" not in (result.data["apps"][0])

    blocked = session.apps(action="download", app_id="833", agent=True, confirm=False)
    assert not blocked.ok
    assert "requires -y/--yes" in (blocked.error or "")


def test_cli_help_and_schema():
    help_result = run_spa(["--no-agent", "apps", "--help"])
    assert help_result.returncode == 0, help_result.stderr
    assert "search" in help_result.stdout
    schema = json.loads(run_spa(["agent", "schema"]).stdout)
    names = {row["name"] for row in schema["data"]["commands"]}
    assert {"apps search", "apps snippet", "apps download"} <= names
    download_row = next(row for row in schema["data"]["commands"] if row["name"] == "apps download")
    assert download_row["requires_confirmation"] is True
    assert "--roles" not in {flag["long"] for flag in download_row.get("flags", [])}
    assert "--extract" in {flag["long"] for flag in download_row.get("flags", [])}
    assert "--overwrite" in {flag["long"] for flag in download_row.get("flags", [])}
    download_help = run_spa(["--no-agent", "apps", "download", "--help"])
    assert download_help.returncode == 0, download_help.stderr
    assert "--roles" not in download_help.stdout
    assert "--extract" in download_help.stdout
    assert "--overwrite" in download_help.stdout
    assert "apps_dir" in download_help.stdout
    snippet_help = run_spa(["--no-agent", "apps", "snippet", "--help"])
    assert snippet_help.returncode == 0, snippet_help.stderr
    assert "--source {splunkbase,local}" in snippet_help.stdout
    assert "--local" in snippet_help.stdout


def test_cli_local_flag_is_shorthand_for_source_local(tmp_path, monkeypatch, capsys):
    env = write_min_env(tmp_path / "env")
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    (apps_dir / "Splunk_TA_nix").mkdir()
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPA_APPS_DIR", str(apps_dir))
    monkeypatch.setattr(
        "spa.apps.get_app",
        lambda app_id, client=None: _ta(),
    )
    from spa.cli import _run

    code = _run(["--no-agent", "apps", "snippet", "833", "--local", "--roles", "indexer"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "source: local" in out
    assert "path: Splunk_TA_nix" in out


def test_cli_search_without_env(monkeypatch, capsys):
    fake = FakeClient(apps=[_ta()])
    monkeypatch.setattr(
        "spa.apps.search",
        lambda query, limit=10, client=None, app_type=None, kind=None: search(
            query, limit=limit, client=fake, app_type=app_type, kind=kind
        ),
    )
    from spa.cli import _run

    code = _run(["--no-agent", "apps", "search", "unix"])
    out = capsys.readouterr().out
    assert code == 0
    assert "833" in out
    assert "Splunk_TA_nix" in out
    assert "password" not in out.lower()
