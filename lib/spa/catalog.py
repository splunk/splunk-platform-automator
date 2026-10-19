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

_SECRET_LEAF = re.compile(r"password|secret|token|private_key", re.IGNORECASE)
_INTERNAL_ID = re.compile(r"\b(?:setting|topology|provider)\.[A-Za-z0-9_.]+\b")
_PASSWORD_LITERAL = re.compile(
    r"(?im)^[ \t-]*[\w.]*password\w*\s*:\s*(?!.*(?:lookup\(|vault)).+$"
)
_NOT_CONFIGURABLE = "not a splunk_config.yml setting"
_MERGE_MODES = frozenset({"deep", "replace"})
_PUBLIC_FIELDS = (
    "title",
    "kind",
    "sva",
    "when_to_use",
    "when_not_to_use",
    "suggest",
    "constraints",
    "search_terms",
)


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


def record_paths(item: Dict[str, Any]) -> List[str]:
    return [key_path(key) for key in item.get("keys") or [] if key_path(key)]


def feature_class(item: Dict[str, Any]) -> str:
    """Return setting, layout, or unsupported for a catalog record."""
    if item.get("kind") == "setting" and item.get("selector"):
        return "setting"
    if item.get("kind") in {"topology", "provider"} and record_paths(item):
        return "layout"
    return "unsupported"


