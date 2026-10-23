"""One-level schema tree for spa config explain and search.

Human text and agent JSON both render this structure. A later GUI calls the
same data. Canonical schema paths keep ``[]`` internally; user paths do not.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from spa.catalog import (
    feature_command,
    key_path,
    load_features,
    public_key_description,
    schema_key_details,
    snippet_is_safe,
)
from spa.config_edit import _ONE_OF, _is_secret

_ROOT_DESCRIPTION = "Configurable sections of splunk_config.yml."
_SEARCH_LIMIT = 10
_LIST_NOTE = "several explicit hostnames have no selector; author that form with spa config merge"
# Roots that exist both at the top of splunk_config.yml and under splunk_hosts.
_SCOPED_ROOTS = ("os", "virtualbox", "terraform", "custom")


def user_path(canonical: str) -> str:
    """Drop empty list markers. ``splunk_hosts[].roles`` becomes ``splunk_hosts.roles``."""
    return canonical.replace("[]", "")


def explain_config(path: str = "") -> Dict[str, Any]:
    """Return one selected node and its immediate children."""
    schema = schema_key_details()
    features = load_features(_spa_home())
    target = (path or "").strip()
    if target in _layout_index(features):
        return _layout_node(target, features[ _layout_index(features)[target] ])
    canonical = _canonical(target, schema)
    if target and canonical is None:
        raise KeyError(target)
    if canonical is None:
        return _root(schema, features)
    return _node(canonical, schema, features)


def search_config(query: str) -> Dict[str, Any]:
    """Rank user paths. Each hit is only a path and a one-line description."""
    schema = schema_key_details()
    features = load_features(_spa_home())
    needles = [part.lower() for part in query.split() if part.strip()]
    rows = []
    seen = set()
    for canonical in schema:
        if canonical.endswith("[]") and canonical[:-2] in schema:
            continue
        shown = canonical[:-2] if canonical.endswith("[]") else canonical
        if shown in seen:
            continue
        seen.add(shown)
        feature = _feature_for(shown, canonical if canonical.endswith("[]") else canonical, features)
        description = _scope_search_line(
            _one_line(_decision_line(feature) or _describe(shown if shown == user_path(canonical) else canonical, schema, features)),
            setting_scope(user_path(shown), schema),
        )
        blob = "%s %s" % (shown.lower(), description.lower())
        if needles and not all(needle in blob for needle in needles):
            continue
        rank = 0 if shown.lower() == query.lower() else 1 if shown.lower().endswith(query.lower()) else 2
        rows.append((rank, shown, {"path": user_path(shown), "description": description}))
    from spa.catalog import app_entry_child_names, app_entry_field_names

    for name in app_entry_field_names():
        shown = "splunk_app_deployment.apps.%s" % name
        description = _one_line("App entry field %s." % name)
        blob = "%s %s" % (shown.lower(), description.lower())
        if not needles or all(needle in blob for needle in needles):
            rows.append((2, shown, {"path": shown, "description": description}))
    for parent in ("content_pack_api", "customizations"):
        for name in app_entry_child_names(parent):
            shown = "splunk_app_deployment.apps.%s.%s" % (parent, name)
            description = _one_line("App entry field %s." % shown)
            blob = shown.lower() + " " + description.lower()
            if not needles or all(needle in blob for needle in needles):
                rows.append((2, shown, {"path": shown, "description": description}))
    for ident, item in _layout_index(features).items():
        feature = features[item]
        description = _one_line(_decision_line(feature) or str(feature.get("title") or ""))
        blob = "%s %s" % (ident.lower(), description.lower())
        if needles and not all(needle in blob for needle in needles):
            continue
        rows.append((3, ident, {"path": ident, "description": description}))
    rows.sort(key=lambda item: (item[0], item[1]))
    total = len(rows)
    matches = [row for _rank, _path, row in rows[:_SEARCH_LIMIT]]
    return {"matches": matches, "total_matches": total, "truncated": total > _SEARCH_LIMIT}


def explain_candidates(token: str) -> List[str]:
    """Immediate user paths for a later shell. No empty brackets."""
    schema = schema_key_details()
    features = load_features(_spa_home())
    text = (token or "").strip()
    if not text:
        return _root_names(schema, features)
    if text in _layout_index(features) or _canonical(text, schema) is not None:
        try:
            data = explain_config(text)
        except KeyError:
            data = {}
        names = []
        for group in ("identity",):
            for item in (data.get(group) or {}).get("one_of") or []:
                names.append("%s.%s" % (text, item["name"]) if text else item["name"])
        for item in data.get("fields") or []:
            names.append("%s.%s" % (text, item["name"]) if text else item["name"])
        for item in data.get("layouts") or []:
            names.append(item["name"])
        if names:
            return names
    prefix = text if text.endswith(".") else text
    pool = _root_names(schema, features)
    pool.extend(_all_user_paths(schema))
    return sorted({path for path in pool if path.startswith(prefix) and path != text})


def format_explain(data: Dict[str, Any]) -> str:
    """kubectl-style page for one node. This is a renderer, not a second tree."""
    lines: List[str] = []
    if data.get("path"):
        lines.append("PATH: %s" % data["path"])
        qualifiers = [str(data.get("type") or "object")]
        if data.get("required"):
            qualifiers.append("required")
        lines.append("TYPE: %s" % "; ".join(qualifiers))
        lines.append("")
    lines.append("DESCRIPTION:")
    lines.append("    %s" % (data.get("description") or ""))
    for label, key in (("WHEN", "when_to_use"), ("WHEN NOT", "when_not_to_use")):
        if data.get(key):
            lines.append("")
            lines.append("%s:" % label)
            lines.append("    %s" % data[key])
    for key in ("suggest", "constraints"):
        if data.get(key):
            lines.append("")
            lines.append("%s:" % key.upper())
            lines.append("    %s" % data[key])
    if data.get("scope"):
        lines.extend(_format_scope(data["scope"]))
    if data.get("allowed"):
        lines.append("")
        lines.append("allowed: %s" % ", ".join(str(item) for item in data["allowed"]))
    if "default" in data:
        lines.append("default: %s" % json.dumps(data["default"]))
    identity = (data.get("identity") or {}).get("one_of") or []
    if identity:
        lines.append("")
        lines.append("IDENTITY (choose exactly one):")
        for item in identity:
            lines.append("  %s   <%s>" % (item["name"], item.get("type") or "string"))
            if item.get("description"):
                lines.append("    %s" % item["description"])
            if item.get("selector"):
                lines.append("    selector: %s" % item["selector"])
    fields = data.get("fields") or []
    if fields:
        lines.append("")
        lines.append("FIELDS:")
        width = max(len(item["name"]) for item in fields)
        for item in fields:
            flag = "; required" if item.get("required") else ""
            lines.append("  %s <%s>%s" % (item["name"].ljust(width), item.get("type") or "object", flag))
            if item.get("description"):
                lines.append("    %s" % item["description"])
    layouts = data.get("layouts") or []
    if layouts:
        lines.append("")
        lines.append("LAYOUTS:")
        width = max(len(item["name"]) for item in layouts)
        for item in layouts:
            lines.append("  %s %s" % (item["name"].ljust(width), item.get("description") or ""))
    shown = data.get("example") or data.get("command")
    if shown:
        lines.append("")
        lines.append("command:")
        lines.append("  %s" % shown)
    if data.get("note"):
        lines.append("note: %s" % data["note"])
    return "\n".join(lines).rstrip() + "\n"


def setting_scope(path: str, schema: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Pair a global setting with its host form when both exist.

    Paths with no counterpart return None. List fields under os and custom
    combine with the global list. Other paired values replace it for that host.
    """
    pair = _scope_pair(user_path(path), schema)
    if not pair:
        return None
    global_path, host_path = pair
    behavior = _scope_behavior(global_path, schema)
    if user_path(path) == global_path:
        return {"applies_to": "all_hosts", "per_host_path": host_path, "behavior": behavior}
    return {"applies_to": "one_host", "global_path": global_path, "behavior": behavior}


