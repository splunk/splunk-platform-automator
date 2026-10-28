"""spa apps discovery, entry construction, and download (mocked HTTP)."""

from __future__ import annotations

import io
import json
import secrets
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest
from ruamel.yaml import YAML

from spa_testutil import LIB, PROJECT_ROOT, run_spa, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.api import open_session  # noqa: E402
from spa.apps import (  # noqa: E402
    AppsError,
    ITE_WORK_ERROR,
    content_pack_catalog,
    download,
    format_search_text,
    inspect_content_pack_archive,
    search,
    snippet,
    summarize,
)
from spa.splunkbase import SplunkbaseError, _SafeRedirectHandler  # noqa: E402


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


def _content_library_tgz(*, unsafe_name: Optional[str] = None) -> bytes:
    output = io.BytesIO()
    configs = {
        "DA-ITSI-CP-nix/default/app.conf": (
            "[launcher]\n"
            "version = 3.2.1\n"
            "description = Monitor Unix and Linux infrastructure.\n"
            "[ui]\n"
            "label = Unix and Linux\n"
        ),
        "DA-ITSI-CP-windows/default/app.conf": (
            "[launcher]\n"
            "version = 4.5.6\n"
            "[ui]\n"
            "label = Microsoft Windows\n"
        ),
        "DA-ITSI-ContentLibrary/default/app.conf": "[launcher]\nversion = 2.0.0\n",
    }
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        for path, text in configs.items():
            payload = text.encode("utf-8")
            member = tarfile.TarInfo(path)
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
        if unsafe_name:
            payload = b"unsafe"
            member = tarfile.TarInfo(unsafe_name)
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
    return output.getvalue()


def test_content_pack_archive_is_authoritative_and_enriched(tmp_path):
    archive = tmp_path / "DA-ITSI-ContentLibrary_2.0.0.tgz"
    archive.write_bytes(_content_library_tgz())

    packs = inspect_content_pack_archive(archive, spa_home=PROJECT_ROOT)

    assert [row["name"] for row in packs] == [
        "DA-ITSI-CP-nix",
        "DA-ITSI-CP-windows",
    ]
    nix = packs[0]
    assert nix["title"] == "Unix and Linux"
    assert nix["summary"] == "Monitor Unix and Linux infrastructure."
    assert nix["version"] == "3.2.1"
    assert nix["spa_automation"]["hook"] == "run_playbook_after_restart"
    assert "Wire Unix content pack" in nix["spa_automation"]["summary"]
    assert nix["spa_automation"]["prerequisites"] == ["Splunk_TA_nix"]
    assert nix["command"] == (
        "spa apps add 5391 --content-pack DA-ITSI-CP-nix --yes"
    )


def test_content_pack_archive_rejects_unsafe_members(tmp_path):
    archive = tmp_path / "unsafe.tgz"
    archive.write_bytes(_content_library_tgz(unsafe_name="../outside"))
    with pytest.raises(AppsError, match="unsafe archive path"):
        inspect_content_pack_archive(archive, spa_home=PROJECT_ROOT)


def test_content_pack_archive_rejects_command_like_folder_name(tmp_path):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        payload = b"[launcher]\nversion = 1\n"
        member = tarfile.TarInfo(
            "DA-ITSI-CP-nix;touch-pwned/default/app.conf"
        )
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    archive = tmp_path / "unsafe-name.tgz"
    archive.write_bytes(output.getvalue())
    with pytest.raises(AppsError, match="invalid content pack folder"):
        inspect_content_pack_archive(archive, spa_home=PROJECT_ROOT)


def test_content_pack_catalog_prefers_matching_local_archive(tmp_path, capsys):
    archive = tmp_path / "DA-ITSI-ContentLibrary_2.0.0.tgz"
    archive.write_bytes(_content_library_tgz())
    data = content_pack_catalog(
        5391,
        version="2.0.0",
        apps_dir=tmp_path,
        spa_home=PROJECT_ROOT,
        client=FakeClient(by_id={5391: _library()}),
    )
    assert data["app_id"] == 5391
    assert data["version"] == "2.0.0"
    assert data["source"] == "local_archive"
    assert data["total_matches"] == 2
    assert data["truncated"] is False
    assert len(data["packs"]) == 2
    assert "Downloading Content Library" not in capsys.readouterr().err


