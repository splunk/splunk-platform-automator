"""spa apps discovery, entry construction, archive inspection, and download."""

from __future__ import annotations

import configparser
import io
import re
import shutil
import tarfile
import tempfile
import unicodedata
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
CONTENT_PACK_LIMIT = 100
MAX_ARCHIVE_MEMBERS = 10000
MAX_APP_CONF_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 8 * 1024 * 1024 * 1024
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
    lines = ["- name: %s" % name]
    if source != "splunkbase":
        lines.append("  source: %s" % source)
    if source == "splunkbase":
        lines.append("  app_id: %s" % app_id)
        if version and version != "latest":
            lines.append("  version: %s" % version)
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
    customization_lines: Sequence[str] = (),
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
        body = ["- name: %s" % name]
        if source != "splunkbase":
            body.append("  source: %s" % source)
        if source == "splunkbase":
            body += ["  app_id: %s" % app_id, "  premium_app: itsi"]
        else:
            if path:
                body.append("  path: %s" % path)
            body.append("  premium_app: itsi")
    elif kind == "itsi_content_library":
        extra.insert(0, "Requires a sibling premium_app: itsi (app_id 1841). Fill content_pack_apps.")
        body = ["- name: %s" % name]
        if source != "splunkbase":
            body.append("  source: %s" % source)
        if source == "splunkbase":
            body.append("  app_id: %s" % app_id)
        elif path:
            body.append("  path: %s" % path)
        body += ["  itsi_content_pack: true", "  content_pack_apps: []"]
    elif kind == "itsi_content_pack_single":
        extra.insert(0, "Requires a sibling premium_app: itsi (app_id 1841).")
        body = ["- name: %s" % name]
        if source != "splunkbase":
            body.append("  source: %s" % source)
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
    body = list(body) + [str(line) for line in customization_lines if str(line).strip()]
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
        if row.get("playbook"):
            first = "%s | playbook" % first
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
    spa_home: Optional[Path] = None,
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
    hits = hits[:limit]
    if spa_home is not None:
        from spa.app_playbooks import has_app_playbook

        for row in hits:
            if has_app_playbook(
                spa_home,
                kind=str(row.get("kind") or ""),
                name=str(row.get("name") or ""),
                app_id=row.get("app_id"),
            ):
                row["playbook"] = True
    return {"query": query, "apps": hits}


def _refuse_ite_work(app_id: int) -> None:
    if app_id == ITE_WORK_ID:
        raise AppsError(ITE_WORK_ERROR)