def _scope_pair(shown: str, schema: Dict[str, Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    if shown.startswith("splunk_hosts."):
        rest = shown[len("splunk_hosts.") :]
        head = rest.split(".", 1)[0]
        if head in _SCOPED_ROOTS:
            global_path = rest
        elif "." not in rest and _known("splunk_defaults.%s" % rest, schema):
            global_path = "splunk_defaults.%s" % rest
        else:
            return None
        host_path = shown
    elif shown.split(".", 1)[0] in _SCOPED_ROOTS:
        global_path = shown
        host_path = "splunk_hosts.%s" % shown
    elif shown.startswith("splunk_defaults.") and shown.count(".") == 1:
        global_path = shown
        host_path = "splunk_hosts.%s" % shown.split(".", 1)[1]
    else:
        return None
    if not _known(global_path, schema) or not _known(host_path, schema):
        return None
    return global_path, host_path


def _known(path: str, schema: Dict[str, Dict[str, Any]]) -> bool:
    return path in schema or _canonical(path, schema) is not None


def _scope_behavior(global_path: str, schema: Dict[str, Dict[str, Any]]) -> str:
    root = global_path.split(".", 1)[0]
    canonical = _canonical(global_path, schema) or global_path
    type_name = str((_detail(canonical, schema) or {}).get("type") or "")
    # Inventory unions list keys inside os and custom. Other paired values replace.
    if root in ("os", "custom") and not type_name.startswith(("string", "bool", "integer", "number", "float")):
        if type_name.startswith("list"):
            return "merge"
        return "mixed"
    return "replace"


def _scope_hint(scope: Optional[Dict[str, str]]) -> str:
    if not scope:
        return ""
    if scope["applies_to"] == "all_hosts":
        return " Also per host: %s." % scope["per_host_path"]
    return " Overrides %s." % scope["global_path"]


def _scope_search_line(description: str, scope: Optional[Dict[str, str]]) -> str:
    if not scope:
        return description
    if scope["applies_to"] == "all_hosts":
        return "All hosts. %s Per-host: %s." % (description, scope["per_host_path"])
    return "Per-host. %s Global: %s." % (description, scope["global_path"])


def _format_scope(scope: Dict[str, str]) -> List[str]:
    lines = ["", "SCOPE:"]
    if scope.get("applies_to") == "all_hosts":
        lines.append("    Applies to all hosts.")
        lines.append("    Per-host alternative: %s" % scope["per_host_path"])
    else:
        lines.append("    Applies only to the selected host or host group.")
        lines.append("    Global setting: %s" % scope["global_path"])
    behavior = {
        "merge": "Each host gets the global list plus its own items.",
        "replace": "A per-host value replaces the global value for that host.",
        "mixed": (
            "Each host gets the global list plus its own items. "
            "Other per-host values replace the global value for that host."
        ),
    }.get(scope.get("behavior") or "")
    if behavior:
        lines.append("    %s" % behavior)
    return lines


def _spa_home() -> Path:
    return Path(__file__).resolve().parents[2]


def _canonical(path: str, schema: Dict[str, Dict[str, Any]]) -> Optional[str]:
    if not path:
        return None
    if path == "splunk_app_deployment.apps" or path.startswith("splunk_app_deployment.apps."):
        return _app_canonical(path)
    if path in schema and any(key.startswith(path + "[].") or key == path + "[]" for key in schema):
        return path + "[]"
    if path in schema:
        return path
    parts = path.split(".")
    built = ""
    for part in parts:
        built = part if not built else "%s.%s" % (built, part)
        if (built + "[]") in schema or any(key.startswith(built + "[].") for key in schema):
            if part != parts[-1] or (built + "[]") in schema:
                built += "[]"
    if built in schema or any(key.startswith(built + ".") for key in schema):
        return built
    return None


def _children(canonical: str, schema: Dict[str, Dict[str, Any]]) -> List[str]:
    """Immediate schema paths, including list entries and map placeholders."""
    direct: List[str] = []
    prefix = canonical + "." if canonical else ""
    for key in schema:
        if canonical:
            if key.startswith(canonical + "[]."):
                remainder = key[len(canonical) + 3 :]
            elif key.startswith(prefix):
                remainder = key[len(prefix) :]
            else:
                continue
        elif "." in key or "[]" in key:
            continue
        else:
            remainder = key
        segment = remainder.split(".", 1)[0]
        if not segment:
            continue
        child = "%s.%s" % (canonical, segment) if canonical else segment
        if (child + "[]") in schema or any(item.startswith(child + "[].") for item in schema):
            child += "[]"
        known = child in schema or any(
            item.startswith(child + ".") or item.startswith(child + "[].") for item in schema
        )
        if known and child not in direct:
            direct.append(child)
    if "splunk_app_deployment.apps" in canonical:
        from spa.catalog import app_entry_child_names, app_entry_field_names

        if ".apps[]." in canonical:
            names = app_entry_child_names(canonical.split(".apps[].", 1)[1])
        elif canonical.endswith(".apps[]") or canonical.endswith(".apps"):
            names = app_entry_field_names()
        else:
            names = []
        base = canonical if canonical.endswith("[]") or ".apps[]." in canonical else canonical + "[]"
        for name in names:
            child = "%s.%s" % (base, name)
            if child not in direct:
                direct.append(child)
    return direct


def _app_canonical(path: str) -> Optional[str]:
    from spa.catalog import app_entry_field_detail

    if path == "splunk_app_deployment.apps":
        return "splunk_app_deployment.apps[]"
    relative = path[len("splunk_app_deployment.apps.") :]
    if app_entry_field_detail(relative):
        return "splunk_app_deployment.apps[]." + relative
    return None


def _detail(canonical: str, schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if canonical in schema:
        return schema[canonical]
    if canonical.endswith("[]") and canonical[:-2] in schema:
        return schema[canonical[:-2]]
    if "splunk_app_deployment.apps[]." in canonical:
        from spa.catalog import app_entry_field_detail

        found = app_entry_field_detail(canonical.split("splunk_app_deployment.apps[].", 1)[1])
        if found:
            return found
    return {}


def _root_names(schema: Dict[str, Dict[str, Any]], features: List[Dict[str, Any]]) -> List[str]:
    names = [key for key in schema if "." not in key and "[]" not in key and "<" not in key]
    names.extend(_layout_index(features))
    return names


def _all_user_paths(schema: Dict[str, Dict[str, Any]]) -> List[str]:
    paths = []
    for key in schema:
        if key.endswith("[]") and key[:-2] in schema:
            continue
        paths.append(user_path(key[:-2] if key.endswith("[]") else key))
    return paths


def _root(schema: Dict[str, Dict[str, Any]], features: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields = []
    for name in _root_names(schema, features):
        if name in _layout_index(features):
            continue
        detail = schema.get(name) or {}
        fields.append(_child(name, name, detail, features, schema))
    layouts = []
    for ident, index in _layout_index(features).items():
        item = features[index]
        layouts.append({"name": ident, "description": str(item.get("id") and item.get("title") or ident)})
    # description in the plan's root example is the topology stem for some layouts.
    # Keep the catalog title, which is what an operator can recognize.
    return {"description": _ROOT_DESCRIPTION, "fields": fields, "layouts": layouts}


def _node(canonical: str, schema: Dict[str, Dict[str, Any]], features: List[Dict[str, Any]]) -> Dict[str, Any]:
    detail = _detail(canonical, schema)
    shown = user_path(canonical[:-2] if canonical.endswith("[]") else canonical)
    feature = _feature_for(shown, canonical, features)
    data: Dict[str, Any] = {
        "path": shown,
        "type": detail.get("type") or "object",
        "description": _describe(canonical, schema, features) or str((feature or {}).get("title") or ""),
    }
    if detail.get("required"):
        data["required"] = True
    if detail.get("allowed") and not _has_children(canonical, schema):
        data["allowed"] = list(detail["allowed"])
    if detail.get("default") is not None and not _is_secret(canonical):
        data["default"] = detail["default"]
    if detail.get("constraints"):
        data["constraints"] = detail["constraints"]
    if feature:
        for key in ("when_to_use", "when_not_to_use", "suggest"):
            if feature.get(key):
                data[key] = str(feature[key]).strip()
    names = _list_names(canonical)
    identity_names = _ONE_OF.get(names) if names else None
    children = _children(canonical, schema)
    identity = []
    fields = []
    for child in children:
        leaf_name = user_path(child).split(".")[-1]
        item = _child(leaf_name, child, schema.get(child) or {}, features, schema)
        if identity_names and leaf_name in identity_names:
            selector = _identity_selector(names, leaf_name)
            if selector:
                item["selector"] = selector
            identity.append(item)
        else:
            fields.append(item)
    if identity:
        data["identity"] = {"one_of": identity}
    if fields:
        data["fields"] = fields
    command, example = _commands(canonical, shown, feature, features)
    if command:
        data["command"] = command
    if example:
        data["example"] = example
    if identity_names and "list" in identity_names:
        data["note"] = _LIST_NOTE
    scope = setting_scope(shown, schema)
    if scope:
        data["scope"] = scope
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def _has_children(canonical: str, schema: Dict[str, Dict[str, Any]]) -> bool:
    return bool(_children(canonical, schema))


def _child(name: str, canonical: str, detail: Dict[str, Any], features: List[Dict[str, Any]], schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not detail:
        detail = _detail(canonical, schema)
    item: Dict[str, Any] = {"name": name, "type": detail.get("type") or "object"}
    if detail.get("required"):
        item["required"] = True
    text = _one_line(_describe(canonical, schema, features))
    hint = _scope_hint(setting_scope(user_path(canonical[:-2] if canonical.endswith("[]") else canonical), schema))
    if hint:
        text = "%s%s" % (text, hint) if text else hint.lstrip()
    if text:
        item["description"] = text
    return item


def _describe(canonical: str, schema: Dict[str, Dict[str, Any]], features: Iterable[Dict[str, Any]]) -> str:
    detail = schema.get(canonical) or {"path": canonical}
    return public_key_description(canonical, detail, features, schema)


def _list_names(canonical: str) -> Optional[Tuple[str, ...]]:
    if not canonical.endswith("[]"):
        return None
    body = canonical[:-2]
    return tuple(part for part in body.split(".") if part and not part.startswith("<"))


def _identity_selector(names: Optional[Tuple[str, ...]], field: str) -> Optional[str]:
    if not names or field == "list":
        return None
    key = "iter.prefix" if field == "iter" else field
    return "%s[%s=NAME]" % (".".join(names), key if field != "iter" else "iter.prefix")


def _feature_for(shown: str, canonical: str, features: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    exact = [item for item in features if user_path(str(item.get("selector") or "")) == shown]
    if exact:
        return exact[0]
    if not canonical.endswith("[]"):
        return None
    for item in features:
        paths = [user_path(key_path(key)) for key in item.get("keys") or []]
        if shown in paths and user_path(str(item.get("selector") or "")).startswith(shown + "."):
            return item
    return None


def _layout_index(features: List[Dict[str, Any]]) -> Dict[str, int]:
    found = {}
    for index, item in enumerate(features):
        if item.get("kind") in {"topology", "provider"} and item.get("id"):
            found[str(item["id"])] = index
    return found


def _layout_node(ident: str, item: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {"path": ident, "type": str(item.get("kind") or "layout"), "description": str(item.get("title") or ident)}
    for key in ("when_to_use", "when_not_to_use", "suggest"):
        if item.get(key):
            data[key] = str(item[key]).strip()
    command = feature_command(item)
    if command and command.get("command"):
        data["command"] = command["command"]
        data["example"] = command["command"]
    return data


def _commands(
    canonical: str,
    shown: str,
    feature: Optional[Dict[str, Any]],
    features: List[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    if _is_secret(canonical) or _is_secret(shown):
        quoted = _quote(shown)
        return "spa config set %s --from-env NAME" % quoted, None
    if canonical.endswith("[]"):
        return _add_commands(canonical, feature)
    value = _snippet_value(shown, feature, features)
    quoted = _quote(_filled(canonical))
    template = "spa config set %s VALUE" % quoted
    if value is None:
        command = feature_command(feature) if feature else None
        return (command or {}).get("command") or template, None
    example = "spa config set %s %s" % (quoted, _quote(json.dumps(value)))
    return example, example


def _add_commands(canonical: str, feature: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    names = _list_names(canonical) or ()
    identities = _ONE_OF.get(names) or ()
    usable = [name for name in identities if name != "list"]
    if not usable:
        command = feature_command(feature) if feature else None
        return (command or {}).get("command"), None
    field = "iter.prefix" if usable[0] == "iter" else usable[0]
    template = "spa config add %s JSON_OBJECT" % _quote("%s[%s=NAME]" % (".".join(names), field))
    example = template
    snippet = str((feature or {}).get("snippet") or "")
    if snippet and snippet_is_safe(snippet):
        loaded = yaml.safe_load(snippet)
        items = loaded.get(names[0]) if isinstance(loaded, dict) else None
        if isinstance(items, list) and items and isinstance(items[0], dict):
            body = dict(items[0])
            identity = body.pop("name", None) or body.pop(field, None)
            if field == "iter.prefix":
                identity = (body.get("iter") or {}).get("prefix")
            if identity:
                example = "spa config add %s %s" % (
                    _quote("%s[%s=%s]" % (".".join(names), field, identity)),
                    _quote(json.dumps(body)),
                )
    return template, example


def _snippet_value(shown: str, feature: Optional[Dict[str, Any]], features: List[Dict[str, Any]]) -> Any:
    candidates = [feature] if feature else []
    candidates.extend(features)
    for item in candidates:
        if not item:
            continue
        snippet = str(item.get("snippet") or "")
        if not snippet or not snippet_is_safe(snippet):
            continue
        try:
            loaded = yaml.safe_load(snippet)
        except yaml.YAMLError:
            continue
        found = _dig(loaded, shown.split("."))
        if found not in (None, {}, []):
            return found
    return None


def _dig(node: Any, parts: List[str]) -> Any:
    if not parts:
        return node
    if isinstance(node, list):
        return _dig(node[0], parts) if node else None
    if isinstance(node, dict) and parts[0] in node:
        return _dig(node[parts[0]], parts[1:])
    return None


def _filled(canonical: str) -> str:
    if "[]" not in canonical:
        return user_path(canonical)
    names = _list_names(canonical.split(".", 1)[0] + "[]" if canonical.startswith("splunk_") else canonical[: canonical.find("]") + 1 if False else canonical])
    # Replace the first [] with the non-list identity.
    head = canonical.split("[]", 1)[0]
    list_names = tuple(part for part in head.split(".") if part)
    identities = _ONE_OF.get(list_names) or ("name",)
    field = next((name for name in identities if name != "list"), identities[0])
    key = "iter.prefix" if field == "iter" else field
    return user_path(canonical.replace("[]", "[%s=NAME]" % key, 1))


def _quote(text: str) -> str:
    if any(char in text for char in " []'\""):
        return "'%s'" % text.replace("'", "'\\''")
    return text


def _decision_line(feature: Optional[Dict[str, Any]]) -> str:
    if not feature:
        return ""
    return str(feature.get("when_to_use") or feature.get("when_not_to_use") or "").strip()


def _one_line(text: str) -> str:
    text = " ".join(str(text or "").split())
    if ". " in text:
        return text.split(". ")[0].rstrip(".") + "."
    return text
