"""spa apps: Splunkbase search, snippet, and download (no config write)."""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlparse

from spa.splunkbase import (
    SplunkbaseError,
    download_release,
    get_app,
    search_apps,
)

ITE_WORK_ID = 5403
ITSI_ID = 1841
CONTENT_LIBRARY_ID = 5391
ES_ID = 263
SINGLE_PACK_IDS = frozenset({7294})

SUMMARY_CHARS = 100
ITE_WORK_ERROR = (
    "use app_id 1841 (premium_app: itsi); ITE Work is unlicensed ITSI, not a separate SPA app."
)
# Splunkbase list `type` values we expose; SPA `kind` is classify_kind() minus ITE Work.
SEARCH_TYPES = ("app", "addon")
SEARCH_KINDS = (
    "ta",
    "premium_itsi",
    "itsi_content_library",
    "itsi_content_pack_single",
    "es_not_premium",
)
_WORD = re.compile(r"[a-z0-9]+")
# Whole-word query tokens that pin a Splunkbase app_id first (fetch if missing).
PINNED_SEARCH = (
    ("itsi", ITSI_ID, "app", "premium_itsi"),
    ("es", ES_ID, "app", "es_not_premium"),
)

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FOLDER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


class AppsError(ValueError):
    """Operator-facing apps error (no secrets)."""