def build_entry(
    app_id_raw: Any,
    *,
    version: str = "latest",
    roles: Optional[Sequence[str]] = None,
    source: str = "splunkbase",
    apps_dir: Optional[Path] = None,
    spa_home: Optional[Path] = None,
    customize: bool = False,
    content_packs: Optional[Sequence[str]] = None,
    install_all_content_packs: bool = False,
    explicit_default: bool = False,
    set_values: Optional[Sequence[Sequence[Any]]] = None,
    for_add: bool = True,
    client=None,
) -> Dict[str, Any]:
    """Build one structured apps[] entry; rendering and config writes share it."""
    if source not in {"splunkbase", "local"}:
        raise AppsError("--source must be one of: splunkbase, local")
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

    normal = kind in {"ta", "es_not_premium"}
    if roles and not normal:
        raise AppsError("--roles is not valid for ITSI or content packs")
    if for_add and normal and not roles:
        raise AppsError("--roles is required for normal apps")
    if content_packs and install_all_content_packs:
        raise AppsError("--content-pack and --install-all-content-packs are mutually exclusive")
    if kind != "itsi_content_library" and (content_packs or install_all_content_packs):
        raise AppsError("Content-pack policy flags are only valid for app 5391")
    if for_add and kind == "itsi_content_library" and not (
        content_packs or install_all_content_packs
    ):
        raise AppsError(
            "spa apps add 5391 requires --install-all-content-packs or --content-pack NAME"
        )

    resolved = latest_version(app) if (not version or version == "latest") else version
    name = str(custom_name) if is_custom else _entry_name(kind, app, int(app_id))
    local_path: Optional[str] = None
    notes: List[str] = []
    if source == "local":
        if apps_dir is None:
            raise AppsError("--source local requires an environment with apps_dir")
        found = _local_source(Path(apps_dir), name, resolved or version or "latest", kind, app_id)
        local_path = found.name
        if found.is_file() and normal:
            hint = (
                "spa apps download %s --extract --yes" % app_id
                if app_id is not None
                else "unpack it in apps_dir"
            )
            notes.append("Archive found; normal apps deploy from a folder — %s." % hint)

    entry: Dict[str, Any] = {"name": name}
    if source == "local":
        entry["source"] = "local"
        if local_path:
            entry["path"] = local_path
    else:
        entry["app_id"] = int(app_id)
        if explicit_default:
            entry["source"] = "splunkbase"
    if version and version != "latest":
        entry["version"] = version
    elif explicit_default:
        entry["version"] = "latest"

    if kind == "premium_itsi":
        entry["premium_app"] = "itsi"
    elif kind == "itsi_content_library":
        entry["itsi_content_pack"] = True
        if install_all_content_packs:
            entry["content_pack_api"] = {"install_all_apps": True}
        else:
            entry["content_pack_apps"] = [
                {"name": str(pack)} for pack in (content_packs or [])
            ]
    elif kind == "itsi_content_pack_single":
        entry["itsi_content_pack"] = True
        entry["content_pack_api"] = {"install_all": True, "enabled": True}
    else:
        entry["target_roles"] = list(roles or [])

    dedicated = {"name", "app_id", "premium_app", "source", "version"}
    if roles:
        dedicated.add("target_roles")
    omitted_defaults: List[Dict[str, Any]] = []
    for assignment in set_values or []:
        if len(assignment) != 2:
            raise AppsError("--set needs FIELD VALUE")
        field, value = str(assignment[0]), assignment[1]
        if field in {"name", "app_id", "premium_app"}:
            raise AppsError("--set cannot set %s; app classification owns it" % field)
        if field in dedicated:
            raise AppsError("--set %s duplicates a dedicated flag" % field)
        try:
            from spa.config_edit import ConfigEditError, _parse_value

            selector = (
                "app_id=%s" % app_id
                if app_id is not None
                else "name=%s" % name
            )
            value = _parse_value(
                "splunk_app_deployment.apps[%s].%s" % (selector, field),
                str(value),
            )
        except ConfigEditError as exc:
            raise AppsError(str(exc)) from exc
        from spa.catalog import app_entry_field_detail

        detail = app_entry_field_detail(field) or {}
        if (
            not explicit_default
            and "default" in detail
            and value == detail["default"]
        ):
            omitted_defaults.append({"path": field, "value": value})
            continue
        current = entry
        parts = field.split(".")
        for part in parts[:-1]:
            child = current.get(part)
            if child is None:
                child = {}
                current[part] = child
            if not isinstance(child, dict):
                raise AppsError("--set %s has a non-mapping parent" % field)
            current = child
        current[parts[-1]] = value

    related = []
    customization_lines: List[str] = []
    if spa_home is not None:
        from spa.app_playbooks import (
            advertise_notes,
            compact_playbooks,
            customization_yaml_lines,
            match_app_playbooks,
        )

        related = match_app_playbooks(spa_home, kind=kind, name=name, app_id=app_id)
        if related and customize:
            customization_lines = customization_yaml_lines(related)
            if customization_lines:
                import yaml

                rendered = "- name: placeholder\n%s\n" % "\n".join(
                    customization_lines
                )
                customization = yaml.safe_load(rendered)[0].get("customizations")
                if customization is not None:
                    entry["customizations"] = customization
        elif related:
            notes.extend(advertise_notes(related))

    data: Dict[str, Any] = {
        "kind": kind,
        "title": _one_line(app.get("title")),
        "name": name,
        "source": source,
        "version": resolved or version or "latest",
        "entry": entry,
        "_app": app,
        "_notes": notes,
        "_customization_lines": customization_lines,
        "omitted_defaults": omitted_defaults,
    }
    if app_id is not None:
        data["app_id"] = app_id
    if local_path:
        data["path"] = local_path
    if related:
        data["playbooks"] = compact_playbooks(related)
    return data


