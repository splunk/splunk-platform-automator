"""Feature catalog lookup for spa features and spa-create-config."""

from __future__ import annotations

import re
import shutil
import sys
import textwrap
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Set, Tuple, get_args, get_origin

import yaml

from spa.paths import SpaPaths

CATALOG_REL = Path("examples") / "catalog" / "features.yml"
DESCRIPTION_REL = Path("examples") / "configuration_description.yml"

# Keys that playbooks honor but that are not Pydantic fields. Empty when schema covers them.
USED_IN_CODE_KEYS: frozenset[str] = frozenset()


def catalog_path(spa_home: Path) -> Path:
    return spa_home / CATALOG_REL


def load_features(spa_home: Path) -> List[Dict[str, Any]]:
    path = catalog_path(spa_home)
    if not path.is_file():
        raise FileNotFoundError("Feature catalog not found: %s" % path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    features = data.get("features") or []
    if not isinstance(features, list):
        raise ValueError("examples/catalog/features.yml must have a features: list")
    return [item for item in features if isinstance(item, dict) and item.get("id")]


def search_features(features: Iterable[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    needles = [part.lower() for part in query.split() if part.strip()]
    if not needles:
        return list(features)
    found = []
    for item in features:
        blob = " ".join(
            [
                str(item.get("id") or ""),
                str(item.get("title") or ""),
                str(item.get("kind") or ""),
                str(item.get("sva") or ""),
                str(item.get("when_to_use") or ""),
                str(item.get("when_not_to_use") or ""),
                str(item.get("suggest") or ""),
                " ".join(key_path(key) for key in item.get("keys") or []),
            ]
        ).lower()
        if all(needle in blob for needle in needles):
            found.append(item)
    return found


def get_feature(features: Iterable[Dict[str, Any]], ident: str) -> Optional[Dict[str, Any]]:
    ident = ident.strip()
    for item in features:
        if str(item.get("id")) == ident:
            return item
    lowered = ident.lower()
    matches = [item for item in features if lowered in str(item.get("id", "")).lower()]
    if len(matches) == 1:
        return matches[0]
    return None


def catalog_key_set(features: Iterable[Dict[str, Any]]) -> Set[str]:
    keys: Set[str] = set()
    for item in features:
        for key in item.get("keys") or []:
            keys.add(key_path(key))
    return keys


def key_path(key: Any) -> str:
    """Return a key path from a compact string or an annotated catalog entry."""
    if isinstance(key, dict):
        return str(key.get("path") or "")
    return str(key)


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None:
        return annotation
    if "Union" in str(origin):
        non_none = [arg for arg in args if arg is not type(None)]
        return _unwrap_optional(non_none[0]) if len(non_none) == 1 else annotation
    return annotation


def _annotation_parts(
    annotation: Any, field_name: str
) -> Tuple[str, Optional[Any], str]:
    """Return display type, nested model (if any), and its path suffix."""
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {list, List}:
        item = _unwrap_optional(args[0]) if args else Any
        item_name = _type_name(item)
        return "list[%s]" % item_name, item if getattr(item, "model_fields", None) else None, "[]"
    if origin in {dict, Dict}:
        key_type = _unwrap_optional(args[0]) if args else Any
        value_type = _unwrap_optional(args[1]) if len(args) > 1 else Any
        display = "map[%s, %s]" % (_type_name(key_type), _type_name(value_type))
        nested = value_type if getattr(value_type, "model_fields", None) else None
        placeholder = "volume" if field_name.endswith("_volumes") else "name"
        return display, nested, ".<%s>" % placeholder
    return _type_name(annotation), annotation if getattr(annotation, "model_fields", None) else None, ""


def _type_name(annotation: Any) -> str:
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {list, List}:
        return "list[%s]" % (_type_name(args[0]) if args else "any")
    if origin in {dict, Dict}:
        left = _type_name(args[0]) if args else "any"
        right = _type_name(args[1]) if len(args) > 1 else "any"
        return "map[%s, %s]" % (left, right)
    if origin is not None and "Union" in str(origin):
        return " | ".join(_type_name(arg) for arg in args if arg is not type(None))
    if origin is Literal:
        return "enum"
    if annotation is Any:
        return "any"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "enum"
    if getattr(annotation, "model_fields", None):
        return "object"
    return {
        str: "string",
        int: "integer",
        bool: "boolean",
        float: "number",
    }.get(annotation, getattr(annotation, "__name__", str(annotation)))


def _field_constraints(field: Any) -> Dict[str, Any]:
    constraints: Dict[str, Any] = {}
    for metadata in getattr(field, "metadata", ()):
        for name in ("ge", "gt", "le", "lt", "min_length", "max_length", "pattern"):
            value = getattr(metadata, name, None)
            if value is not None:
                constraints[name] = value
    return constraints


def _allowed_values(annotation: Any) -> List[Any]:
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {list, List} and args:
        annotation = _unwrap_optional(args[0])
        origin = get_origin(annotation)
        args = get_args(annotation)
    if origin is Literal:
        return list(args)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [member.value for member in annotation]
    return []


def schema_key_details() -> Dict[str, Dict[str, Any]]:
    """Describe Pydantic fields using list/map-aware catalog paths."""
    plugin = Path(__file__).resolve().parents[2] / "ansible" / "plugins" / "inventory"
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    from schema import SplunkConfig  # type: ignore

    details: Dict[str, Dict[str, Any]] = {}

    def walk(model: Any, prefix: str) -> None:
        fields = getattr(model, "model_fields", None)
        if not fields:
            return
        for name, field in fields.items():
            path = "%s.%s" % (prefix, name) if prefix else name
            type_name, nested, suffix = _annotation_parts(field.annotation, name)
            detail: Dict[str, Any] = {
                "path": path,
                "type": type_name,
                "required": bool(field.is_required()),
            }
            if field.description:
                detail["description"] = field.description
            constraints = _field_constraints(field)
            if constraints:
                detail["constraints"] = constraints
            allowed = _allowed_values(field.annotation)
            if allowed:
                detail["allowed"] = allowed
            if not field.is_required() and field.default is not None:
                detail["default"] = field.default
            details[path] = detail
            if nested:
                walk(nested, path + suffix)

    walk(SplunkConfig, "")
    return details


def schema_key_paths() -> List[str]:
    return list(schema_key_details())


def description_key_paths(spa_home: Path) -> Set[str]:
    path = spa_home / DESCRIPTION_REL
    if not path.is_file():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_keys: Set[str] = set()

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            if prefix:
                raw_keys.add(prefix)
            for name, value in node.items():
                child = "%s.%s" % (prefix, name) if prefix else str(name)
                walk(value, child)
        elif isinstance(node, list) and node and isinstance(node[0], dict):
            if prefix:
                raw_keys.add(prefix)
            walk(node[0], prefix)
        elif prefix:
            raw_keys.add(prefix)

    if isinstance(data, dict):
        walk(data, "")
    keys = set(raw_keys)
    for schema_path in schema_key_paths():
        pattern = re.escape(schema_path.replace("[]", ""))
        pattern = re.sub(r"<[^>]+>", r"[^.]+", pattern)
        if any(re.fullmatch(pattern, raw) for raw in raw_keys):
            keys.add(schema_path)
    return keys


def key_inventory(spa_home: Path) -> Dict[str, Any]:
    features = load_features(spa_home)
    covered = catalog_key_set(features)
    schema_details = schema_key_details()
    schema_keys = list(schema_details)
    described = description_key_paths(spa_home)
    catalog_details = {
        key_path(key): key
        for feature in features
        for key in feature.get("keys") or []
        if isinstance(key, dict)
    }
    rows = []
    all_keys = sorted(set(schema_keys) | described | USED_IN_CODE_KEYS | covered)
    for key in all_keys:
        override = catalog_details.get(key) or {}
        has_detail = key in schema_details or bool(override.get("type"))
        rows.append(
            {
                "key": key,
                "in_schema": key in schema_keys,
                "in_description": key in described,
                "used_in_code": key in USED_IN_CODE_KEYS or key in schema_keys,
                "in_catalog": key in covered,
                "has_key_detail": has_detail,
            }
        )
    missing = [row["key"] for row in rows if row["in_schema"] and not row["in_catalog"]]
    missing_detail = [
        row["key"]
        for row in rows
        if row["in_catalog"] and not row["has_key_detail"]
    ]
    return {
        "keys": rows,
        "missing_from_catalog": missing,
        "missing_key_detail": missing_detail,
        "features": len(features),
    }


def summarize_feature(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return enough decision context without snippets or per-key details."""
    return {
        field: item.get(field)
        for field in (
            "id",
            "title",
            "kind",
            "sva",
            "when_to_use",
            "when_not_to_use",
            "suggest",
        )
        if item.get(field) is not None
    }


def list_payload(spa_home: Path) -> Dict[str, Any]:
    features = load_features(spa_home)
    return {"features": [summarize_feature(item) for item in features]}


def format_feature_rows(features: List[Dict[str, Any]], width: Optional[int] = None) -> str:
    """One record per block: id, title, SVA, then guidance aligned under the title."""
    rows = [item for item in features if item.get("id")]
    if not rows:
        return ""
    id_width = max(len(str(item["id"])) for item in rows)
    indent = " " * (id_width + 2)
    if width is None:
        width = shutil.get_terminal_size(fallback=(100, 24)).columns
    text_width = max(width - len(indent), 40)
    lines: List[str] = []
    for item in rows:
        head = "%s  %s" % (str(item["id"]).ljust(id_width), item.get("title") or "")
        if item.get("sva"):
            head = "%s  [SVA %s]" % (head.rstrip(), item["sva"])
        lines.append(head.rstrip())
        guidance = item.get("when_to_use") or item.get("when_not_to_use")
        if guidance:
            lines.extend(
                indent + line
                for line in textwrap.wrap(str(guidance), width=text_width) or [""]
            )
    return "\n".join(lines)


def feature_key_details(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Merge schema-derived details with catalog-only semantic overrides."""
    schema = schema_key_details()
    result = []
    for key in item.get("keys") or []:
        path = key_path(key)
        detail = dict(schema.get(path) or {"path": path})
        if isinstance(key, dict):
            # Schema owns type/allowed/default; catalog may only add notes.
            detail.update(
                {
                    name: value
                    for name, value in key.items()
                    if name not in {"path", "type", "allowed", "default"}
                }
            )
        result.append(detail)
    return result


def _wrap_prose(label: str, text: str, width: int, indent: str = "") -> List[str]:
    """Wrap a label: prose pair; key lines and snippets stay verbatim."""
    wrapped = textwrap.wrap(
        "%s%s: %s" % (indent, label, text),
        width=width,
        subsequent_indent=indent + "  ",
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or ["%s%s: %s" % (indent, label, text)]


def format_feature_text(
    item: Dict[str, Any],
    key_details: Optional[List[Dict[str, Any]]] = None,
    width: Optional[int] = None,
) -> str:
    if width is None:
        width = shutil.get_terminal_size(fallback=(100, 24)).columns
    lines = [
        "%s  %s" % (item.get("id"), item.get("title") or ""),
        "kind: %s" % (item.get("kind") or ""),
    ]
    if item.get("sva"):
        lines.append("sva: %s" % item["sva"])
    for field in ("when_to_use", "when_not_to_use", "suggest", "constraints"):
        if item.get(field):
            lines.extend(_wrap_prose(field, str(item[field]), width))
    if key_details is not None:
        lines.append("keys:")
        for detail in key_details:
            qualifiers = [str(detail.get("type") or "undocumented type")]
            qualifiers.append("required" if detail.get("required") else "optional")
            if detail.get("default") is not None:
                qualifiers.append("default=%r" % detail["default"])
            if detail.get("allowed"):
                qualifiers.append(
                    "allowed=%s" % "|".join(str(value) for value in detail["allowed"])
                )
            constraints = detail.get("constraints") or {}
            qualifiers.extend("%s=%s" % pair for pair in constraints.items())
            lines.append("  %s — %s" % (detail["path"], "; ".join(qualifiers)))
            for field in ("description", "note"):
                if detail.get(field):
                    lines.extend(
                        _wrap_prose(field, str(detail[field]), width, indent="    ")
                    )
    related = item.get("related") or []
    if related:
        lines.append("related: %s" % ", ".join(str(item) for item in related))
    snippet = (item.get("snippet") or "").rstrip()
    if snippet:
        lines.append("snippet:")
        lines.extend("  %s" % line for line in snippet.splitlines())
    return "\n".join(lines)


def features_for_paths(paths: SpaPaths) -> List[Dict[str, Any]]:
    return load_features(paths.spa_home)