def search_features(features: Iterable[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Return raw records whose public text matches. Internal ids are not indexed."""
    needles = [part.lower() for part in query.split() if part.strip()]
    if not needles:
        return list(features)
    schema = schema_key_details()
    found = []
    for item in features:
        if _search_rank(item, needles, schema) is not None:
            found.append(item)
    return found


def _without_brackets(value: str) -> str:
    return value.replace("[]", "")


def shell_label(label: str) -> str:
    """Quote selectors that zsh would treat as a glob."""
    if "[]" in label:
        return "'%s'" % label
    return label


def resolve_feature(features: Iterable[Dict[str, Any]], ident: str) -> Optional[Dict[str, Any]]:
    """Resolve one public selector, layout id, or unsupported title.

    Old ``setting.*`` selectors are unknown. Settings match their schema selector
    exactly, or the same selector with ``[]`` omitted so zsh does not need quotes.
    Layouts match ``topology.*`` / implemented ``provider.*`` ids.
    Records with no schema key match their exact human title.
    """
    ident = ident.strip()
    if not ident or ident.startswith("setting."):
        return None
    items = list(features)
    selector_hits = [item for item in items if item.get("selector") == ident]
    if len(selector_hits) == 1:
        return selector_hits[0]
    if len(selector_hits) > 1:
        return None
    folded = _without_brackets(ident)
    folded_hits = [
        item
        for item in items
        if item.get("selector") and _without_brackets(str(item["selector"])) == folded
    ]
    if len(folded_hits) == 1:
        return folded_hits[0]
    if len(folded_hits) > 1:
        return None
    layout_hits = [
        item
        for item in items
        if feature_class(item) == "layout" and str(item.get("id")) == ident
    ]
    if len(layout_hits) == 1:
        return layout_hits[0]
    title_hits = [
        item
        for item in items
        if feature_class(item) == "unsupported" and str(item.get("title") or "") == ident
    ]
    if len(title_hits) == 1:
        return title_hits[0]
    return None


def get_feature(features: Iterable[Dict[str, Any]], ident: str) -> Optional[Dict[str, Any]]:
    return resolve_feature(features, ident)


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


_OMIT_DEFAULT = re.compile(r"\bDefault (.+?)\.(?: Omit| VirtualBox|$)")
_SITE_FACTOR = re.compile(r"^origin:\d+, total:\d+$")


def _omit_default_value(description: str, type_name: str) -> Any:
    """Copyable value used when the key is left out of splunk_config.yml.

    Prose such as "Default is a lab password" is not a value. Returns None when
    there is nothing safe to publish.
    """
    match = _OMIT_DEFAULT.search(description or "")
    if not match:
        return None
    raw = match.group(1).strip()
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    if lowered == "none":
        return [] if type_name.startswith("list") else None
    named = re.fullmatch(r"is (\S+)", raw)
    if named:
        token = named.group(1)
        return [token] if type_name.startswith("list") else token
    if " " in raw and not _SITE_FACTOR.fullmatch(raw):
        return None
    if type_name.startswith("list"):
        return [raw]
    return raw


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
            elif not field.is_required() and not _is_secret_path(path):
                omit = _omit_default_value(str(field.description or ""), type_name)
                if omit is not None:
                    detail["default"] = omit
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


def _path_regex(pattern: str) -> "re.Pattern[str]":
    parts = []
    for part in pattern.split("."):
        if part.startswith("<") and part.endswith(">") and len(part) > 2:
            parts.append(r"[^.\[\]]+")
        else:
            parts.append(re.escape(part))
    return re.compile(r"^" + r"\.".join(parts) + r"$")


def path_is_schema_backed(path: str, schema: Dict[str, Dict[str, Any]]) -> bool:
    """True when path is a schema field or a dynamic child of one."""
    if path in schema:
        return True
    parts = path.split(".")
    built: List[str] = []
    for part in parts[:-1]:
        built.append(part[:-2] if part.endswith("[]") else part)
        if ".".join(built) in schema:
            return True
    return False


def _segment_match(pattern: str, written: str) -> bool:
    if pattern.startswith("<") and pattern.endswith(">") and len(pattern) > 2:
        return bool(written) and "[" not in written
    left = pattern[:-2] if pattern.endswith("[]") else pattern
    right = written[:-2] if written.endswith("[]") else written
    return left == right


def path_related(path: str, declared: Iterable[str]) -> bool:
    """True when path equals, contains, or sits inside a declared catalog path."""
    written = path.split(".")
    for pattern in declared:
        expected = pattern.split(".")
        limit = min(len(written), len(expected))
        if limit and all(_segment_match(expected[i], written[i]) for i in range(limit)):
            return True
    return False


def snippet_yaml_paths(snippet: str) -> List[str]:
    """Return dotted paths written by a catalog snippet. Comments yield none."""
    loaded = yaml.safe_load(snippet) if snippet and snippet.strip() else None
    found: List[str] = []

    def walk(node: Any, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            path = "%s.%s" % (prefix, key) if prefix else str(key)
            found.append(path)
            if isinstance(value, dict):
                walk(value, path)
            elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
                found.append(path + "[]")
                for item in value:
                    if isinstance(item, dict):
                        walk(item, path + "[]")

    if loaded is not None:
        walk(loaded, "")
    return found


def snippet_is_safe(snippet: str) -> bool:
    if "-----BEGIN" in snippet:
        return False
    return _PASSWORD_LITERAL.search(snippet) is None


def _search_blobs(item: Dict[str, Any], schema: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    paths = record_paths(item)
    allowed: List[str] = []
    for path in paths:
        values = (schema.get(path) or {}).get("allowed") or []
        allowed.extend(str(value) for value in values)
    klass = feature_class(item)
    selector = str(item.get("selector") or "")
    if klass == "layout":
        selector = str(item.get("id") or "")
    terms = item.get("search_terms") or []
    if isinstance(terms, str):
        terms = [terms]
    return {
        "selector": selector,
        "schema path": " ".join(paths),
        "search term": " ".join(str(term) for term in terms),
        "allowed value": " ".join(allowed),
        "title": str(item.get("title") or ""),
        "guidance": " ".join(
            str(item.get(name) or "")
            for name in ("when_to_use", "when_not_to_use", "suggest", "constraints")
        ),
        "snippet": str(item.get("snippet") or ""),
        "sva": str(item.get("sva") or ""),
    }


def _search_rank(
    item: Dict[str, Any], needles: List[str], schema: Dict[str, Dict[str, Any]]
) -> Optional[Tuple[int, str, List[str]]]:
    blobs = _search_blobs(item, schema)
    combined = " ".join(blobs.values()).lower()

    def _contains(needle: str, blob: str) -> bool:
        return needle in blob or _without_brackets(needle) in _without_brackets(blob)

    if needles and not all(_contains(needle, combined) for needle in needles):
        return None
    query = " ".join(needles)
    order = (
        (0, "selector"),
        (1, "schema path"),
        (2, "search term"),
        (3, "allowed value"),
        (4, "title"),
        (5, "guidance"),
        (6, "snippet"),
    )
    paths = record_paths(item)
    rank = 7
    reason = "guidance"
    for score, name in order:
        blob = blobs[name].lower()
        if not blob or not all(_contains(needle, blob) for needle in needles):
            continue
        folded_query = _without_brackets(query)
        exact = query == blob.strip() or folded_query == _without_brackets(blob.strip()) or (
            name in {"selector", "schema path"}
            and any(
                query == path.lower() or folded_query == _without_brackets(path.lower())
                for path in paths
            )
        )
        if name == "selector" and (
            query == blob.strip() or folded_query == _without_brackets(blob.strip())
        ):
            return -1, "selector", _matched_keys(item, needles, schema)
        if exact and name == "schema path":
            return 0, "schema path", _matched_keys(item, needles, schema)
        if score < rank:
            rank = score
            reason = name
    return rank, reason, _matched_keys(item, needles, schema)


def _matched_keys(
    item: Dict[str, Any], needles: List[str], schema: Dict[str, Dict[str, Any]]
) -> List[str]:
    matched = []
    for path in record_paths(item):
        allowed = " ".join(str(value) for value in (schema.get(path) or {}).get("allowed") or [])
        blob = "%s %s" % (path.lower(), allowed.lower())
        if any(needle in blob for needle in needles):
            matched.append(path)
    return matched


def translate_related(item: Dict[str, Any], features: Iterable[Dict[str, Any]]) -> List[str]:
    by_id = {str(feature.get("id")): feature for feature in features}
    labels = []
    for rel in item.get("related") or []:
        text = str(rel)
        if text.startswith("#"):
            labels.append(text)
            continue
        target = by_id.get(text)
        if target is None:
            continue
        labels.append(public_label(target))
    return labels


def public_label(item: Dict[str, Any]) -> str:
    klass = feature_class(item)
    if klass == "setting":
        return str(item.get("selector") or "")
    if klass == "layout":
        return str(item.get("id") or "")
    return str(item.get("title") or "")


def _row_label(item: Dict[str, Any]) -> str:
    if item.get("label"):
        return str(item["label"])
    if item.get("selector"):
        return str(item["selector"])
    ident = str(item.get("id") or "")
    if ident and not ident.startswith("setting."):
        return ident
    return str(item.get("title") or "")


def decision_guidance(item: Dict[str, Any]) -> str:
    return str(item.get("when_to_use") or item.get("when_not_to_use") or "").strip()


def guidance_is_useful(item: Dict[str, Any]) -> bool:
    text = " ".join(decision_guidance(item).split()).lower()
    if len(text) < 24:
        return False
    echoes = {
        " ".join(str(item.get("title") or "").split()).lower(),
        " ".join(str(item.get("selector") or "").split()).lower(),
        " ".join(str(item.get("id") or "").split()).lower(),
    }
    return text not in echoes and _INTERNAL_ID.fullmatch(text) is None


def build_apply(item: Dict[str, Any], schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    paths = [path for path in record_paths(item) if path_is_schema_backed(path, schema)]
    snippet = str(item.get("snippet") or "").rstrip()
    return {
        "merge": item.get("merge"),
        "snippet": snippet,
        "paths": paths,
    }


def validate_feature_catalog(
    features: Iterable[Dict[str, Any]], schema: Optional[Dict[str, Dict[str, Any]]] = None
) -> None:
    """Fail closed when a public selector, snippet, or description is unsafe."""
    items = list(features)
    schema = schema if schema is not None else schema_key_details()
    errors: List[str] = []
    seen: Dict[str, str] = {}
    for item in items:
        ident = str(item.get("id") or "")
        if not guidance_is_useful(item):
            errors.append("%s needs behavioral when_to_use or when_not_to_use" % ident)
        if item.get("kind") == "setting":
            public_text = "\n".join(
                str(item.get(name) or "")
                for name in ("when_to_use", "when_not_to_use", "suggest", "snippet")
            )
            for key in item.get("keys") or []:
                if isinstance(key, dict) and key.get("note"):
                    public_text += "\n" + str(key["note"])
            if _INTERNAL_ID.search(public_text):
                errors.append("%s guidance leaks an internal id" % ident)
        paths = record_paths(item)
        selector = item.get("selector")
        if item.get("kind") == "setting" and paths:
            if not selector or selector not in paths:
                errors.append("%s selector must be one of its schema paths" % ident)
            elif not path_is_schema_backed(str(selector), schema):
                errors.append("%s selector is not schema-backed: %s" % (ident, selector))
            elif str(selector) in seen:
                errors.append("duplicate selector %s (%s, %s)" % (selector, seen[str(selector)], ident))
            else:
                seen[str(selector)] = ident
            if item.get("merge") not in _MERGE_MODES:
                errors.append("%s merge must be deep or replace" % ident)
            snippet = str(item.get("snippet") or "")
            if not snippet_is_safe(snippet):
                errors.append("%s snippet contains a credential or certificate" % ident)
            try:
                written = snippet_yaml_paths(snippet)
            except yaml.YAMLError as exc:
                errors.append("%s snippet is not YAML: %s" % (ident, exc))
                written = []
            for path in written:
                if not path_related(path, paths):
                    errors.append("%s snippet path is not declared: %s" % (ident, path))
        elif selector:
            errors.append("%s must not publish a selector" % ident)
    described = {
        path: public_key_description(path, schema.get(path) or {"path": path}, items, schema)
        for path in schema
    }
    for path, text in described.items():
        if not description_is_useful(path, text):
            errors.append("schema key lacks a useful description: %s" % path)
    if errors:
        raise ValueError("feature catalog: " + "; ".join(errors))


def public_feature(
    item: Dict[str, Any],
    features: Iterable[Dict[str, Any]],
    *,
    include_keys: bool = False,
    schema: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Public list/search/show record. Settings expose selector, never internal id."""
    feature_list = list(features)
    row: Dict[str, Any] = {}
    for name in _PUBLIC_FIELDS:
        value = item.get(name)
        if value not in (None, "", []):
            row[name] = value
    klass = feature_class(item)
    if klass == "setting":
        row["selector"] = item.get("selector")
        row["configurable"] = True
        row["label"] = public_label(item)
    elif klass == "layout":
        row["id"] = item.get("id")
        row["label"] = public_label(item)
    else:
        row["configurable"] = False
        row["marker"] = _NOT_CONFIGURABLE
        row["label"] = public_label(item)
    related = translate_related(item, feature_list)
    if related:
        row["related"] = related
    if include_keys and klass == "setting":
        schema = schema if schema is not None else schema_key_details()
        row["key_details"] = _public_key_details(item, feature_list, schema)
        row["apply"] = build_apply(item, schema)
    elif include_keys and klass == "layout":
        schema = schema if schema is not None else schema_key_details()
        row["key_details"] = _public_key_details(item, feature_list, schema)
    return row


def summarize_feature(
    item: Dict[str, Any], features: Optional[Iterable[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Decision context without snippets or per-key details."""
    return public_feature(item, features if features is not None else [item])


def list_payload(spa_home: Path) -> Dict[str, Any]:
    features = load_features(spa_home)
    validate_feature_catalog(features)
    return {"features": [summarize_feature(item, features) for item in features]}


def search_payload(features: Iterable[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    items = list(features)
    schema = schema_key_details()
    needles = [part.lower() for part in query.split() if part.strip()]
    ranked = []
    for item in items:
        scored = _search_rank(item, needles, schema)
        if scored is None:
            continue
        rank, reason, matched = scored
        row = summarize_feature(item, items)
        row["matched_keys"] = matched
        row["match_reason"] = reason
        ranked.append((rank, public_label(item), row))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))
    return [row for _rank, _label, row in ranked]


def format_feature_rows(features: List[Dict[str, Any]], width: Optional[int] = None) -> str:
    """One record per block: public label, title, then guidance under the title."""
    rows = [item for item in features if _row_label(item)]
    if not rows:
        return ""
    id_width = max(len(shell_label(_row_label(item))) for item in rows)
    indent = " " * (id_width + 2)
    if width is None:
        width = shutil.get_terminal_size(fallback=(100, 24)).columns
    text_width = max(width - len(indent), 40)
    lines: List[str] = []
    for item in rows:
        label = shell_label(_row_label(item))
        title = str(item.get("title") or "")
        marker = item.get("marker")
        if marker and _row_label(item) == title:
            head = "%s  %s" % (title, marker)
        else:
            head = "%s  %s" % (label.ljust(id_width), title)
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


def _public_key_details(
    item: Dict[str, Any],
    features: Iterable[Dict[str, Any]],
    schema: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    feature_list = list(features)
    details = []
    for detail in feature_key_details(item):
        row = dict(detail)
        path = str(row.get("path") or "")
        if _is_secret_path(path):
            row.pop("default", None)
        schema_detail = schema.get(path) or {"path": path}
        row["description"] = public_key_description(path, schema_detail, feature_list, schema)
        row.pop("note", None)
        details.append(row)
    return details


def _scrub_catalog_ids(text: str) -> str:
    cleaned = _INTERNAL_ID.sub("", text)
    return " ".join(cleaned.split()).strip(" -;,")


def description_is_useful(path: str, text: str) -> bool:
    compact = " ".join(text.split())
    if len(compact) < 12:
        return False
    lowered = compact.lower()
    echoes = {path.lower(), path.rsplit(".", 1)[-1].lower()}
    if lowered in echoes or _INTERNAL_ID.fullmatch(compact):
        return False
    return True


_OVERRIDE_ROOTS = ("os", "virtualbox", "terraform")
_ENDPOINT_LABELS = (
    (".splunk_ssl.web", "Splunk Web"),
    (".splunk_ssl.inputs", "receiving inputs"),
    (".splunk_ssl.outputs", "forwarding outputs"),
)


def _schema_container(path: str, schema: Dict[str, Dict[str, Any]]) -> bool:
    """True when another schema path is nested under this one, including list items."""
    dotted = path + "."
    listed = path + "[]."
    return any(
        other.startswith(dotted) or other.startswith(listed)
        for other in schema
        if other != path
    )


def _global_counterpart(path: str) -> Optional[str]:
    host = "splunk_hosts[]."
    if not path.startswith(host):
        return None
    rest = path[len(host):]
    for root in _OVERRIDE_ROOTS:
        if rest == root or rest.startswith(root + "."):
            return rest
    return None


def _specialize_endpoint(path: str, text: str) -> str:
    for needle, label in _ENDPOINT_LABELS:
        if needle in path:
            return text.replace("this endpoint", label)
    return text


def _catalog_notes(path: str, features: Iterable[Dict[str, Any]]) -> List[str]:
    notes: List[str] = []
    for item in features:
        for key in item.get("keys") or []:
            if not isinstance(key, dict) or key_path(key) != path:
                continue
            note = " ".join(str(key.get("note") or "").split())
            if note and note not in notes:
                notes.append(note)
    return notes


def _note_already_said(note: str, text: str) -> bool:
    """True when the note restates the schema sentence instead of adding a constraint."""
    norm_note = " ".join(note.lower().split())
    norm_text = " ".join(text.lower().split())
    if not norm_note or norm_note in norm_text:
        return True
    note_words = set(re.findall(r"[a-z0-9]+", norm_note))
    text_words = set(re.findall(r"[a-z0-9]+", norm_text))
    if not note_words:
        return True
    return len(note_words & text_words) / float(len(note_words)) >= 0.72


_PUBLISHED_DEFAULT = re.compile(r"\s*Default .+?\. Omit the key to keep that\.")


def _without_published_default(text: str, detail: Dict[str, Any]) -> str:
    """Drop the default sentence when Qualifiers already carries that value."""
    if detail.get("default") is None:
        return text
    return " ".join(_PUBLISHED_DEFAULT.sub(" ", text).split())


def public_key_description(
    path: str,
    detail: Dict[str, Any],
    features: Iterable[Dict[str, Any]],
    schema: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Schema behavior, a per-host override prefix, then a leaf-only extra constraint."""
    schema = schema if schema is not None else schema_key_details()
    text = _specialize_endpoint(path, str(detail.get("description") or "").strip())
    text = _without_published_default(text, detail)
    counterpart = _global_counterpart(path)
    if counterpart and text:
        text = "Per-host override of `%s`: %s" % (counterpart, text)
    if text and not _schema_container(path, schema):
        for note in _catalog_notes(path, features):
            if _note_already_said(note, text):
                continue
            text = "%s %s" % (text, note)
    elif not text:
        notes = _catalog_notes(path, features)
        text = " ".join(notes)
    return _scrub_catalog_ids(text)


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
    label = shell_label(_row_label(item))
    title = str(item.get("title") or "")
    if item.get("marker") and _row_label(item) == title:
        lines = ["%s  %s" % (title, item["marker"])]
    else:
        lines = ["%s  %s" % (label, title)]
    lines.append("kind: %s" % (item.get("kind") or ""))
    if item.get("marker") and label != title:
        lines.append(str(item["marker"]))
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
            lines.append("  %s — %s" % (shell_label(str(detail["path"])), "; ".join(qualifiers)))
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


# Top-level splunk_config.yml areas for the human settings dump.
# Unknown roots land in "other" so a new schema field cannot disappear.
CONFIG_AREAS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("identity", "Identity", ("plugin",)),
    ("general", "General", ("general", "custom")),
    ("os", "OS", ("os",)),
    ("provider", "Provider", ("terraform", "virtualbox", "aws")),
    ("defaults", "Defaults", ("splunk_defaults", "splunk_dirs", "splunk_systemd", "splunk_environments")),
    ("hosts", "Hosts", ("splunk_hosts",)),
    ("apps", "Apps", ("splunk_app_deployment", "splunk_apps")),
    ("clustering", "Clustering", ("splunk_idxclusters", "splunk_shclusters")),
)

_AREA_BY_ROOT = {
    root: area_id
    for area_id, _title, roots in CONFIG_AREAS
    for root in roots
}

def _root_segment(path: str) -> str:
    head = path.split(".", 1)[0]
    if head.endswith("[]"):
        head = head[:-2]
    return head


def _area_id_for_path(path: str) -> str:
    return _AREA_BY_ROOT.get(_root_segment(path), "other")


def _path_rank(path: str, roots: Tuple[str, ...]) -> Tuple[int, str]:
    root = _root_segment(path)
    try:
        rank = roots.index(root)
    except ValueError:
        rank = len(roots)
    return (rank, path)


def _is_secret_path(path: str) -> bool:
    leaf = path.rsplit(".", 1)[-1]
    leaf = leaf.replace("[]", "")
    if leaf.startswith("<") and leaf.endswith(">"):
        leaf = leaf[1:-1]
    return _SECRET_LEAF.search(leaf) is not None


def _public_key_row(detail: Dict[str, Any], description: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "path": detail["path"],
        "type": detail.get("type") or "any",
        "required": bool(detail.get("required")),
        "description": description,
    }
    for name in ("constraints", "allowed"):
        if detail.get(name):
            row[name] = detail[name]
    if detail.get("default") is not None and not _is_secret_path(str(detail["path"])):
        row["default"] = detail["default"]
    return row


def config_schema_payload(spa_home: Path) -> Dict[str, Any]:
    """Schema envelope of every splunk_config.yml key, grouped for humans and agents."""
    features = load_features(spa_home)
    schema = schema_key_details()
    validate_feature_catalog(features, schema)
    buckets: Dict[str, Dict[str, Any]] = {
        area_id: {"id": area_id, "title": title, "keys": [], "snippets": []}
        for area_id, title, _roots in CONFIG_AREAS
    }
    for path, detail in schema.items():
        area_id = _area_id_for_path(path)
        description = public_key_description(path, detail, features)
        buckets[area_id]["keys"].append(_public_key_row(detail, description))
    root_order = {area_id: roots for area_id, _title, roots in CONFIG_AREAS}
    for area_id, area in buckets.items():
        roots = root_order[area_id]
        area["keys"].sort(key=lambda row, roots=roots: _path_rank(row["path"], roots))
    seen_selectors: Set[str] = set()
    for feature in features:
        if feature_class(feature) != "setting":
            continue
        selector = str(feature.get("selector") or "")
        snippet = str(feature.get("snippet") or "").rstrip()
        if not selector or not snippet or selector in seen_selectors:
            continue
        seen_selectors.add(selector)
        area_id = _area_id_for_path(selector)
        buckets[area_id]["snippets"].append(
            {
                "selector": selector,
                "title": str(feature.get("title") or ""),
                "guidance": decision_guidance(feature),
                "yaml": snippet,
            }
        )
    for area_id, area in buckets.items():
        roots = root_order[area_id]
        area["snippets"].sort(key=lambda item, roots=roots: _path_rank(item["selector"], roots))
    return {"areas": [buckets[area_id] for area_id, _title, _roots in CONFIG_AREAS]}


def _qualifier_text(row: Dict[str, Any]) -> str:
    parts = ["required" if row.get("required") else "optional"]
    if row.get("default") is not None:
        parts.append("default=%r" % (row["default"],))
    if row.get("allowed"):
        parts.append("allowed=%s" % "|".join(str(value) for value in row["allowed"]))
    constraints = row.get("constraints") or {}
    parts.extend("%s=%s" % pair for pair in constraints.items())
    return "; ".join(parts)


def format_config_markdown(spa_home: Path) -> str:
    """Render the settings dump checked in as docs/config.md."""
    from spa.agent import _markdown_cell

    payload = config_schema_payload(spa_home)
    lines = [
        "<!-- Generated by spa features schema --markdown. Do not edit by hand. -->",
        "",
        "# splunk_config.yml settings",
        "",
        "Generated from the Pydantic schema and `examples/catalog/features.yml`.",
        "Do not edit this file; regenerate with",
        "`spa --no-agent features schema --markdown`.",
        "Concise lookup stays `spa features list`, `search`, and `show`.",
        "CLI flags stay in [commands.md](commands.md).",
        "",
    ]
    for area in payload["areas"]:
        lines.append("## %s" % area["title"])
        lines.append("")
        keys = area.get("keys") or []
        if keys:
            lines.append("| Path | Type | Qualifiers | Description |")
            lines.append("| --- | --- | --- | --- |")
            for row in keys:
                description = row.get("description") or ""
                lines.append(
                    "| `%s` | %s | %s | %s |"
                    % (
                        _markdown_cell(row["path"]),
                        _markdown_cell(row.get("type") or ""),
                        _markdown_cell(_qualifier_text(row)),
                        _markdown_cell(description),
                    )
                )
            lines.append("")
        snippets = area.get("snippets") or []
        if snippets:
            lines.append("### Snippets")
            lines.append("")
            for item in snippets:
                lines.append("#### %s" % item.get("title") or item["selector"])
                lines.append("")
                lines.append("`%s`" % item["selector"])
                lines.append("")
                if item.get("guidance"):
                    lines.append(item["guidance"])
                    lines.append("")
                lines.append("```yaml")
                lines.append(item["yaml"])
                lines.append("```")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"