def test_content_pack_catalog_accepts_latest_local_spl_archive(tmp_path):
    archive = tmp_path / "DA-ITSI-ContentLibrary_2.0.0.spl"
    archive.write_bytes(_content_library_tgz())
    data = content_pack_catalog(
        5391,
        apps_dir=tmp_path,
        spa_home=PROJECT_ROOT,
        client=FakeClient(by_id={}),
    )
    assert data["source"] == "local_archive"
    assert data["version"] == "2.0.0"


def test_content_pack_catalog_uses_temporary_authenticated_download(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", secrets.token_urlsafe(24))
    client = FakeClient(
        by_id={5391: _library()},
        archive=_content_library_tgz(),
    )
    downloads = {"n": 0}
    original = client.get_bytes

    def _count_download(url, headers=None):
        downloads["n"] += 1
        return original(url, headers)

    client.get_bytes = _count_download
    cache_root = tmp_path / "splunk_apps"
    data = content_pack_catalog(
        5391,
        apps_dir=tmp_path / "apps",
        spa_home=PROJECT_ROOT,
        client=client,
        config={"splunk_app_deployment": {"temp_dir": str(cache_root)}},
    )
    assert data["source"] == "cached"
    assert data["version"] == "2.0.0"
    assert downloads["n"] == 1
    assert not list(tmp_path.rglob("*.tgz"))
    cached = (
        cache_root
        / "content_pack_DA-ITSI-ContentLibrary"
        / "content_pack_app_confs"
        / "2.0.0"
        / "DA-ITSI-CP-nix"
        / "default"
        / "app.conf"
    )
    assert cached.is_file()
    library_conf = cached.parents[2] / "DA-ITSI-ContentLibrary" / "default" / "app.conf"
    assert library_conf.is_file()
    assert client.login_fields
    err = capsys.readouterr().err
    assert "Downloading Content Library 5391 (2.0.0) from Splunkbase." in err
    assert "This can take a minute." in err
    assert "No cache is kept." not in err
    assert str(cached.parent.parent.parent) in err

    again = content_pack_catalog(
        5391,
        apps_dir=tmp_path / "apps",
        spa_home=PROJECT_ROOT,
        client=client,
        config={"splunk_app_deployment": {"temp_dir": str(cache_root)}},
    )
    assert again["source"] == "cached"
    assert again["version"] == "2.0.0"
    assert downloads["n"] == 1
    reused = capsys.readouterr().err
    assert "Using cached Content Library 5391 (2.0.0)" in reused
    assert "Downloading Content Library" not in reused


def test_content_pack_cache_replaces_an_older_version_and_keeps_a_requested_one(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", secrets.token_urlsafe(24))
    cache_root = tmp_path / "splunk_apps"
    old = (
        cache_root
        / "content_pack_DA-ITSI-ContentLibrary"
        / "content_pack_app_confs"
        / "2.0.0"
        / "DA-ITSI-CP-nix"
        / "default"
    )
    old.mkdir(parents=True)
    (old / "app.conf").write_text("[ui]\nlabel = Unix and Linux\n", encoding="utf-8")
    newer = _library()
    newer["release"]["title"] = "2.1.0"
    newer["release"]["path"] = "https://splunkbase.splunk.com/app/5391/release/2.1.0/download/"
    client = FakeClient(by_id={5391: newer}, archive=_content_library_tgz())
    config = {"splunk_app_deployment": {"temp_dir": str(cache_root)}}

    pinned = content_pack_catalog(
        5391, version="2.0.0", apps_dir=tmp_path / "apps", spa_home=PROJECT_ROOT, client=client, config=config
    )
    assert pinned["version"] == "2.0.0"
    assert pinned["source"] == "cached"
    assert old.joinpath("app.conf").is_file()
    assert client.login_fields == []

    latest = content_pack_catalog(
        5391, apps_dir=tmp_path / "apps", spa_home=PROJECT_ROOT, client=client, config=config
    )
    assert latest["version"] == "2.1.0"
    assert latest["source"] == "cached"
    assert not old.parent.parent.exists()
    assert (
        cache_root
        / "content_pack_DA-ITSI-ContentLibrary"
        / "content_pack_app_confs"
        / "2.1.0"
        / "DA-ITSI-CP-nix"
        / "default"
        / "app.conf"
    ).is_file()
    assert client.login_fields


def test_content_library_cache_rejects_unsafe_archives(tmp_path, monkeypatch):
    from spa.apps import _store_content_library_cache

    monkeypatch.setattr("spa.apps.MAX_ARCHIVE_EXPANDED_BYTES", 32)
    archive = tmp_path / "library.tgz"
    archive.write_bytes(_content_library_tgz())
    with pytest.raises(AppsError, match="expands beyond"):
        _store_content_library_cache(archive, tmp_path / "cache" / "2.0.0")

    monkeypatch.setattr("spa.apps.MAX_ARCHIVE_EXPANDED_BYTES", 8 * 1024 * 1024 * 1024)
    duplicate = io.BytesIO()
    with tarfile.open(fileobj=duplicate, mode="w:gz") as bundle:
        for _unused in range(2):
            payload = b"[ui]\nlabel = Unix\n"
            member = tarfile.TarInfo("DA-ITSI-CP-nix/default/app.conf")
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
    dup_path = tmp_path / "duplicate.tgz"
    dup_path.write_bytes(duplicate.getvalue())
    with pytest.raises(AppsError, match="duplicate"):
        _store_content_library_cache(dup_path, tmp_path / "cache" / "2.0.0")

    invalid = io.BytesIO()
    with tarfile.open(fileobj=invalid, mode="w:gz") as bundle:
        payload = b"[ui]\nlabel = Unix\n"
        member = tarfile.TarInfo("DA-ITSI-CP-bad name/default/app.conf")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    invalid_path = tmp_path / "invalid.tgz"
    invalid_path.write_bytes(invalid.getvalue())
    with pytest.raises(AppsError, match="invalid content pack folder"):
        _store_content_library_cache(invalid_path, tmp_path / "cache" / "2.0.0")


def test_content_library_cache_rejects_unsafe_members(tmp_path, monkeypatch):
    from spa.apps import _store_content_library_cache

    def _archive(members) -> bytes:
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as bundle:
            for member, payload in members:
                bundle.addfile(member, io.BytesIO(payload) if payload is not None else None)
        return output.getvalue()

    unsafe = tmp_path / "unsafe.tgz"
    escaped = tarfile.TarInfo("../DA-ITSI-CP-nix/default/app.conf")
    body = b"[ui]\nlabel = Unix\n"
    escaped.size = len(body)
    unsafe.write_bytes(_archive([(escaped, body)]))
    with pytest.raises(AppsError, match="unsafe archive path"):
        _store_content_library_cache(unsafe, tmp_path / "cache" / "2.0.0")

    linked = tmp_path / "link.tgz"
    symlink = tarfile.TarInfo("DA-ITSI-CP-nix/default/app.conf")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "elsewhere"
    linked.write_bytes(_archive([(symlink, None)]))
    with pytest.raises(AppsError, match="unsafe archive member"):
        _store_content_library_cache(linked, tmp_path / "cache" / "2.0.0")

    monkeypatch.setattr("spa.apps.MAX_APP_CONF_BYTES", 4)
    oversized = tmp_path / "oversize.tgz"
    big = tarfile.TarInfo("DA-ITSI-CP-nix/default/app.conf")
    big.size = len(body)
    oversized.write_bytes(_archive([(big, body)]))
    with pytest.raises(AppsError, match="exceeds 4 bytes"):
        _store_content_library_cache(oversized, tmp_path / "cache" / "2.0.0")

    monkeypatch.setattr("spa.apps.MAX_APP_CONF_BYTES", 256 * 1024)
    monkeypatch.setattr("spa.apps.MAX_ARCHIVE_MEMBERS", 1)
    crowded = tmp_path / "crowded.tgz"
    first = tarfile.TarInfo("readme.txt")
    first.size = 1
    second = tarfile.TarInfo("DA-ITSI-CP-nix/default/app.conf")
    second.size = len(body)
    crowded.write_bytes(_archive([(first, b"x"), (second, body)]))
    with pytest.raises(AppsError, match="more than 1 members"):
        _store_content_library_cache(crowded, tmp_path / "cache" / "2.0.0")


def test_content_pack_catalog_rejects_an_unsafe_version(tmp_path):
    with pytest.raises(AppsError, match="unsafe Content Library version"):
        content_pack_catalog(
            5391,
            version="../2.0.0",
            apps_dir=tmp_path / "apps",
            config={"splunk_app_deployment": {"temp_dir": str(tmp_path / "cache")}},
        )
    assert not (tmp_path / "cache").exists()


def test_content_pack_catalog_uses_the_configured_library_name(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", secrets.token_urlsafe(24))
    cache_root = tmp_path / "splunk_apps"
    install_dir = cache_root / "content_pack_Library_Alias"
    kept = install_dir / "content_pack_Library_Alias_2.0.0.tgz"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(_content_library_tgz())
    client = FakeClient(by_id={5391: _library()}, archive=_content_library_tgz())
    catalog = content_pack_catalog(
        5391,
        version="2.0.0",
        apps_dir=tmp_path / "apps",
        spa_home=PROJECT_ROOT,
        client=client,
        config={
            "splunk_app_deployment": {
                "temp_dir": str(cache_root),
                "apps": [{"name": "Library Alias", "app_id": 5391}],
            }
        },
    )
    assert catalog["source"] == "install_cache"
    assert catalog["version"] == "2.0.0"
    assert kept.is_file()
    assert client.login_fields == []


def test_content_pack_catalog_keeps_an_existing_install_archive(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", secrets.token_urlsafe(24))
    cache_root = tmp_path / "splunk_apps"
    install_dir = cache_root / "content_pack_DA-ITSI-ContentLibrary"
    kept = install_dir / "content_pack_DA-ITSI-ContentLibrary_2.0.0.tgz"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(_content_library_tgz())
    stale = install_dir / "content_pack_app_confs" / "1.9.0" / "DA-ITSI-CP-nix" / "default"
    stale.mkdir(parents=True)
    (stale / "app.conf").write_text("[ui]\nlabel = Old\n", encoding="utf-8")
    client = FakeClient(by_id={5391: _library()}, archive=_content_library_tgz())
    downloads = {"n": 0}
    original = client.get_bytes

    def _count_download(url, headers=None):
        downloads["n"] += 1
        return original(url, headers)

    client.get_bytes = _count_download
    config = {"splunk_app_deployment": {"temp_dir": str(cache_root)}}

    pinned = content_pack_catalog(
        5391,
        version="2.0.0",
        apps_dir=tmp_path / "apps",
        spa_home=PROJECT_ROOT,
        client=client,
        config=config,
    )
    assert pinned["source"] == "install_cache"
    assert pinned["version"] == "2.0.0"
    assert pinned["total_matches"] == 2
    assert kept.is_file()
    assert downloads["n"] == 0
    assert client.login_fields == []
    err = capsys.readouterr().err
    assert str(kept) in err
    assert "Downloading Content Library" not in err

    latest = content_pack_catalog(
        5391,
        apps_dir=tmp_path / "apps",
        spa_home=PROJECT_ROOT,
        client=client,
        config=config,
    )
    assert latest["source"] == "install_cache"
    assert latest["version"] == "2.0.0"
    assert kept.is_file()
    assert downloads["n"] == 0
    assert not stale.parent.parent.exists()

    newer = _library()
    newer["release"]["title"] = "2.1.0"
    newer["release"]["path"] = "https://splunkbase.splunk.com/app/5391/release/2.1.0/download/"
    client.by_id[5391] = newer
    moved = content_pack_catalog(
        5391,
        apps_dir=tmp_path / "apps",
        spa_home=PROJECT_ROOT,
        client=client,
        config=config,
    )
    assert moved["version"] == "2.1.0"
    assert moved["source"] == "cached"
    assert kept.is_file()
    assert downloads["n"] == 1
    assert list(cache_root.rglob("*.tgz")) == [kept]
    assert (
        install_dir
        / "content_pack_app_confs"
        / "2.1.0"
        / "DA-ITSI-CP-nix"
        / "default"
        / "app.conf"
    ).is_file()


def test_content_pack_catalog_rejects_download_over_transport_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLUNKBASE_USERNAME", "user@example.com")
    monkeypatch.setenv("SPLUNKBASE_PASSWORD", secrets.token_urlsafe(24))
    monkeypatch.setattr("spa.splunkbase.MAX_DOWNLOAD_BYTES", 1)
    with pytest.raises(SplunkbaseError, match="maximum download size"):
        content_pack_catalog(
            5391,
            apps_dir=tmp_path,
            spa_home=PROJECT_ROOT,
            client=FakeClient(
                by_id={5391: _library()},
                archive=_content_library_tgz(),
            ),
        )


def test_content_pack_catalog_refuses_lookalike_download_host(tmp_path):
    library = _library()
    library["release"]["path"] = (
        "https://splunkbase.splunk.com.evil.example/app/5391/download/"
    )
    with pytest.raises(AppsError, match="Refusing download URL host"):
        content_pack_catalog(
            5391,
            apps_dir=tmp_path,
            spa_home=PROJECT_ROOT,
            client=FakeClient(by_id={5391: library}),
        )


def test_authenticated_redirect_drops_token_across_origins_and_https_downgrade():
    handler = _SafeRedirectHandler()
    request = urllib.request.Request(
        "https://splunkbase.splunk.com/download",
        headers={"X-Auth-Token": secrets.token_urlsafe(24)},
    )
    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://downloads.example/archive.tgz",
    )
    assert redirected is not None
    assert redirected.get_header("X-Auth-Token") is None
    assert (
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://splunkbase.splunk.com/archive.tgz",
        )
        is None
    )


def test_content_pack_archive_rejects_malformed_archive(tmp_path):
    archive = tmp_path / "broken.tgz"
    archive.write_bytes(b"not an archive")
    with pytest.raises(AppsError, match="Could not inspect"):
        inspect_content_pack_archive(archive, spa_home=PROJECT_ROOT)


def test_content_pack_archive_enforces_expanded_size_limit(tmp_path, monkeypatch):
    archive = tmp_path / "large-expanded.tgz"
    archive.write_bytes(_content_library_tgz())
    monkeypatch.setattr("spa.apps.MAX_ARCHIVE_EXPANDED_BYTES", 1)
    with pytest.raises(AppsError, match="expands beyond"):
        inspect_content_pack_archive(archive, spa_home=PROJECT_ROOT)


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


def test_search_itsi_fetches_library_5391_when_missing_from_page():
    client = FakeClient(apps=[_itsi(), _pack()], by_id={5391: _library()})
    data = search("itsi", limit=10, client=client)
    ids = [row["app_id"] for row in data["apps"]]
    assert ids[:2] == [1841, 5391]
    assert ids.count(5391) == 1


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


def test_snippet_omits_default_splunkbase_source():
    """CFG-APP-002: generated Splunkbase entries omit the default source."""
    data = snippet(833, roles=["indexer"], client=FakeClient(by_id={833: _ta()}))
    assert "source: splunkbase" not in data["snippet"]


def test_snippet_comment_is_title_only():
    data = snippet(833, client=FakeClient(by_id={833: _ta()}))
    comments = [line for line in data["snippet"].splitlines() if line.startswith("#")]
    assert comments == ["# Splunk Add-on for Unix and Linux"]
    assert "splunkbase.splunk.com" not in data["snippet"]
    assert "rapid insights" not in data["snippet"]


def test_snippet_itsi_rejects_target_roles():
    with pytest.raises(AppsError, match="--roles is not valid"):
        snippet(1841, roles=["search_head"], client=FakeClient(by_id={1841: _itsi()}))


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
        lambda query, limit=10, client=None, app_type=None, kind=None, spa_home=None: search(
            query, limit=limit, client=fake, app_type=app_type, kind=kind, spa_home=spa_home
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
    assert "content-packs" in help_result.stdout
    schema = json.loads(run_spa(["agent", "schema"]).stdout)
    names = {row["name"] for row in schema["data"]["commands"]}
    assert {
        "apps search",
        "apps snippet",
        "apps content-packs list",
        "apps download",
    } <= names
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
    assert "--customize" in snippet_help.stdout
    add_help = run_spa(["--no-agent", "apps", "add", "--help"])
    assert add_help.returncode == 0, add_help.stderr
    for phrase in (
        "App kinds:",
        "Normal app",
        "ITSI 1841",
        "Content Library 5391",
        "Recognized single pack",
        "edits splunk_config.yml but does not deploy",
        "spa apps content-packs list 5391",
        "--content-pack NAME",
        "mutually exclusive",
        "strict JSON",
        "spa validate",
        "spa deploy --yes",
    ):
        assert phrase in add_help.stdout
    assert "Splunkbase app ID or local app folder name" in add_help.stdout


def test_cli_content_pack_catalog_from_explicit_archive(tmp_path, capsys):
    archive = tmp_path / "library.tgz"
    archive.write_bytes(_content_library_tgz())
    from spa.cli import _run

    code = _run(
        [
            "--agent",
            "apps",
            "content-packs",
            "list",
            "5391",
            "--archive",
            str(archive),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["source"] == "archive"
    assert payload["data"]["version"] == "2.0.0"
    assert payload["data"]["packs"][0]["name"] == "DA-ITSI-CP-nix"

    code = _run(
        [
            "--no-agent",
            "apps",
            "content-packs",
            "list",
            "5391",
            "--archive",
            str(archive),
        ]
    )
    text = capsys.readouterr().out
    assert code == 0
    assert "DA-ITSI-CP-nix" in text
    assert "Unix and Linux" in text
    assert "SPA automation:" in text
    assert "spa apps add 5391 --content-pack DA-ITSI-CP-nix --yes" in text


def test_explicit_content_pack_archive_rejects_mismatched_version(tmp_path):
    archive = tmp_path / "library.tgz"
    archive.write_bytes(_content_library_tgz())
    with pytest.raises(AppsError, match="does not match archive version"):
        content_pack_catalog(
            5391,
            version="9.9.9",
            archive=archive,
            spa_home=PROJECT_ROOT,
        )


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


def test_cli_agent_add_and_remove_edit_config_without_yes(tmp_path, monkeypatch, capsys):
    """CFG-CLI-003 CFG-APP-003 CFG-APP-008."""
    env = write_min_env(tmp_path / "env")
    config = env / "config" / "splunk_config.yml"
    config.write_text(
        "plugin: splunk-platform-automator\n"
        "splunk_defaults:\n"
        "  splunk_admin_password: \"{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}\"\n"
        "splunk_hosts:\n"
        "  - name: idx\n"
        "    roles: [indexer]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(env))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setattr("spa.apps.get_app", lambda app_id, client=None: _ta())
    from spa.cli import _run

    assert _run(
        ["--agent", "--start-dir", str(env), "apps", "add", "833", "--roles", "indexer"]
    ) == 0
    added = json.loads(capsys.readouterr().out)
    assert added["data"]["changed"] is True
    authored = YAML(typ="safe").load(config.read_text(encoding="utf-8"))
    assert authored["splunk_app_deployment"]["apps"][0]["app_id"] == 833

    assert _run(
        ["--agent", "--start-dir", str(env), "apps", "remove", "833"]
    ) == 0
    removed = json.loads(capsys.readouterr().out)
    assert removed["data"]["changed"] is True
    assert YAML(typ="safe").load(
        config.read_text(encoding="utf-8")
    )["splunk_app_deployment"]["apps"] == []


def test_cli_search_without_env(monkeypatch, capsys):
    fake = FakeClient(apps=[_ta()])
    monkeypatch.setattr(
        "spa.apps.search",
        lambda query, limit=10, client=None, app_type=None, kind=None, spa_home=None: search(
            query, limit=limit, client=fake, app_type=app_type, kind=kind, spa_home=spa_home
        ),
    )
    from spa.cli import _run

    code = _run(["--no-agent", "apps", "search", "unix"])
    out = capsys.readouterr().out
    assert code == 0
    assert "833" in out
    assert "Splunk_TA_nix" in out
    assert "password" not in out.lower()


def test_snippet_advertises_curated_playbook_without_attaching(tmp_path):
    data = snippet(
        833,
        roles=["indexer"],
        spa_home=PROJECT_ROOT,
        client=FakeClient(by_id={833: _ta()}),
    )
    assert "pass --customize" in data["snippet"]
    assert "  customizations:" not in data["snippet"]
    assert data["playbooks"][0]["kind"] == "ta"
    assert data["playbooks"][0]["hook"] == "run_playbook"
    assert "Splunk_TA_nix-enable_perf_metrics.yml" in data["playbooks"][0]["path"]


def test_snippet_customize_adds_run_playbook():
    data = snippet(
        833,
        roles=["indexer"],
        spa_home=PROJECT_ROOT,
        customize=True,
        client=FakeClient(by_id={833: _ta()}),
    )
    assert "  customizations:" in data["snippet"]
    assert "    run_playbook: ansible/apps_playbooks/Splunk_TA_nix-enable_perf_metrics.yml" in data["snippet"]
    assert "ta_nix_script_index: itsi_im_metrics" in data["snippet"]
    assert "pass --customize" not in data["snippet"]
    assert data["entry"]["customizations"]["run_playbook"].endswith(
        "Splunk_TA_nix-enable_perf_metrics.yml"
    )


def test_snippet_content_pack_playbook_does_not_match_ta():
    data = snippet(833, spa_home=PROJECT_ROOT, client=FakeClient(by_id={833: _ta()}))
    paths = [row["path"] for row in data.get("playbooks") or []]
    assert all("DA-ITSI-CP" not in path for path in paths)


def test_snippet_customize_snow_uses_env_lookup_not_password():
    snow = {
        "uid": 1928,
        "appid": "Splunk_TA_snow",
        "title": "Splunk Add-on for ServiceNow",
        "type": "addon",
        "release": {"title": "1.0.0", "path": "https://splunkbase.splunk.com/app/1928/release/1.0.0/download"},
    }
    data = snippet(
        1928,
        spa_home=PROJECT_ROOT,
        customize=True,
        client=FakeClient(by_id={1928: snow}),
    )
    assert "lookup('env', 'SNOW_PASSWORD')" in data["snippet"]
    assert "not-a-real-password" not in data["snippet"]
    assert "snow_password:" in data["snippet"]


def _itsi_hits():
    return [
        {
            "app_id": 1841,
            "name": "itsi",
            "title": "Splunk IT Service Intelligence",
            "type": "app",
            "kind": "premium_itsi",
            "version": "5.0.2",
            "summary": "ITSI monitoring",
        },
        {
            "app_id": 3598,
            "name": "xmatters_itsi",
            "title": "xMatters for Splunk ITSI",
            "type": "app",
            "kind": "ta",
            "version": "1.7.4",
            "summary": "xMatters integration",
        },
        {
            "app_id": 5391,
            "name": "DA-ITSI-ContentLibrary",
            "title": "Splunk IT Service Intelligence Content Library",
            "type": "app",
            "kind": "itsi_content_library",
            "version": "2.5.1",
            "summary": "Content packs library",
        },
        {
            "app_id": 7375,
            "name": "DA-ITSI-CP-CUST-ATLAS-PFSENSE",
            "title": "Atlas ITSI Content Pack for Pfsense",
            "type": "addon",
            "kind": "itsi_content_pack_single",
            "version": "1.0.0",
            "summary": "pfSense content pack",
        },
    ]


def test_search_human_text_groups_itsi_hits_into_sections():
    lines = format_search_text("itsi", _itsi_hits()).splitlines()
    core = lines.index("Core ITSI")
    library = lines.index("Content packs (from Library 5391)")
    single = lines.index("Single content packs")
    other = lines.index("Other apps")
    assert core < library < single < other
    assert lines[core + 1].startswith("1841 | ")
    assert library < next(i for i, line in enumerate(lines) if line.startswith("5391 | "))
    assert single < next(i for i, line in enumerate(lines) if line.startswith("7375 | "))
    assert other < next(i for i, line in enumerate(lines) if line.startswith("3598 | "))


def test_search_human_text_library_section_shows_pack_commands():
    text = format_search_text("itsi", _itsi_hits())
    library_part = text.split("Content packs (from Library 5391)", 1)[1].split("Single content packs", 1)[0]
    assert "spa apps content-packs list 5391" in library_part
    assert "spa apps add 5391 --content-pack NAME" in library_part


def test_search_human_text_single_pack_names_core_itsi_dependency():
    text = format_search_text("itsi", _itsi_hits())
    single_part = text.split("Single content packs", 1)[1].split("Other apps", 1)[0]
    assert "spa apps add 7375" in single_part
    assert "1841" in single_part


def test_search_human_text_without_itsi_hits_keeps_flat_list():
    rows = [
        {"app_id": 833, "name": "Splunk_TA_nix", "title": "Unix", "type": "addon", "kind": "ta"},
        {"app_id": 1928, "name": "Splunk_TA_snow", "title": "ServiceNow", "type": "addon", "kind": "ta"},
    ]
    lines = format_search_text("unix", rows).splitlines()
    assert lines[0].startswith("833 | ")
    assert lines[1].startswith("1928 | ")
    assert "Core ITSI" not in format_search_text("unix", rows)


def test_search_marks_playbook_on_matching_hit():
    result = search("unix", spa_home=PROJECT_ROOT, client=FakeClient(apps=[_ta()]))
    assert result["apps"][0]["playbook"] is True
    text = format_search_text("unix", result["apps"])
    assert "playbook" in text.splitlines()[0]


def test_snippet_customize_sim_uses_env_lookup_not_token():
    sim = {
        "uid": 5247,
        "appid": "splunk_ta_sim",
        "title": "Splunk Infrastructure Monitoring Add-on",
        "type": "addon",
        "release": {"title": "1.0.0", "path": "https://splunkbase.splunk.com/app/5247/release/1.0.0/download"},
    }
    data = snippet(
        5247,
        spa_home=PROJECT_ROOT,
        customize=True,
        client=FakeClient(by_id={5247: sim}),
    )
    assert "run_playbook_after_restart: ansible/apps_playbooks/splunk_ta_sim-configure.yml" in data["snippet"]
    assert "lookup('env', 'O11Y_API_TOKEN')" in data["snippet"]
    assert "not-a-real-token" not in data["snippet"]
    extra = data["playbooks"][0]["extra_vars"]
    assert {"name": "o11y_api_token", "required": True} in extra
    assert all("env" not in item for item in extra)


def test_search_library_does_not_mark_content_pack_playbooks():
    library = {
        "uid": 5391,
        "appid": "DA-ITSI-ContentLibrary",
        "title": "Splunk ITSI Content Pack Library",
        "type": "app",
        "description": "library",
        "release": {"title": "1.0.0", "path": "https://splunkbase.splunk.com/app/5391/release/1.0.0/download"},
    }
    result = search("itsi", spa_home=PROJECT_ROOT, client=FakeClient(apps=[library]))
    assert result["apps"][0]["app_id"] == 5391
    assert "playbook" not in result["apps"][0]