def snippet(
    app_id_raw: Any,
    *,
    version: str = "latest",
    roles: Optional[Sequence[str]] = None,
    source: str = "splunkbase",
    apps_dir: Optional[Path] = None,
    spa_home: Optional[Path] = None,
    customize: bool = False,
    set_values: Optional[Sequence[Sequence[Any]]] = None,
    client=None,
) -> Dict[str, Any]:
    built = build_entry(
        app_id_raw,
        version=version,
        roles=roles,
        source=source,
        apps_dir=apps_dir,
        spa_home=spa_home,
        customize=customize,
        set_values=set_values,
        for_add=False,
        client=client,
    )
    app = built.pop("_app")
    notes = built.pop("_notes")
    customization_lines = built.pop("_customization_lines")
    kind = built["kind"]
    app_id = built.get("app_id")
    name = built["name"]
    local_path = built.get("path")
    yaml_text = format_snippet_yaml(
        app,
        app_id=int(app_id or 0),
        kind=kind,
        version=version or "latest",
        roles=roles,
        source=source,
        path=local_path,
        roles_ignored=False,
        notes=notes,
        customization_lines=customization_lines,
    )
    if set_values:
        from ruamel.yaml import YAML

        rendered = io.StringIO()
        yaml = YAML()
        yaml.default_flow_style = False
        assigned_roots = {str(pair[0]).split(".", 1)[0] for pair in set_values}
        yaml.dump(
            {
                key: value
                for key, value in built["entry"].items()
                if key in assigned_roots
            },
            rendered,
        )
        yaml_text += "".join(
            "  %s\n" % line if line else "\n"
            for line in rendered.getvalue().splitlines()
        )
    built["snippet"] = yaml_text
    return built


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


def _humanize_content_pack(name: str) -> str:
    suffix = re.sub(r"^DA-ITSI-CP-", "", name, flags=re.I)
    words = re.sub(r"[-_]+", " ", suffix).strip()
    return words.title() if words else name


def _safe_archive_text(value: Any, *, limit: int = 500) -> str:
    text = "".join(
        character
        if not unicodedata.category(character).startswith("C")
        else " "
        for character in str(value or "")
    )
    return _WS.sub(" ", text).strip()[:limit]


def _app_conf_value(
    parser: configparser.ConfigParser, section: str, option: str
) -> str:
    if not parser.has_section(section):
        return ""
    return _safe_archive_text(parser.get(section, option, fallback=""))


def _parse_app_conf(raw: bytes) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(raw.decode("utf-8-sig", errors="replace"))
    except configparser.Error:
        return configparser.ConfigParser(interpolation=None)
    return parser


def _content_pack_automation(
    spa_home: Optional[Path], name: str
) -> Optional[Dict[str, Any]]:
    if spa_home is None:
        return None
    from spa.app_playbooks import match_app_playbooks

    matches = match_app_playbooks(
        Path(spa_home),
        kind="itsi_content_pack_single",
        name=name,
    )
    if not matches:
        return None
    row = matches[0]
    automation = {
        "hook": row.get("hook"),
        "summary": row.get("summary"),
        "path": row.get("path"),
    }
    if row.get("prerequisites"):
        automation["prerequisites"] = row["prerequisites"]
    return {
        key: value
        for key, value in automation.items()
        if value not in (None, "", [], {})
    }


