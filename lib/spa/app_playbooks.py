"""Curated ansible/apps_playbooks/ metadata (# spa-app:).

Used by spa apps snippet/search and spa run splunk_apps_playbook_run --help.
Never logs extra_vars values.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

SCHEMA = 1
HOOKS = ("run_playbook", "run_playbook_after_restart")
RELATED_DIR = "apps_playbooks"
# Closed set; keep in lockstep with schema.CONTENT_PACK_API_TYPES.
CONTENT_PACK_API_TYPES = {
    "install_all": bool,
    "saved_search_action": str,
    "backfill": bool,
    "resolution": str,
    "enabled": bool,
    "prefix": str,
}
CONTENT_PACK_ITEM_KEY_ORDER = (
    "name",
    "content_pack_install",
    "content_pack_api",
    "customizations",
)
CONTENT_PACK_API_KEY_ORDER = (
    "install_all",
    "enabled",
    "saved_search_action",
    "backfill",
    "resolution",
    "prefix",
)


class AppPlaybookError(ValueError):
    """Operator-facing catalog error (no secrets)."""


def _comment_block_yaml(text: str, key: str) -> Optional[str]:
    lines = text.splitlines()
    index = 0
    if lines and lines[0].strip() == "---":
        index = 1
    body: List[str] = []
    in_block = False
    marker = "%s:" % key
    for line in lines[index:]:
        if line.strip() == "":
            if in_block:
                body.append("")
            continue
        if not line.lstrip().startswith("#"):
            break
        rest = line.lstrip()[1:]
        if rest.startswith(" "):
            rest = rest[1:]
        if not in_block:
            if rest.strip().startswith(marker):
                in_block = True
                body.append("%s:" % key)
                after = rest.split(marker, 1)[1]
                if after.strip():
                    body.append(after)
            continue
        if rest.startswith(" ") or rest.startswith("\t") or rest.strip() == "":
            body.append(rest)
            continue
        break
    if not in_block:
        return None
    return "\n".join(body)


def _parse_extra_vars(raw: Any, path: Path) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AppPlaybookError("%s: spa-app.extra_vars must be a list" % path)
    out: List[Dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise AppPlaybookError(
                "%s: spa-app.extra_vars[%s] must have a name" % (path, index)
            )
        row: Dict[str, Any] = {"name": str(item["name"]).strip()}
        if item.get("required") not in (None, True, False):
            raise AppPlaybookError(
                "%s: spa-app.extra_vars[%s].required must be a boolean" % (path, index)
            )
        row["required"] = bool(item.get("required"))
        if item.get("secret") not in (None, True, False):
            raise AppPlaybookError(
                "%s: spa-app.extra_vars[%s].secret must be a boolean" % (path, index)
            )
        if item.get("secret"):
            row["secret"] = True
        env_name = str(item.get("env") or "").strip()
        if env_name:
            row["env"] = env_name
        if item.get("secret") and not env_name:
            raise AppPlaybookError(
                "%s: spa-app.extra_vars[%s] secret vars need env" % (path, index)
            )
        if "default" in item and item["default"] is not None:
            row["default"] = item["default"]
        out.append(row)
    return out


def _parse_content_pack_api(raw: Any, path: Path) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise AppPlaybookError("%s: spa-app.content_pack_api must be a mapping" % path)
    unknown = sorted(str(key) for key in raw if key not in CONTENT_PACK_API_TYPES)
    if unknown:
        raise AppPlaybookError(
            "%s: spa-app.content_pack_api does not allow %s. Allowed keys: %s"
            % (path, unknown, list(CONTENT_PACK_API_TYPES))
        )
    parsed: Dict[str, Any] = {}
    for key, value in raw.items():
        expected = CONTENT_PACK_API_TYPES[key]
        if not isinstance(value, expected):
            raise AppPlaybookError(
                "%s: spa-app.content_pack_api.%s must be a %s, got %s"
                % (path, key, expected.__name__, type(value).__name__)
            )
        parsed[key] = value
    return parsed


def _comment_list(text: str, label: str) -> List[str]:
    pattern = re.compile(r"^\s*#\s*%s:\s*(.*?)\s*$" % re.escape(label), re.I | re.M)
    match = pattern.search(text)
    if not match:
        return []
    return [
        item.strip()
        for item in re.split(r"\s*,\s*", match.group(1))
        if item.strip()
    ]


def parse_app_playbook_metadata(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    block = _comment_block_yaml(text, "spa-app")
    if block is None:
        return None
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict) or not isinstance(loaded.get("spa-app"), dict):
        return None
    data = loaded["spa-app"]
    if data.get("schema") != SCHEMA:
        return None
    name = str(data.get("name") or "").strip()
    kind = str(data.get("kind") or "").strip()
    hook = str(data.get("hook") or "").strip()
    summary = str(data.get("summary") or "").strip()
    from spa.apps import SEARCH_KINDS

    if not name or kind not in SEARCH_KINDS or hook not in HOOKS or not summary:
        return None
    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "name": name,
        "kind": kind,
        "hook": hook,
        "summary": summary,
        "stem": path.stem,
        "file": path.name,
        "path": "ansible/apps_playbooks/%s" % path.name,
        "relpath": "apps_playbooks/%s" % path.name,
        "extra_vars": _parse_extra_vars(data.get("extra_vars"), path),
    }
    prerequisites = _comment_list(text, "Prerequisites")
    if prerequisites:
        out["prerequisites"] = prerequisites
    app_id = data.get("app_id")
    if app_id is not None:
        try:
            out["app_id"] = int(app_id)
        except (TypeError, ValueError):
            return None
        if out["app_id"] < 1:
            return None
    api = _parse_content_pack_api(data.get("content_pack_api"), path)
    if api:
        out["content_pack_api"] = api
    return out


def list_app_playbooks(spa_home: Path) -> List[Dict[str, Any]]:
    folder = Path(spa_home) / "ansible" / RELATED_DIR
    if not folder.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(folder.glob("*.yml")):
        try:
            meta = parse_app_playbook_metadata(path)
        except AppPlaybookError:
            continue
        if meta:
            rows.append(meta)
    return rows


def match_app_playbooks(
    spa_home: Path,
    *,
    kind: str,
    name: str,
    app_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for row in list_app_playbooks(spa_home):
        if row["kind"] != kind:
            continue
        if row["name"] == name or (
            app_id is not None and row.get("app_id") == app_id
        ):
            found.append(row)
    return found


def has_app_playbook(
    spa_home: Path,
    *,
    kind: str,
    name: Optional[str] = None,
    app_id: Optional[int] = None,
) -> bool:
    folder = name or ""
    return bool(
        match_app_playbooks(spa_home, kind=kind, name=folder, app_id=app_id)
    )


def _safe_under(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _task_file(path: Path) -> Optional[Path]:
    for suffix in (".yml", ".yaml"):
        probe = path if path.suffix in {".yml", ".yaml"} else path.with_suffix(suffix)
        if probe.is_file():
            return probe
    if path.is_file():
        return path
    return None


def resolve_apps_playbook(
    spa_home: Path,
    stem: str,
    spa_env_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    raw = str(stem or "").strip()
    if not raw:
        raise AppPlaybookError("spa run --apps-playbook needs a playbook stem")
    as_path = Path(raw)
    if as_path.is_absolute():
        raise AppPlaybookError("spa run --apps-playbook must be a relative path")
    if ".." in as_path.parts:
        raise AppPlaybookError("Path escape is not allowed: %s" % raw)

    posix = raw.replace("\\", "/")
    if "/" not in posix:
        wanted = as_path.name
        if wanted.endswith(".yml") or wanted.endswith(".yaml"):
            wanted = Path(wanted).stem
        for row in list_app_playbooks(spa_home):
            if row["stem"] == wanted:
                return row
        raise AppPlaybookError(
            "Unknown apps playbook %r (spa run splunk_apps_playbook_run --help)" % wanted
        )

    home = Path(spa_home)
    env = Path(spa_env_dir) if spa_env_dir else None
    probes = []
    if env is not None:
        probes.append(env / as_path)
    probes.append(home / "ansible" / as_path)
    probes.append(home / as_path)
    found = None
    for probe in probes:
        hit = _task_file(probe)
        if hit is None:
            continue
        allowed = _safe_under(home, hit) or (env is not None and _safe_under(env, hit))
        if allowed:
            found = hit
            break
    if found is None:
        raise AppPlaybookError(
            "Unknown apps playbook %r (spa run splunk_apps_playbook_run --help)" % raw
        )

    curated_dir = (home / "ansible" / RELATED_DIR).resolve()
    meta = parse_app_playbook_metadata(found)
    if meta and found.resolve().parent == curated_dir:
        return meta
    abs_path = str(found.resolve())
    return {
        "name": str((meta or {}).get("name") or found.stem),
        "stem": found.stem,
        "file": found.name,
        "path": abs_path,
        "relpath": abs_path,
        "extra_vars": list((meta or {}).get("extra_vars") or []),
    }


def compact_playbooks(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for row in rows:
        item: Dict[str, Any] = {
            "path": row["path"],
            "hook": row["hook"],
            "kind": row["kind"],
            "summary": row["summary"],
        }
        extra = []
        for var in row.get("extra_vars") or []:
            extra.append({"name": var["name"], "required": bool(var.get("required"))})
        if extra:
            item["extra_vars"] = extra
        compact.append(item)
    return compact


def extra_var_snippet_value(var: Dict[str, Any]) -> str:
    if var.get("secret"):
        return '"{{ lookup(\'env\', \'%s\') }}"' % var["env"]
    if "default" in var:
        value = var["default"]
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        text = str(value)
        if ":" in text or " " in text:
            return json.dumps(text)
        return text
    return "<%s>" % var["name"]


def customization_yaml_lines(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """YAML lines (2-space indent) for customizations on one apps[] item."""
    if not rows:
        return []
    by_hook: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_hook.setdefault(row["hook"], []).append(row)
    lines = ["  customizations:"]
    extras: List[Dict[str, Any]] = []
    for hook in HOOKS:
        matches = by_hook.get(hook) or []
        if not matches:
            continue
        chosen = matches[0]
        lines.append("    %s: %s" % (hook, chosen["path"]))
        extras.extend(chosen.get("extra_vars") or [])
        if len(matches) > 1:
            others = ", ".join(item["file"] for item in matches[1:])
            lines.append("    # Also: %s (pick one %s)" % (others, hook))
    if extras:
        lines.append("    extra_vars:")
        for var in extras:
            lines.append("      %s: %s" % (var["name"], extra_var_snippet_value(var)))
    return lines


def advertise_notes(rows: Sequence[Dict[str, Any]]) -> List[str]:
    notes = []
    for row in rows:
        notes.append("Curated playbook: %s (pass --customize)" % row["summary"])
    return notes


def _api_note_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _curated_playbook_path(spa_home: Path, raw: Any) -> Optional[Path]:
    text = str(raw or "").strip()
    if not text:
        return None
    as_path = Path(text)
    home = Path(spa_home)
    curated = (home / "ansible" / RELATED_DIR).resolve()
    probes = []
    if as_path.is_absolute():
        probes.append(as_path)
    else:
        probes.append(home / as_path)
        probes.append(home / "ansible" / as_path)
        probes.append(curated / as_path.name)
    for probe in probes:
        try:
            resolved = probe.resolve()
            resolved.relative_to(curated)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _pack_targets(config: Mapping[str, Any]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    apps = ((config.get("splunk_app_deployment") or {}) or {}).get("apps") or []
    if not isinstance(apps, list):
        return
    for index, app in enumerate(apps):
        if not isinstance(app, Mapping):
            continue
        packs = app.get("content_pack_apps")
        if isinstance(packs, list):
            for item_index, item in enumerate(packs):
                if isinstance(item, Mapping):
                    yield (
                        "splunk_app_deployment.apps[%s].content_pack_apps[%s]"
                        % (index, item_index),
                        item,
                    )
            continue
        if app.get("itsi_content_pack"):
            yield "splunk_app_deployment.apps[%s]" % index, app


def content_pack_header_errors(
    config: Mapping[str, Any], spa_home: Path
) -> List[str]:
    """Require configure-playbook header keys present and equal; skip env-local files."""
    errors: List[str] = []
    for loc, target in _pack_targets(config):
        customizations = target.get("customizations")
        if not isinstance(customizations, Mapping):
            continue
        playbook = customizations.get("run_playbook_after_restart")
        path = _curated_playbook_path(spa_home, playbook)
        if path is None:
            continue
        try:
            meta = parse_app_playbook_metadata(path)
        except AppPlaybookError as exc:
            errors.append(str(exc))
            continue
        if not meta:
            continue
        if target.get("content_pack_install") is False:
            errors.append(
                "%s: %s requires content_pack_install not false"
                % (loc, path.name)
            )
        header = meta.get("content_pack_api")
        if not isinstance(header, dict) or not header:
            continue
        api = target.get("content_pack_api")
        if not isinstance(api, dict):
            api = {}
        for key, value in header.items():
            if key not in api:
                errors.append(
                    "%s: %s requires content_pack_api.%s=%s"
                    % (loc, path.name, key, _api_note_value(value))
                )
            elif api[key] != value:
                errors.append(
                    "%s: %s requires content_pack_api.%s=%s, got %s"
                    % (
                        loc,
                        path.name,
                        key,
                        _api_note_value(value),
                        _api_note_value(api[key]),
                    )
                )
    return errors


def _order_mapping(mapping: Dict[str, Any], ordered_keys: Sequence[str]) -> None:
    extras = [key for key in list(mapping) if key not in ordered_keys]
    if hasattr(mapping, "move_to_end"):
        for key in reversed(list(ordered_keys)):
            if key in mapping:
                mapping.move_to_end(key, last=False)
        for key in extras:
            mapping.move_to_end(key, last=True)
        return
    rebuilt = type(mapping)()
    for key in ordered_keys:
        if key in mapping:
            rebuilt[key] = mapping[key]
    for key in extras:
        rebuilt[key] = mapping[key]
    mapping.clear()
    mapping.update(rebuilt)


def order_content_pack_item(item: Dict[str, Any]) -> None:
    """Write pack-item keys as name, content_pack_install, content_pack_api, customizations."""
    api = item.get("content_pack_api")
    if isinstance(api, dict):
        _order_mapping(api, CONTENT_PACK_API_KEY_ORDER)
    _order_mapping(item, CONTENT_PACK_ITEM_KEY_ORDER)


def apply_content_pack_api(
    target: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    *,
    write_install: bool = True,
) -> List[str]:
    """Copy spa-app.content_pack_api onto a pack item or single-app entry.

    Any declared header key is written. Explicit false is kept. When the header
    sets at least one API key, also write content_pack_install true (unless
    write_install is false) and install_all true if the header omitted it.
    """
    notes: List[str] = []
    for row in rows:
        api = row.get("content_pack_api")
        if not isinstance(api, dict) or not api:
            continue
        if write_install:
            target["content_pack_install"] = True
        dest = target.get("content_pack_api")
        if not isinstance(dest, dict):
            dest = {}
        for key, value in api.items():
            dest[key] = value
        if "install_all" not in dest:
            dest["install_all"] = True
        _order_mapping(dest, CONTENT_PACK_API_KEY_ORDER)
        target["content_pack_api"] = dest
        parts = [
            "%s=%s" % (key, _api_note_value(api[key])) for key in api
        ]
        notes.append(
            "Playbook %s set content_pack_api.%s."
            % (row.get("file") or Path(str(row.get("path") or "")).name, ", ".join(parts))
        )
    return notes


def run_extra_vars(row: Dict[str, Any]) -> List[str]:
    """ansible-playbook -e fragments for apps_playbook and app_name."""
    return [
        "-e",
        "apps_playbook=%s" % row["relpath"],
        "-e",
        "app_name=%s" % row["name"],
    ]


def format_related_help(rows: Sequence[Dict[str, Any]]) -> List[str]:
    if not rows:
        return []
    lines = ["Curated apps playbooks (ansible/apps_playbooks/):"]
    for row in rows:
        extra = ", ".join(
            ("%s%s" % (var["name"], "*" if var.get("required") else ""))
            for var in (row.get("extra_vars") or [])
        )
        suffix = " extra_vars: %s" % extra if extra else ""
        lines.append(
            "  %s  %s  %s  %s%s"
            % (row["stem"], row["kind"], row["name"], row["hook"], suffix)
        )
        lines.append("    %s" % row["summary"])
        lines.append(
            "    spa run splunk_apps_playbook_run --apps-playbook %s --hosts ROLE --yes"
            % row["stem"]
        )
    lines.append(
        "Custom env-dir task files are not listed. Example: --apps-playbook ancustom/my_custom_playbook"
    )
    return lines