def parse_app_id(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        raise AppsError("spa apps: app_id must be an integer")
    if isinstance(value, int):
        if value < 1:
            raise AppsError("spa apps: app_id must be an integer")
        return value
    text = str(value).strip()
    if not text.isdigit():
        raise AppsError("spa apps: app_id must be an integer")
    number = int(text)
    if number < 1:
        raise AppsError("spa apps: app_id must be an integer")
    return number


def folder_appid(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text or _UUID.match(text):
        return None
    if not _FOLDER.match(text):
        return None
    return text


def _one_line(text: Any) -> str:
    cleaned = _HTML.sub(" ", str(text or ""))
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned


def summarize(description: Any, limit: int = SUMMARY_CHARS) -> str:
    line = _one_line(description)
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def latest_version(app: Dict[str, Any]) -> str:
    release = app.get("release")
    if isinstance(release, dict) and release.get("title"):
        return str(release["title"]).strip()
    releases = app.get("releases")
    if isinstance(releases, list) and releases:
        first = releases[0]
        if isinstance(first, dict) and first.get("title"):
            return str(first["title"]).strip()
    return ""


def release_download_url(app: Dict[str, Any], version: str) -> str:
    wanted = (version or "").strip() or "latest"
    release = app.get("release") if isinstance(app.get("release"), dict) else {}
    if wanted in {"", "latest"}:
        path = (release or {}).get("path")
        if path:
            return str(path)
    releases = app.get("releases") if isinstance(app.get("releases"), list) else []
    for item in releases:
        if not isinstance(item, dict):
            continue
        if str(item.get("title") or "").strip() == wanted and item.get("path"):
            return str(item["path"])
    if wanted not in {"", "latest"} and (release or {}).get("title") == wanted:
        path = (release or {}).get("path")
        if path:
            return str(path)
    raise AppsError("No Splunkbase release download URL for version %s" % wanted)


def classify_kind(app_id: int, app: Optional[Dict[str, Any]] = None) -> str:
    if app_id == ITE_WORK_ID:
        return "itsi_essentials_work"
    if app_id == ITSI_ID:
        return "premium_itsi"
    if app_id == CONTENT_LIBRARY_ID:
        return "itsi_content_library"
    if app_id == ES_ID:
        return "es_not_premium"
    if app_id in SINGLE_PACK_IDS:
        return "itsi_content_pack_single"
    appid = folder_appid((app or {}).get("appid"))
    title = str((app or {}).get("title") or "").lower()
    if appid and appid.startswith("DA-ITSI-CP"):
        return "itsi_content_pack_single"
    if "content pack" in title and "library" not in title:
        return "itsi_content_pack_single"
    return "ta"


def parse_search_filter(value: Any, allowed: Sequence[str], flag: str) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lookup = {item.lower(): item for item in allowed}
    key = text.lower()
    if key not in lookup:
        raise AppsError("spa apps search %s must be one of: %s" % (flag, ", ".join(allowed)))
    return lookup[key]


def _query_tokens(query: str) -> set:
    return set(_WORD.findall((query or "").lower()))


def _wanted_pins(
    query: str,
    wanted_type: Optional[str],
    wanted_kind: Optional[str],
) -> List[int]:
    tokens = _query_tokens(query)
    pins: List[int] = []
    for token, app_id, app_type, kind in PINNED_SEARCH:
        if token not in tokens:
            continue
        if wanted_type not in (None, app_type):
            continue
        if wanted_kind not in (None, kind):
            continue
        pins.append(app_id)
    return pins


def _pin_ids(hits: List[Dict[str, Any]], app_ids: Sequence[int]) -> List[Dict[str, Any]]:
    wanted = list(app_ids)
    skip = set(wanted)
    head = []
    for app_id in wanted:
        head.extend(row for row in hits if row.get("app_id") == app_id)
    rest = [row for row in hits if row.get("app_id") not in skip]
    return head + rest


def _matches_filters(
    row: Dict[str, Any],
    wanted_type: Optional[str],
    wanted_kind: Optional[str],
) -> bool:
    if wanted_type and (row.get("type") or "") != wanted_type:
        return False
    if wanted_kind and (row.get("kind") or "") != wanted_kind:
        return False
    return True


def _comment_block(title: str, extra: Sequence[str] = ()) -> List[str]:
    lines = ["# %s" % _one_line(title)] if title else []
    for item in extra:
        text = str(item).strip()
        if text:
            lines.append("# %s" % text)
    return lines


def _yaml_roles(roles: Optional[Sequence[str]]) -> str:
    names = [str(item).strip() for item in (roles or []) if str(item).strip()]
    if not names:
        return "[]"
    return "[%s]" % ", ".join(names)


def _entry_name(kind: str, app: Dict[str, Any], app_id: int) -> str:
    if kind == "premium_itsi":
        return "Splunk IT Service Intelligence"
    if kind == "itsi_content_library":
        return folder_appid(app.get("appid")) or "DA-ITSI-ContentLibrary"
    name = folder_appid(app.get("appid"))
    if name:
        return name
    raise AppsError(
        "Splunkbase app_id %s has no folder-like appid; cannot set apps[].name" % app_id
    )


def _ta_keys(
    name: str,
    app_id: int,
    version: str,
    roles: Optional[Sequence[str]],
    *,
    source: str,
    path: Optional[str] = None,
) -> List[str]:
    lines = [
        "- name: %s" % name,
        "  source: %s" % source,
    ]
    if source == "splunkbase":
        lines.append("  app_id: %s" % app_id)
        if version and version != "latest":
            lines.append("  version: %s" % version)
        else:
            lines.append("  version: latest")
    else:
        if path:
            lines.append("  path: %s" % path)
    lines.append("  target_roles: %s" % _yaml_roles(roles))
    return lines


def format_snippet_yaml(
    app: Dict[str, Any],
    *,
    app_id: int,
    kind: str,
    version: str,
    roles: Optional[Sequence[str]] = None,
    source: str = "splunkbase",
    path: Optional[str] = None,
    roles_ignored: bool = False,
    notes: Sequence[str] = (),
) -> str:
    title = str(app.get("title") or "").strip()
    extra: List[str] = [str(note) for note in notes if str(note).strip()]
    if roles_ignored:
        extra.append("--roles is ignored for this kind (no target_roles).")
    name = _entry_name(kind, app, app_id)
    if kind == "premium_itsi":
        extra[0:0] = [
            "SPA premium_app: itsi. No target_roles.",
            "Java 21 on the search/ITSI host; Enterprise + ITSI license files.",
        ]
        body = [
            "- name: %s" % name,
            "  source: %s" % source,
        ]
        if source == "splunkbase":
            body += ["  app_id: %s" % app_id, "  premium_app: itsi"]
        else:
            if path:
                body.append("  path: %s" % path)
            body.append("  premium_app: itsi")
    elif kind == "itsi_content_library":
        extra.insert(0, "Requires a sibling premium_app: itsi (app_id 1841). Fill content_pack_apps.")
        body = [
            "- name: %s" % name,
            "  source: %s" % source,
        ]
        if source == "splunkbase":
            body.append("  app_id: %s" % app_id)
        elif path:
            body.append("  path: %s" % path)
        body += ["  itsi_content_pack: true", "  content_pack_apps: []"]
    elif kind == "itsi_content_pack_single":
        extra.insert(0, "Requires a sibling premium_app: itsi (app_id 1841).")
        body = [
            "- name: %s" % name,
            "  source: %s" % source,
        ]
        if source == "splunkbase":
            body.append("  app_id: %s" % app_id)
        elif path:
            body.append("  path: %s" % path)
        body += [
            "  itsi_content_pack: true",
            "  content_pack_api:",
            "    install_all: true",
            "    enabled: true",
        ]
    elif kind == "es_not_premium":
        extra.insert(0, "Enterprise Security is not premium_app: es yet (#60). TA-shaped snippet only.")
        body = _ta_keys(name, app_id, version, roles, source=source, path=path)
    else:
        body = _ta_keys(name, app_id, version, roles, source=source, path=path)
    return "\n".join(_comment_block(title, extra) + body) + "\n"


def project_hit(app: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    app_id = parse_app_id(app.get("uid") or app.get("app_id"))
    if app_id == ITE_WORK_ID:
        return None
    kind = classify_kind(app_id, app)
    name = folder_appid(app.get("appid"))
    row: Dict[str, Any] = {
        "app_id": app_id,
        "title": _one_line(app.get("title")),
        "type": str(app.get("type") or "").strip(),
        "kind": kind,
        "summary": summarize(app.get("description")),
    }
    version = latest_version(app)
    if version:
        row["version"] = version
    if name:
        row["name"] = name
    return row


def format_search_text(query: str, hits: Sequence[Dict[str, Any]]) -> str:
    if not hits:
        return "No Splunkbase apps matched %r\n" % query
    lines = []
    for row in hits:
        name = row.get("name") or "-"
        fields = [
            str(row.get("app_id") or ""),
            name,
            row.get("type") or "",
            row.get("kind") or "",
            row.get("version") or "",
            row.get("title") or "",
        ]
        first = " | ".join(fields)
        lines.append(first)
        summary = row.get("summary") or ""
        if summary:
            indent = " " * (len(str(row.get("app_id") or "")) + len(" | "))
            lines.append("%s%s" % (indent, summary))
    return "\n".join(lines) + "\n"


def search(
    query: str,
    *,
    limit: int = 10,
    app_type: Optional[str] = None,
    kind: Optional[str] = None,
    client=None,
) -> Dict[str, Any]:
    wanted_type = parse_search_filter(app_type, SEARCH_TYPES, "--type")
    wanted_kind = parse_search_filter(kind, SEARCH_KINDS, "--kind")
    fetch = max(limit, 1) + 4
    if wanted_type or wanted_kind:
        fetch = max(fetch, min(50, max(limit, 1) * 5))
    raw = search_apps(query, limit=fetch, client=client)
    hits: List[Dict[str, Any]] = []
    seen: set = set()
    for app in raw:
        try:
            row = project_hit(app)
        except (AppsError, SplunkbaseError):
            continue
        if row is None or not _matches_filters(row, wanted_type, wanted_kind):
            continue
        hits.append(row)
        seen.add(row["app_id"])
        if len(hits) >= fetch:
            break
    pins = _wanted_pins(query, wanted_type, wanted_kind)
    for app_id in pins:
        if app_id in seen:
            continue
        try:
            extra = project_hit(get_app(app_id, client=client))
        except (AppsError, SplunkbaseError):
            extra = None
        if extra is not None and _matches_filters(extra, wanted_type, wanted_kind):
            hits.append(extra)
            seen.add(app_id)
    if pins:
        hits = _pin_ids(hits, pins)
    return {"query": query, "apps": hits[:limit]}


def _refuse_ite_work(app_id: int) -> None:
    if app_id == ITE_WORK_ID:
        raise AppsError(ITE_WORK_ERROR)


def snippet(
    app_id_raw: Any,
    *,
    version: str = "latest",
    roles: Optional[Sequence[str]] = None,
    source: str = "splunkbase",
    apps_dir: Optional[Path] = None,
    client=None,
) -> Dict[str, Any]:
    if source not in {"splunkbase", "local"}:
        raise AppsError("spa apps snippet --source must be one of: splunkbase, local")
    custom_name = folder_appid(app_id_raw) if source == "local" else None
    is_custom = custom_name is not None and not str(app_id_raw).strip().isdigit()
    if is_custom:
        app_id: Optional[int] = None
        app = {"appid": custom_name, "title": custom_name}
        kind = "ta"
    else:
        app_id = parse_app_id(app_id_raw)
        _refuse_ite_work(app_id)
        app = get_app(app_id, client=client)
        kind = classify_kind(app_id, app)
    roles_ignored = bool(roles) and kind not in {"ta", "es_not_premium"}
    use_roles = None if roles_ignored else roles
    resolved = latest_version(app) if (not version or version == "latest") else version
    local_path: Optional[str] = None
    notes: List[str] = []
    name = str(custom_name) if is_custom else _entry_name(kind, app, int(app_id))
    if source == "local":
        if apps_dir is None:
            raise AppsError("spa apps snippet --source local requires an environment with apps_dir")
        found = _local_source(
            Path(apps_dir), name, resolved or version or "latest", kind, app_id
        )
        local_path = found.name
        # Deploy rsyncs a folder for normal apps; only ITSI/content packs take an archive.
        if found.is_file() and kind in {"ta", "es_not_premium"}:
            hint = (
                "spa apps download %s --extract --yes" % app_id
                if app_id is not None
                else "unpack it in apps_dir"
            )
            notes.append("Archive found; normal apps deploy from a folder — %s." % hint)
    yaml_text = format_snippet_yaml(
        app,
        app_id=int(app_id or 0),
        kind=kind,
        version=version or "latest",
        roles=use_roles,
        source=source,
        path=local_path,
        roles_ignored=roles_ignored,
        notes=notes,
    )
    data: Dict[str, Any] = {
        "kind": kind,
        "title": _one_line(app.get("title")),
        "name": name,
        "source": source,
        "version": resolved or version or "latest",
        "snippet": yaml_text,
    }
    if app_id is not None:
        data["app_id"] = app_id
    if local_path:
        data["path"] = local_path
    return data


def _safe_filename(name: str, version: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "app"
    ver = re.sub(r"[^A-Za-z0-9._-]+", "_", version).strip("._") or "latest"
    return "%s_%s.tgz" % (stem, ver)


def _archive_candidates(apps_dir: Path, name: str, version: str) -> List[Path]:
    exact = apps_dir / _safe_filename(name, version)
    candidates = [exact] if exact.is_file() else []
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "app"
    patterns = (
        "%s_*.tgz" % stem,
        "%s_*.tar.gz" % stem,
        "%s_*.spl" % stem,
        "%s.tgz" % stem,
        "%s.tar.gz" % stem,
        "%s.spl" % stem,
    )
    for pattern in patterns:
        for path in sorted(apps_dir.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True):
            if path not in candidates:
                candidates.append(path)
    return candidates


def _local_source(
    apps_dir: Path,
    name: str,
    version: str,
    kind: str,
    app_id: Optional[int] = None,
) -> Path:
    folder = apps_dir / name
    if folder.is_dir():
        return folder
    archives = _archive_candidates(apps_dir, name, version)
    if archives:
        return archives[0]
    if app_id is None:
        raise AppsError(
            "Local custom app %s not found in apps_dir %s; place its folder or archive there first"
            % (name, apps_dir)
        )
    extract = " --extract" if kind in {"ta", "es_not_premium"} else ""
    raise AppsError(
        "Local app %s not found in apps_dir %s; run spa apps download %s%s --yes first"
        % (name, apps_dir, app_id, extract)
    )


def _extract_archive(
    archive: Path, apps_dir: Path, name: str, *, overwrite: bool = False
) -> Path:
    """Extract one folder-backed Splunk app without allowing tar path traversal."""
    extracted = apps_dir / name
    if extracted.exists() and not overwrite:
        raise AppsError(
            "Refusing to extract over existing app folder: %s (pass --overwrite)"
            % extracted
        )
    staging = Path(tempfile.mkdtemp(prefix=".spa-extract-", dir=str(apps_dir)))
    try:
        with tarfile.open(str(archive), mode="r:*") as bundle:
            members = bundle.getmembers()
            for member in members:
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise AppsError("Refusing unsafe archive path: %s" % member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise AppsError("Refusing unsafe archive member: %s" % member.name)
            bundle.extractall(str(staging))
        matches = [path for path in staging.rglob(name) if path.is_dir()]
        if len(matches) != 1:
            raise AppsError(
                "Downloaded archive does not contain exactly one %s folder" % name
            )
        if extracted.exists():
            if extracted.is_dir():
                shutil.rmtree(str(extracted))
            else:
                extracted.unlink()
        shutil.move(str(matches[0]), str(extracted))
        return extracted
    except (tarfile.TarError, OSError) as exc:
        if isinstance(exc, AppsError):
            raise
        raise AppsError("Could not extract downloaded archive: %s" % exc) from exc
    finally:
        shutil.rmtree(str(staging), ignore_errors=True)


def download(
    app_id_raw: Any,
    dest_dir: Path,
    *,
    version: str = "latest",
    extract: bool = False,
    overwrite: bool = False,
    config: Optional[Mapping[str, Any]] = None,
    client=None,
) -> Dict[str, Any]:
    app_id = parse_app_id(app_id_raw)
    _refuse_ite_work(app_id)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if overwrite and not extract:
        raise AppsError("--overwrite requires --extract")
    app = get_app(app_id, client=client)
    kind = classify_kind(app_id, app)
    resolved = latest_version(app) if (not version or version == "latest") else version
    url = release_download_url(app, version or "latest")
    name = _entry_name(kind, app, app_id)
    filename = _safe_filename(name, resolved or "latest")
    dest = dest_dir / filename
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or "splunkbase.splunk.com" not in (parsed.netloc or ""):
        raise AppsError("Refusing download URL host")
    if extract and kind not in {"ta", "es_not_premium"}:
        raise AppsError(
            "--extract is only supported for folder-backed apps; keep %s as an archive"
            % kind
        )
    download_release(url, dest, client=client, config=config)
    data = {
        "kind": kind,
        "title": _one_line(app.get("title")),
        "name": name,
        "app_id": app_id,
        "version": resolved or version or "latest",
        "path": str(dest),
    }
    if extract:
        extracted = _extract_archive(dest, dest_dir, name, overwrite=overwrite)
        dest.unlink(missing_ok=True)
        data["extracted_path"] = str(extracted)
        data["path"] = str(extracted)
        data["archive_removed"] = True
    return data