def inspect_content_pack_archive(
    archive: Path,
    *,
    spa_home: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List 5391 content packs without extracting untrusted archive members."""
    archive = Path(archive)
    if not archive.is_file():
        raise AppsError("Content Library archive not found: %s" % archive)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise AppsError(
            "Content Library archive exceeds %s bytes" % MAX_ARCHIVE_BYTES
        )
    found: Dict[str, Dict[str, Any]] = {}
    expanded_bytes = 0
    try:
        with tarfile.open(str(archive), mode="r:*") as bundle:
            for index, member in enumerate(bundle):
                if index >= MAX_ARCHIVE_MEMBERS:
                    raise AppsError(
                        "Content Library archive has more than %s members"
                        % MAX_ARCHIVE_MEMBERS
                    )
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise AppsError("Refusing unsafe archive path: %s" % member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise AppsError("Refusing unsafe archive member: %s" % member.name)
                expanded_bytes += max(int(member.size or 0), 0)
                if expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
                    raise AppsError(
                        "Content Library archive expands beyond %s bytes"
                        % MAX_ARCHIVE_EXPANDED_BYTES
                    )
                parts = member_path.parts
                if (
                    len(parts) != 3
                    or parts[-2:] != ("default", "app.conf")
                    or not parts[-3].startswith("DA-ITSI-CP-")
                ):
                    continue
                name = parts[-3]
                if not _FOLDER.fullmatch(name):
                    raise AppsError(
                        "Refusing invalid content pack folder: %s" % name
                    )
                if name in found:
                    raise AppsError(
                        "Content Library archive contains duplicate pack folder: %s"
                        % name
                    )
                if member.size > MAX_APP_CONF_BYTES:
                    raise AppsError(
                        "Content pack app.conf exceeds %s bytes: %s"
                        % (MAX_APP_CONF_BYTES, member.name)
                    )
                stream = bundle.extractfile(member)
                if stream is None:
                    continue
                raw = stream.read(MAX_APP_CONF_BYTES + 1)
                if len(raw) > MAX_APP_CONF_BYTES:
                    raise AppsError(
                        "Content pack app.conf exceeds %s bytes: %s"
                        % (MAX_APP_CONF_BYTES, member.name)
                    )
                parser = _parse_app_conf(raw)
                title = _app_conf_value(parser, "ui", "label")
                summary = _app_conf_value(parser, "launcher", "description")
                version = (
                    _app_conf_value(parser, "launcher", "version")
                    or _app_conf_value(parser, "id", "version")
                    or _app_conf_value(parser, "package", "version")
                )
                row: Dict[str, Any] = {
                    "name": name,
                    "title": title or _humanize_content_pack(name),
                    "command": "spa apps add 5391 --content-pack %s --yes" % name,
                }
                if summary:
                    row["summary"] = _one_line(summary)
                if version:
                    row["version"] = version
                automation = _content_pack_automation(spa_home, name)
                if automation:
                    row["spa_automation"] = automation
                found[name] = row
    except AppsError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise AppsError("Could not inspect Content Library archive: %s" % exc) from exc
    return [found[name] for name in sorted(found)]


def _content_library_archive_version(archive: Path) -> str:
    try:
        with tarfile.open(str(archive), mode="r:*") as bundle:
            for member in bundle:
                parts = Path(member.name).parts
                if (
                    len(parts) == 3
                    and parts[0] == "DA-ITSI-ContentLibrary"
                    and parts[1:] == ("default", "app.conf")
                    and 0 <= member.size <= MAX_APP_CONF_BYTES
                ):
                    stream = bundle.extractfile(member)
                    if stream is None:
                        return ""
                    parser = _parse_app_conf(stream.read(MAX_APP_CONF_BYTES + 1))
                    return (
                        _app_conf_value(parser, "launcher", "version")
                        or _app_conf_value(parser, "id", "version")
                        or _app_conf_value(parser, "package", "version")
                    )
    except (tarfile.TarError, OSError):
        return ""
    return ""


def _local_content_library_archive(
    apps_dir: Path, version: str
) -> Optional[Path]:
    name = "DA-ITSI-ContentLibrary"
    candidates = _archive_candidates(apps_dir, name, version)
    if version == "latest":
        return (
            max(candidates, key=lambda item: item.stat().st_mtime)
            if candidates
            else None
        )
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "app"
    wanted = "%s_%s" % (
        stem,
        re.sub(r"[^A-Za-z0-9._-]+", "_", version).strip("._"),
    )
    for candidate in candidates:
        if candidate.name in {
            wanted + ".tgz",
            wanted + ".tar.gz",
            wanted + ".spl",
        }:
            return candidate
    return None


def _trusted_download_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() == "splunkbase.splunk.com"
    )


def content_pack_catalog(
    app_id_raw: Any = CONTENT_LIBRARY_ID,
    *,
    version: str = "latest",
    archive: Optional[Path] = None,
    apps_dir: Optional[Path] = None,
    spa_home: Optional[Path] = None,
    config: Optional[Mapping[str, Any]] = None,
    client=None,
) -> Dict[str, Any]:
    """Discover packs from an explicit, local, or temporary 5391 archive."""
    app_id = parse_app_id(app_id_raw)
    if app_id != CONTENT_LIBRARY_ID:
        raise AppsError(
            "spa apps content-packs list supports Content Library app_id 5391"
        )
    resolved = version or "latest"
    selected: Optional[Path] = Path(archive) if archive is not None else None
    source = "archive"
    temporary: Optional[tempfile.TemporaryDirectory] = None
    try:
        if selected is None:
            if apps_dir is not None:
                selected = _local_content_library_archive(
                    Path(apps_dir), resolved
                )
            if selected is not None:
                source = "local_archive"
                if resolved == "latest":
                    resolved = (
                        _content_library_archive_version(selected) or "unknown"
                    )
            else:
                app = get_app(app_id, client=client)
                resolved = latest_version(app) if resolved == "latest" else resolved
                name = _entry_name("itsi_content_library", app, app_id)
                temporary = tempfile.TemporaryDirectory(prefix="spa-content-packs-")
                selected = Path(temporary.name) / _safe_filename(name, resolved)
                url = release_download_url(app, version or "latest")
                if not _trusted_download_url(url):
                    raise AppsError("Refusing download URL host")
                download_release(url, selected, client=client, config=config)
                source = "temporary_download"
        packs = inspect_content_pack_archive(selected, spa_home=spa_home)
        if source in {"archive", "local_archive"}:
            archive_version = _content_library_archive_version(selected)
            if resolved == "latest":
                resolved = archive_version or "unknown"
            elif archive_version and archive_version != resolved:
                raise AppsError(
                    "Requested version %s does not match archive version %s"
                    % (resolved, archive_version)
                )
        if not packs:
            raise AppsError(
                "Content Library archive contains no DA-ITSI-CP-*/default/app.conf entries"
            )
        return {
            "app_id": app_id,
            "version": resolved,
            "source": source,
            "packs": packs[:CONTENT_PACK_LIMIT],
            "total_matches": len(packs),
            "truncated": len(packs) > CONTENT_PACK_LIMIT,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def format_content_pack_catalog(data: Mapping[str, Any]) -> str:
    """Render bounded content-pack rows from the session payload."""
    lines = [
        "Content Library %s (%s) — %s"
        % (
            data.get("app_id") or CONTENT_LIBRARY_ID,
            data.get("version") or "unknown version",
            str(data.get("source") or "archive").replace("_", " "),
        )
    ]
    for row in data.get("packs") or []:
        title = row.get("title") or row.get("name") or ""
        lines.append("")
        lines.append("%s  %s" % (row.get("name") or "", title))
        if row.get("version"):
            lines.append("  version: %s" % row["version"])
        if row.get("summary"):
            lines.append("  %s" % row["summary"])
        automation = row.get("spa_automation") or {}
        if automation:
            lines.append(
                "  SPA automation: %s (%s)"
                % (
                    automation.get("summary") or "available",
                    automation.get("hook") or "configured hook",
                )
            )
            if automation.get("prerequisites"):
                lines.append(
                    "  prerequisites: %s"
                    % ", ".join(str(item) for item in automation["prerequisites"])
                )
        lines.append("  command: %s" % row.get("command"))
    if data.get("truncated"):
        lines.append("")
        lines.append(
            "Showing %s of %s packs."
            % (len(data.get("packs") or []), data.get("total_matches"))
        )
    lines.append("")
    lines.append(
        "All packs: spa apps add 5391 --install-all-content-packs --yes"
    )
    return "\n".join(lines).rstrip() + "\n"


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
    if not _trusted_download_url(url):
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
