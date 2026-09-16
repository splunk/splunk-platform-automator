"""Curated ansible/apps_playbooks/ metadata (# spa-app:).

Used by spa apps snippet/search and spa run splunk_apps_playbook_run --help.
Never logs extra_vars values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

SCHEMA = 1
HOOKS = ("run_playbook", "run_playbook_after_restart")
RELATED_DIR = "apps_playbooks"


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
    app_id = data.get("app_id")
    if app_id is not None:
        try:
            out["app_id"] = int(app_id)
        except (TypeError, ValueError):
            return None
        if out["app_id"] < 1:
            return None
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
