"""Transactional, round-trip editor for ``splunk_config.yml``."""

from __future__ import annotations

import copy
import difflib
import fcntl
import hashlib
import io
import json
import os
import re
import shlex
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


class ConfigEditError(RuntimeError):
    """A safe, operator-facing config edit error."""


_SEGMENT = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<selector>[^\]]+)\])?$"
)
_FILTER_SPLIT = re.compile(r"\s*,\s*(?=[A-Za-z_][A-Za-z0-9_]*=)")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET = re.compile(r"(?:password|secret|token|private_key)$", re.IGNORECASE)
_IDENTITIES: Dict[Tuple[str, ...], Tuple[str, ...]] = {
    ("splunk_hosts",): ("name", "iter.prefix"),
    ("splunk_idxclusters",): ("idxc_name",),
    ("splunk_shclusters",): ("shc_name",),
    ("splunk_environments",): ("splunk_env_name",),
    ("splunk_app_deployment", "apps"): ("app_id", "name"),
    ("virtualbox", "synced_folder"): ("target",),
    ("splunk_hosts", "virtualbox", "synced_folder"): ("target",),
    ("splunk_app_deployment", "apps", "content_pack_apps"): ("app_id", "name"),
}
# One-of groups for spa config explain. Host names match validate_host_identifier.
_ONE_OF: Dict[Tuple[str, ...], Tuple[str, ...]] = {
    ("splunk_hosts",): ("name", "list", "iter"),
    ("splunk_idxclusters",): ("idxc_name",),
    ("splunk_shclusters",): ("shc_name",),
    ("splunk_environments",): ("splunk_env_name",),
}
_APP_IDENTITY_LISTS = {
    ("splunk_app_deployment", "apps"),
    ("splunk_app_deployment", "apps", "content_pack_apps"),
}
_PROVIDER_ROOTS = ("terraform", "virtualbox", "aws", "external", "ccm")
_TOPOLOGY_ROOTS = ("splunk_hosts", "splunk_idxclusters", "splunk_shclusters", "splunk_environments")
_HEADER_FIELDS = (
    "intent",
    "requirements",
    "sva",
    "placement",
    "license",
    "installer",
    "os",
    "aws",
    "deploy",
)
# Marker shapes only. A PEM body is covered by the BEGIN marker.
_HEADER_SECRET = re.compile(
    r"-----BEGIN|<license|password:"
    r"|eyJ[^\s.]*\.[^\s.]+\.[^\s.]+"
    r"|AKIA|ghp_|sk_live_|sk_test_"
)
_MISSING = object()


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.allow_duplicate_keys = False
    yaml.default_flow_style = False
    yaml.width = 4096
    return yaml


def _read(path: Path) -> Tuple[bytes, MutableMapping[str, Any]]:
    if path.is_symlink():
        raise ConfigEditError("Refusing to edit a symlink config target: %s" % path)
    if not path.is_file():
        raise ConfigEditError("Config file not found: %s; run spa init first" % path)
    raw = path.read_bytes()
    try:
        data = _yaml().load(raw.decode("utf-8"))
    except Exception as exc:
        raise ConfigEditError("Cannot parse splunk_config.yml: %s" % exc) from exc
    if not isinstance(data, MutableMapping):
        raise ConfigEditError("splunk_config.yml must contain a mapping")
    return raw, data


def _revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _stamp_path(config_path: Path) -> Path:
    return Path(config_path).with_name(".%s.spa-stamp" % Path(config_path).name)


def _write_stamp(config_path: Path, sha256: str, command: str) -> None:
    payload = {
        "sha256": sha256,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": command,
    }
    _stamp_path(config_path).write_text(json.dumps(payload) + "\n", encoding="utf-8")


@contextmanager
def _locked(path: Path):
    lock_path = path.with_name(".%s.lock" % path.name)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _parse_filters(selector: str) -> List[Tuple[str, str]]:
    pairs = _FILTER_SPLIT.split(selector)
    filters: List[Tuple[str, str]] = []
    for pair in pairs:
        if "=" not in pair:
            raise ConfigEditError("Invalid config path selector %r" % selector)
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigEditError("Invalid config path selector %r" % selector)
        filters.append((key, value.strip()))
    return filters


def _segments(path: str) -> List[Tuple[str, Optional[str], Optional[str], Tuple[Tuple[str, str], ...]]]:
    if not path or path.startswith(".") or path.endswith("."):
        raise ConfigEditError("Invalid config path: %r" % path)
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    for char in path:
        if char == "." and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
    parts.append("".join(current))
    parsed = []
    for part in parts:
        match = _SEGMENT.fullmatch(part)
        if not match:
            if "[]" in part:
                raise ConfigEditError("A mutation path needs an identity selector, not []: %s" % path)
            raise ConfigEditError("Invalid config path segment %r" % part)
        selector = match.group("selector")
        if selector:
            filters = _parse_filters(selector)
            key, value = filters[0]
            extras = tuple(filters[1:])
            parsed.append((match.group("name"), key, value, extras))
        else:
            parsed.append((match.group("name"), None, None, ()))
    return parsed


def _normalized_path(path: str) -> str:
    return ".".join("%s[]" % name if key else name for name, key, _, _extras in _segments(path))


def _nested_get(item: Mapping[str, Any], path: str) -> Any:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _roles_match(actual: Any, wanted: str) -> bool:
    actual_list = [str(role) for role in (actual or [])]
    needed = [part.strip() for part in str(wanted).split(",") if part.strip()]
    if len(needed) == 1:
        return needed[0] in actual_list
    return sorted(actual_list) == sorted(needed)


def _item_matches_filters(
    item: Mapping[str, Any], filters: Sequence[Tuple[str, str]]
) -> bool:
    for key, value in filters:
        if key == "target_roles":
            if not _roles_match(item.get("target_roles"), value):
                return False
            continue
        if str(_nested_get(item, key)) != value:
            return False
    return True


def _select(
    items: Any,
    key: str,
    value: str,
    path: str,
    extras: Sequence[Tuple[str, str]] = (),
) -> MutableMapping[str, Any]:
    if not isinstance(items, list):
        raise ConfigEditError("%s is not a list" % path)
    filters = [(key, value), *list(extras)]
    matches = [
        item
        for item in items
        if isinstance(item, MutableMapping) and _item_matches_filters(item, filters)
    ]
    if not matches:
        raise ConfigEditError("%s matched no items" % path)
    if len(matches) > 1:
        raise ConfigEditError("%s matched multiple items" % path)
    return matches[0]


def _parent(
    document: MutableMapping[str, Any],
    path: str,
    *,
    create: bool,
) -> Tuple[MutableMapping[str, Any], str]:
    parsed = _segments(path)
    current: Any = document
    walked: List[str] = []
    for name, selector_key, selector_value, extras in parsed[:-1]:
        walked.append(name)
        if not isinstance(current, MutableMapping):
            raise ConfigEditError("%s is not a mapping" % ".".join(walked[:-1]))
        if name not in current or current.get(name) is None:
            if selector_key or not create:
                raise ConfigEditError("%s does not exist" % ".".join(walked))
            current[name] = CommentedMap()
        current = current[name]
        if selector_key:
            current = _select(
                current,
                selector_key,
                str(selector_value),
                ".".join(walked),
                extras,
            )
    leaf, selector_key, selector_value, extras = parsed[-1]
    if selector_key:
        if not isinstance(current, MutableMapping) or leaf not in current:
            raise ConfigEditError("%s does not exist" % path)
        selected = _select(
            current[leaf], selector_key, str(selector_value), path, extras
        )
        return selected, ""
    if not isinstance(current, MutableMapping):
        raise ConfigEditError("Parent of %s is not a mapping" % path)
    return current, leaf


def _lookup_leaf(document: Mapping[str, Any], path: str) -> Tuple[bool, Any]:
    """Return (found, value) for PATH. found is False when the leaf is absent."""
    try:
        parent, leaf = _parent(document, path, create=False)  # type: ignore[arg-type]
    except ConfigEditError:
        return False, None
    if not leaf:
        return True, parent
    if leaf not in parent:
        return False, None
    return True, parent[leaf]


def _schema_detail(path: str) -> Optional[Dict[str, Any]]:
    from spa.catalog import app_entry_field_detail, schema_key_details

    normalized = _normalized_path(path)
    app_prefix = "splunk_app_deployment.apps[]."
    if normalized.startswith(app_prefix):
        detail = app_entry_field_detail(normalized[len(app_prefix):])
        if detail:
            return detail
    details = schema_key_details()
    detail = details.get(normalized)
    if detail:
        return detail
    if normalized.endswith("[]") and any(
        key.startswith(normalized + ".") for key in details
    ):
        return None
    # Custom/provider models deliberately allow additional keys.
    if normalized.startswith(("custom.", "terraform.", "virtualbox.", "aws.")) or ".custom." in normalized:
        return None
    raise ConfigEditError("Unknown schema path: %s" % path)


def _enum_scalar_json_type(allowed: Sequence[Any]) -> Optional[str]:
    """Integer/number/bool Literal enums use JSON, like non-enum scalars."""
    values = list(allowed)
    if not values:
        return None
    if all(isinstance(item, bool) for item in values):
        return "boolean"
    if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
        return "integer"
    if all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in values
    ):
        return "number"
    return None


def _parse_value(path: str, raw: str) -> Any:
    detail = _schema_detail(path)
    type_name = str((detail or {}).get("type") or "string")
    if type_name == "enum":
        json_type = _enum_scalar_json_type((detail or {}).get("allowed") or [])
        if json_type:
            type_name = json_type
    structured = type_name.startswith(("list", "map", "object"))
    scalar_json = type_name in {"boolean", "integer", "number", "null"}
    if structured or scalar_json:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigEditError("%s requires strict JSON: %s" % (path, exc.msg)) from exc
        expected = (
            list if type_name.startswith("list")
            else dict if type_name.startswith(("map", "object"))
            else bool if type_name == "boolean"
            else int if type_name == "integer"
            else (int, float) if type_name == "number"
            else type(None)
        )
        if not isinstance(value, expected) or (type_name == "integer" and isinstance(value, bool)):
            raise ConfigEditError("%s expects %s" % (path, type_name))
        return value
    parts = [part.strip() for part in type_name.split("|")]
    if any(part.startswith(("list", "map", "object")) for part in parts):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return _unwrap_json_string(raw)
        if isinstance(loaded, list) and any(part.startswith("list") for part in parts):
            return loaded
        if isinstance(loaded, dict) and any(part.startswith(("map", "object")) for part in parts):
            return loaded
        if isinstance(loaded, str):
            return loaded
        return raw
    return _unwrap_json_string(raw)


def _unwrap_json_string(raw: str) -> str:
    """Unwrap one JSON string layer. `"eu-central-1"` becomes eu-central-1."""
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(loaded, str):
        return loaded
    return raw


def _is_secret(path: str) -> bool:
    return bool(_SECRET.search(path.rsplit(".", 1)[-1]))


def _redacted_value(path: str, value: Any) -> Any:
    if _is_secret(path):
        return "<redacted>"
    safe = copy.deepcopy(value)
    _redact_document(safe, path)
    return safe


def _cleanup_empty(document: MutableMapping[str, Any], path: str) -> None:
    parsed = _segments(path)
    parents: List[Tuple[MutableMapping[str, Any], str]] = []
    current: Any = document
    for name, selector_key, selector_value, extras in parsed[:-1]:
        if not isinstance(current, MutableMapping) or name not in current:
            return
        if selector_key:
            current = _select(
                current[name], selector_key, str(selector_value), path, extras
            )
        else:
            parents.append((current, name))
            current = current[name]
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, Mapping) and not child:
            del parent[key]
        else:
            break


def _identity_for(path: Sequence[str], item: Mapping[str, Any]) -> Optional[Tuple[str, Any]]:
    compact = tuple(part for part in path if part != "[]")
    candidates = _IDENTITIES.get(tuple(path)) or _IDENTITIES.get(compact)
    if not candidates:
        return None
    for candidate in candidates:
        value = _nested_get(item, candidate)
        if value is not None:
            return candidate, value
    return None


def _typed_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return (
            left.keys() == right.keys()
            and all(_typed_equal(left[key], right[key]) for key in left)
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, (Mapping, list)) or isinstance(right, (Mapping, list)):
        return False
    if type(left) is not type(right):
        return False
    return left == right


def _merge(
    current: Any,
    incoming: Any,
    path: Tuple[str, ...],
    warnings: List[str],
) -> Any:
    if incoming is None:
        warnings.append("%s: null skipped; use spa config unset to remove it" % ".".join(path))
        return current
    if isinstance(current, MutableMapping) and isinstance(incoming, Mapping):
        for key, value in incoming.items():
            if key in current:
                current[key] = _merge(current[key], value, path + (str(key),), warnings)
            elif value is None:
                warnings.append("%s: null skipped; use spa config unset to remove it" % ".".join(path + (str(key),)))
            else:
                current[key] = copy.deepcopy(value)
        return current
    if isinstance(current, list) and isinstance(incoming, list):
        compact_path = tuple(part for part in path if part != "[]")
        known_identity = _IDENTITIES.get(path) or _IDENTITIES.get(compact_path)
        if known_identity:
            for item in incoming:
                if not isinstance(item, Mapping):
                    raise ConfigEditError("%s items must be mappings" % ".".join(path))
                identity = _identity_for(path, item)
                if identity is None:
                    raise ConfigEditError("%s item has no identity key" % ".".join(path))
                key, value = identity
                match = next(
                    (
                        existing
                        for existing in current
                        if isinstance(existing, MutableMapping)
                        and str(_nested_get(existing, key)) == str(value)
                    ),
                    None,
                )
                if match is None:
                    added = copy.deepcopy(item)
                    if compact_path == ("splunk_hosts",):
                        _promote_host_identity(added)
                    current.append(added)
                else:
                    _merge(match, item, path + ("[]",), warnings)
            return current
        for item in incoming:
            if not any(_typed_equal(item, existing) for existing in current):
                current.append(copy.deepcopy(item))
        return current
    promoted = _promote_scalar_list(current, incoming)
    if promoted is not None:
        return promoted
    return copy.deepcopy(incoming)


def _scalar_list(value: Any) -> bool:
    return isinstance(value, list) and all(not isinstance(item, (Mapping, list)) for item in value)


def _promote_scalar_list(current: Any, incoming: Any) -> Optional[List[Any]]:
    """Keep a scalar filename when a fragment adds a list, and the reverse."""
    if isinstance(current, str) and _scalar_list(incoming):
        base: List[Any] = [current]
        extra = incoming
    elif isinstance(incoming, str) and _scalar_list(current):
        base = list(current)
        extra = [incoming]
    else:
        return None
    for item in extra:
        if not any(_typed_equal(item, existing) for existing in base):
            base.append(copy.deepcopy(item))
    return base


def _ordered(document: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    from spa.catalog import order_config_roots

    return order_config_roots(document)


def _dump_text(document: Any) -> str:
    from spa.catalog import format_config_text

    stream = io.StringIO()
    _yaml().dump(document, stream)
    return format_config_text(stream.getvalue())


def _dump(document: MutableMapping[str, Any], path: Path) -> None:
    path.write_text(_dump_text(document), encoding="utf-8")


def _redacted_diff(before: Any, after: Any) -> str:
    safe_before = copy.deepcopy(before)
    safe_after = copy.deepcopy(after)
    _redact_document(safe_before)
    _redact_document(safe_after)
    return "".join(
        difflib.unified_diff(
            _dump_text(safe_before).splitlines(keepends=True),
            _dump_text(safe_after).splitlines(keepends=True),
            fromfile="splunk_config.yml",
            tofile="splunk_config.yml",
        )
    )


def _validate(path: Path, spa_home: Path) -> None:
    import sys

    plugin = spa_home / "ansible" / "plugins" / "inventory"
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    try:
        from schema import validate_config_file  # type: ignore

        validate_config_file(str(path))
    except Exception as exc:
        raise ConfigEditError("Config validation failed: %s" % exc) from exc


def _plan_dependencies(document: MutableMapping[str, Any], spa_home: Path) -> Dict[str, Any]:
    import sys

    plugin = spa_home / "ansible" / "plugins" / "inventory"
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    from schema import plan_config_dependencies  # type: ignore

    return plan_config_dependencies(document)


def _apply_resolution_value(
    document: MutableMapping[str, Any], path: str, raw: str
) -> None:
    if _is_secret(path):
        raise ConfigEditError(
            "Secret paths require --from-env; plaintext values are not accepted"
        )
    parsed = _parse_value(path, raw)
    _validate_fragment_secrets(parsed, path)
    parent, leaf = _parent(document, path, create=True)
    if not leaf:
        raise ConfigEditError("A resolution must name a field path")
    parent[leaf] = copy.deepcopy(parsed)


def _leaf_operations(before: Any, after: Any, prefix: str = "") -> List[Dict[str, Any]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        operations: List[Dict[str, Any]] = []
        keys = list(before)
        keys.extend(key for key in after if key not in before)
        for key in keys:
            path = "%s.%s" % (prefix, key) if prefix else str(key)
            if key not in after:
                operations.append({"op": "unset", "path": path})
            elif key not in before:
                if isinstance(after[key], Mapping):
                    operations.extend(_leaf_operations({}, after[key], path))
                else:
                    operations.append({"op": "set", "path": path, "value": _redacted_value(path, after[key])})
            else:
                operations.extend(_leaf_operations(before[key], after[key], path))
        return operations
    if isinstance(before, list) and isinstance(after, list) and prefix:
        names = tuple(name for name, _, _, _ in _segments(prefix))
        identities = _IDENTITIES.get(names)
        if identities:
            operations = []
            matched_before = set()
            for item in after:
                if not isinstance(item, Mapping):
                    continue
                identity = _identity_for(names, item)
                if identity is None:
                    continue
                key, value = identity
                match_index = next(
                    (
                        index
                        for index, existing in enumerate(before)
                        if index not in matched_before
                        and isinstance(existing, Mapping)
                        and str(_nested_get(existing, key)) == str(value)
                    ),
                    None,
                )
                selected_path = "%s[%s=%s]" % (prefix, key, value)
                if match_index is None:
                    operations.append(
                        {
                            "op": "set",
                            "path": selected_path,
                            "value": _redacted_value(selected_path, item),
                        }
                    )
                else:
                    matched_before.add(match_index)
                    operations.extend(
                        _leaf_operations(
                            before[match_index], item, selected_path
                        )
                    )
            for index, item in enumerate(before):
                if index in matched_before or not isinstance(item, Mapping):
                    continue
                identity = _identity_for(names, item)
                if identity is not None:
                    key, value = identity
                    operations.append(
                        {
                            "op": "unset",
                            "path": "%s[%s=%s]" % (prefix, key, value),
                        }
                    )
            if operations:
                return operations
    if before != after:
        return [{"op": "set", "path": prefix, "value": _redacted_value(prefix, after)}]
    return []


def config_mutate(
    config_path: Path,
    spa_home: Path,
    mutate: Callable[[MutableMapping[str, Any], List[str]], None],
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
    command: str = "config",
) -> Dict[str, Any]:
    """Run one config-edit transaction with a caller-supplied in-memory mutate."""
    return _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command=command,
    )


def _transact(
    config_path: Path,
    spa_home: Path,
    mutate: Callable[[MutableMapping[str, Any], List[str]], None],
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
    command: str = "config",
) -> Dict[str, Any]:
    config_path = Path(config_path)
    spa_home = Path(spa_home)
    with _locked(config_path):
        raw, document = _read(config_path)
        before_revision = _revision(raw)
        if expect_revision is not None and expect_revision != before_revision:
            raise ConfigEditError(
                "Config revision conflict: expected %s, current %s"
                % (expect_revision, before_revision)
            )
        before = copy.deepcopy(document)
        warnings: List[Any] = []
        mutate(document, warnings)
        for pair in resolve or []:
            if len(pair) != 2:
                raise ConfigEditError("--resolve needs PATH VALUE")
            _apply_resolution_value(document, str(pair[0]), str(pair[1]))
        if resolve_file:
            resolution = _load_fragment(spa_home, resolve_file, stdin_text)
            _merge(document, resolution, (), warnings)
        dependency = (
            _plan_dependencies(document, spa_home)
            if validate
            else {"ready": True, "requirements": [], "repairs": [], "warnings": []}
        )
        warnings.extend(dependency.get("warnings") or [])
        from spa.next_steps import ITSI_LICENSE_FILE_WARNING, attach_license_file_next

        apps = ((document.get("splunk_app_deployment") or {}).get("apps") or [])
        has_itsi = any(
            isinstance(app, Mapping)
            and str(app.get("state") or "installed") != "absent"
            and (app.get("app_id") == 1841 or str(app.get("premium_app") or "") == "itsi")
            for app in apps
        )
        has_file = bool((document.get("splunk_defaults") or {}).get("splunk_license_file"))
        if has_itsi and not has_file and not any(
            isinstance(item, Mapping) and item.get("id") == ITSI_LICENSE_FILE_WARNING["id"]
            for item in warnings
        ):
            warnings.append(dict(ITSI_LICENSE_FILE_WARNING))

        def finish(payload: Dict[str, Any]) -> Dict[str, Any]:
            attach_license_file_next(payload)
            return payload

        document = _ordered(document)
        operations = _leaf_operations(before, document)
        diff = _redacted_diff(before, document) if operations else ""
        if not dependency["ready"]:
            return finish({
                "changed": False,
                "ready": False,
                "revision_before": before_revision,
                "operations": [],
                "planned_operations": operations,
                "diff": diff,
                "requirements": dependency["requirements"],
                "warnings": warnings,
                "omitted_defaults": [],
                "validation": "pending",
            })
        if not operations:
            return finish({
                "changed": False,
                "ready": True,
                "revision_before": before_revision,
                "operations": [],
                "diff": "",
                "warnings": warnings,
                "omitted_defaults": [],
                "validation": "ok",
                "requirements": [],
            })
        fd, temp_name = tempfile.mkstemp(
            prefix=".%s." % config_path.name,
            suffix=".tmp",
            dir=str(config_path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            _dump(document, temp_path)
            os.chmod(temp_path, stat.S_IMODE(config_path.stat().st_mode))
            if validate:
                _validate(temp_path, spa_home)
            candidate_raw = temp_path.read_bytes()
            result = {
                "changed": True,
                "ready": True,
                "revision_before": before_revision,
                "operations": operations,
                "diff": diff,
                "warnings": warnings,
                "omitted_defaults": [],
                "validation": "ok" if validate else "skipped",
                "requirements": [],
            }
            if not dry_run:
                os.replace(temp_path, config_path)
                result["revision_after"] = _revision(candidate_raw)
                _write_stamp(config_path, result["revision_after"], command)
            return finish(result)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def _header_comment(fields: Mapping[str, str]) -> str:
    unknown = [str(key) for key in fields if key not in _HEADER_FIELDS]
    if unknown:
        raise ConfigEditError("Unknown config header field: %s" % ", ".join(unknown))
    lines = []
    for name in _HEADER_FIELDS:
        if name not in fields:
            continue
        value = fields[name]
        if value is None:
            continue
        if not isinstance(value, str):
            raise ConfigEditError("Config header field %s must be text" % name)
        text = value.strip()
        if not text:
            continue
        if "\n" in text or "\r" in text:
            raise ConfigEditError("Config header field %s cannot contain a line break" % name)
        if _HEADER_SECRET.search(text):
            raise ConfigEditError(
                "Config header field %s cannot contain a secret-shaped value" % name
            )
        lines.append("# %s: %s" % (name, text))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _leading_preamble_end(raw: bytes) -> int:
    """Byte offset of the first line that is not blank, ``---``, or a comment."""
    position = 0
    length = len(raw)
    while position < length:
        newline = raw.find(b"\n", position)
        line_end = length if newline < 0 else newline
        line = raw[position:line_end]
        if line.endswith(b"\r"):
            line = line[:-1]
        stripped = line.strip()
        if stripped and stripped != b"---" and not stripped.startswith(b"#"):
            return position
        if newline < 0:
            return length
        position = newline + 1
    return length


def _replace_bytes(path: Path, raw: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=".%s." % path.name,
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        temp_path.write_bytes(raw)
        os.chmod(temp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def config_header_set(
    config_path: Path,
    fields: Mapping[str, str],
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
) -> Dict[str, Any]:
    """Replace the leading comment. The YAML mapping bytes after it stay unchanged."""
    header = _header_comment(fields)
    config_path = Path(config_path)
    with _locked(config_path):
        raw, _parsed = _read(config_path)
        current = _revision(raw)
        if expect_revision is not None and expect_revision != current:
            raise ConfigEditError(
                "Config revision conflict: expected %s, current %s"
                % (expect_revision, current)
            )
        updated = header.encode("utf-8") + raw[_leading_preamble_end(raw):]
        changed = updated != raw
        if changed and not dry_run:
            _replace_bytes(config_path, updated)
            _write_stamp(config_path, _revision(updated), "config header set")
        return {"changed": changed, "header": header}


def config_set(
    config_path: Path,
    spa_home: Path,
    path: str,
    value: Optional[str] = None,
    *,
    value_file: Optional[str] = None,
    from_env: Optional[str] = None,
    explicit_default: bool = False,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    if sum(item is not None for item in (value, value_file, from_env)) != 1:
        raise ConfigEditError("Provide exactly one of VALUE, --value-file, or --from-env")
    detail = _schema_detail(path)
    if _is_secret(path):
        if from_env is None:
            raise ConfigEditError("Secret paths require --from-env; plaintext values are not accepted")
    elif from_env is not None:
        raise ConfigEditError("--from-env is only valid for a secret path")
    if from_env is not None:
        if not _ENV_NAME.fullmatch(from_env):
            raise ConfigEditError("Invalid environment variable name")
        parsed: Any = "{{ lookup('env', '%s') }}" % from_env
    elif value_file is not None:
        source = Path(value_file)
        if not source.is_file():
            raise ConfigEditError("Value file not found: %s" % source)
        try:
            parsed = _yaml().load(source.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConfigEditError("Cannot parse value file: %s" % exc) from exc
    else:
        parsed = _parse_value(path, str(value))
    _validate_fragment_secrets(parsed, path)
    default = (detail or {}).get("default", _MISSING)
    matches_default = default is not _MISSING and parsed == default and not explicit_default
    nested_omitted: List[Dict[str, Any]] = []
    if not matches_default and isinstance(parsed, Mapping) and not explicit_default:
        parsed = _omit_fragment_defaults(
            parsed,
            parts=tuple(part for part in path.split(".") if part),
            omitted=nested_omitted,
        )
        matches_default = parsed == {} and bool(nested_omitted)
    omitted_defaults: List[Dict[str, Any]] = []

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        if matches_default and nested_omitted:
            warnings.append("%s already has the schema default; use --explicit-default to author it" % path)
            omitted_defaults.extend(nested_omitted)
            return
        if matches_default:
            found, current = _lookup_leaf(document, path)
            if not found or current == default:
                warnings.append("%s already has the schema default; use --explicit-default to author it" % path)
                omitted_defaults.append({"path": path, "value": _redacted_value(path, parsed)})
                return
        parent, leaf = _parent(document, path, create=True)
        if not leaf:
            raise ConfigEditError("Cannot replace a selected item without a field path")
        parent[leaf] = copy.deepcopy(parsed)
        _attach_ami_comment(document, parent, leaf, parsed, warnings)

    result = _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config set",
    )
    if omitted_defaults:
        result["omitted_defaults"] = omitted_defaults
    elif nested_omitted:
        result["omitted_defaults"] = nested_omitted
    return result


def config_migrate(
    config_path: Path,
    spa_home: Path,
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Stamp schema_version to current and apply MIGRATIONS in order. Does not touch config_version."""
    import sys

    plugin = Path(spa_home) / "ansible" / "plugins" / "inventory"
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    from schema import CURRENT_SCHEMA_VERSION, MIGRATIONS  # type: ignore

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        authored = document.get("schema_version")
        if authored is None:
            document["schema_version"] = CURRENT_SCHEMA_VERSION
            return
        if isinstance(authored, bool) or not isinstance(authored, int):
            return
        if authored > CURRENT_SCHEMA_VERSION:
            return
        for src in range(authored, CURRENT_SCHEMA_VERSION):
            step = MIGRATIONS.get((src, src + 1))
            if isinstance(step, Mapping) and step:
                _merge(document, step, (), warnings)
        document["schema_version"] = CURRENT_SCHEMA_VERSION

    return _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config migrate",
    )


_AMI_ID = re.compile(r"^ami-[0-9a-fA-F]+$")


def _region_for_ami(document: Mapping[str, Any], parent: Any) -> Optional[str]:
    if isinstance(parent, Mapping):
        region = parent.get("region")
        if isinstance(region, str) and region.strip():
            return region.strip()
    terraform = document.get("terraform") if isinstance(document, Mapping) else None
    aws = terraform.get("aws") if isinstance(terraform, Mapping) else None
    region = aws.get("region") if isinstance(aws, Mapping) else None
    if isinstance(region, str) and region.strip():
        return region.strip()
    return None


def _set_eol_comment(parent: Any, key: str, comment: Optional[str]) -> None:
    if comment:
        if hasattr(parent, "yaml_add_eol_comment"):
            parent.yaml_add_eol_comment(comment, key=key)
        return
    items = getattr(getattr(parent, "ca", None), "items", None)
    if not items or key not in items or not isinstance(items[key], list):
        return
    if len(items[key]) > 2:
        items[key][2] = None


def _attach_ami_comment(
    document: Mapping[str, Any],
    parent: Any,
    leaf: str,
    value: Any,
    warnings: List[str],
) -> None:
    if leaf != "ami_id" or not isinstance(value, str) or not _AMI_ID.fullmatch(value):
        return
    region = _region_for_ami(document, parent)
    comment = None
    if region:
        from spa.aws import ami_comment_for_config

        comment = ami_comment_for_config(region, value)
    if comment:
        _set_eol_comment(parent, leaf, comment)
        return
    _set_eol_comment(parent, leaf, None)
    if region:
        warnings.append(
            "AMI %s was set in %s without an image comment. "
            "spa provider aws describe-ami --region %s --ami-id %s can identify it."
            % (value, region, region, value)
        )
    else:
        warnings.append(
            "AMI %s was set without an image comment because terraform.aws.region is empty."
            % value
        )


def _commented(value: Any) -> Any:
    if isinstance(value, Mapping):
        mapped = CommentedMap()
        for key, child in value.items():
            mapped[key] = _commented(child)
        return mapped
    if isinstance(value, list):
        sequence = CommentedSeq()
        for child in value:
            sequence.append(_commented(child))
        return sequence
    return copy.deepcopy(value)


def _assign_field(item: MutableMapping[str, Any], field: str, value: Any) -> None:
    if not field or field.startswith(".") or field.endswith(".") or ".." in field:
        raise ConfigEditError("Invalid --from-env field: %s" % field)
    current: MutableMapping[str, Any] = item
    parts = field.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = CommentedMap()
            current[part] = child
        if not isinstance(child, MutableMapping):
            raise ConfigEditError("--from-env field %s is not a mapping" % field)
        current = child
    current[parts[-1]] = value


def _identity_selector(path: str) -> Tuple[Tuple[str, ...], str, str]:
    parsed = _segments(path)
    if not parsed or not parsed[-1][1]:
        raise ConfigEditError("spa config add needs an identity selector: %s" % path)
    names = tuple(name for name, _, _, _ in parsed)
    return names, str(parsed[-1][1]), str(parsed[-1][2])


def _identity_list(document: MutableMapping[str, Any], path: str) -> Tuple[list, str, str]:
    names, key, value = _identity_selector(path)
    if names in _APP_IDENTITY_LISTS:
        raise ConfigEditError("App entries use spa apps add")
    identities = _IDENTITIES.get(names)
    if not identities:
        raise ConfigEditError("spa config add requires an identity list: %s" % path)
    if key not in identities:
        raise ConfigEditError("%s identity must be one of: %s" % (path, ", ".join(identities)))
    current: Any = document
    walked: List[str] = []
    for name, selector_key, selector_value, extras in _segments(path)[:-1]:
        walked.append(name)
        if not isinstance(current, MutableMapping):
            raise ConfigEditError("%s is not a mapping" % ".".join(walked[:-1]))
        if selector_key:
            if name not in current:
                raise ConfigEditError("%s does not exist" % ".".join(walked))
            current = _select(
                current[name],
                selector_key,
                str(selector_value),
                ".".join(walked),
                extras,
            )
        else:
            if name not in current or current.get(name) is None:
                current[name] = CommentedMap()
            current = current[name]
            if not isinstance(current, MutableMapping):
                raise ConfigEditError("%s is not a mapping" % ".".join(walked))
    list_name = _segments(path)[-1][0]
    if not isinstance(current, MutableMapping):
        raise ConfigEditError("Parent of %s is not a mapping" % path)
    if list_name not in current or current.get(list_name) is None:
        current[list_name] = CommentedSeq()
    items = current[list_name]
    if not isinstance(items, list):
        raise ConfigEditError("%s is not a list" % path)
    return items, key, value


def _promote_host_identity(item: MutableMapping[str, Any]) -> None:
    """Write name, list, or iter before the other fields on a host entry."""
    for key in ("name", "list", "iter"):
        if key in item and hasattr(item, "move_to_end"):
            item.move_to_end(key, last=False)
            return


def _inject_identity(item: MutableMapping[str, Any], key: str, value: str) -> None:
    current: MutableMapping[str, Any] = item
    parts = key.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = CommentedMap()
            current[part] = child
        if not isinstance(child, MutableMapping):
            raise ConfigEditError("Identity parent %s is not a mapping" % key)
        current = child
    existing = current.get(parts[-1])
    if existing is not None and str(existing) != value:
        raise ConfigEditError(
            "Selector %s=%s does not match the object value %s" % (key, value, existing)
        )
    current[parts[-1]] = value
    if parts[0] in ("name", "list", "iter"):
        _promote_host_identity(item)


def _load_add_object(value: Optional[str], value_file: Optional[str]) -> MutableMapping[str, Any]:
    if (value is None) == (value_file is None):
        raise ConfigEditError("Provide exactly one of JSON_OBJECT or --value-file")
    if value_file is not None:
        source = Path(value_file)
        if not source.is_file():
            raise ConfigEditError("Value file not found: %s" % source)
        try:
            parsed = _yaml().load(source.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConfigEditError("Cannot parse value file: %s" % exc) from exc
    else:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise ConfigEditError("JSON_OBJECT requires strict JSON: %s" % exc.msg) from exc
    if not isinstance(parsed, Mapping):
        raise ConfigEditError("spa config add requires a JSON object")
    return _commented(parsed)


def _apply_add_secrets(
    item: MutableMapping[str, Any],
    from_env: Optional[Sequence[Sequence[str]]],
) -> None:
    for pair in from_env or []:
        if len(pair) != 2:
            raise ConfigEditError("--from-env needs FIELD NAME")
        field, name = str(pair[0]), str(pair[1])
        if not _is_secret(field):
            raise ConfigEditError("--from-env is only valid for a secret field: %s" % field)
        if not _ENV_NAME.fullmatch(name):
            raise ConfigEditError("Invalid environment variable name")
        _assign_field(item, field, "{{ lookup('env', '%s') }}" % name)


def config_add(
    config_path: Path,
    spa_home: Path,
    path: str,
    value: Optional[str] = None,
    *,
    value_file: Optional[str] = None,
    from_env: Optional[Sequence[Sequence[str]]] = None,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one new non-app identity-list entry. The selector supplies its identity."""
    names, key, _identity = _identity_selector(path)
    if names in _APP_IDENTITY_LISTS:
        raise ConfigEditError("App entries use spa apps add")
    identities = _IDENTITIES.get(names)
    if not identities:
        raise ConfigEditError("spa config add requires an identity list: %s" % path)
    if key not in identities:
        raise ConfigEditError("%s identity must be one of: %s" % (path, ", ".join(identities)))
    item = _load_add_object(value, value_file)

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        del warnings
        items, key, identity = _identity_list(document, path)
        _inject_identity(item, key, identity)
        _apply_add_secrets(item, from_env)
        _validate_fragment_secrets(item, path)
        for existing in items:
            if isinstance(existing, Mapping) and str(_nested_get(existing, key)) == identity:
                raise ConfigEditError("%s already exists" % path)
        items.append(item)

    return _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config add",
    )


def config_unset(
    config_path: Path,
    spa_home: Path,
    paths: str | Sequence[str],
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    requested = [paths] if isinstance(paths, str) else list(paths)
    for path in requested:
        _schema_detail(path)

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        for path in requested:
            parsed = _segments(path)
            if parsed[-1][1]:
                current: Any = document
                for name, selector_key, selector_value, extras in parsed[:-1]:
                    if not isinstance(current, MutableMapping) or name not in current:
                        raise ConfigEditError("%s does not exist" % path)
                    current = current[name]
                    if selector_key:
                        current = _select(
                            current, selector_key, str(selector_value), path, extras
                        )
                name, selector_key, selector_value, extras = parsed[-1]
                if not isinstance(current, MutableMapping) or name not in current:
                    raise ConfigEditError("%s does not exist" % path)
                selected = _select(
                    current[name],
                    str(selector_key),
                    str(selector_value),
                    path,
                    extras,
                )
                current[name].remove(selected)
                continue
            parent, leaf = _parent(document, path, create=False)
            if leaf not in parent:
                raise ConfigEditError("%s does not exist" % path)
            del parent[leaf]
            _cleanup_empty(document, path)

    return _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config unset",
    )


_HOST_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_AFFIX_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ROLES_NEEDING_IDXC = frozenset({"cluster_manager", "indexer"})
_ROLES_NEEDING_SHC = frozenset({"deployer", "search_head"})
_ROLES_WITH_SITE = frozenset({"indexer", "search_head", "cluster_manager"})


def _host_names(host: Mapping[str, Any]) -> List[str]:
    if host.get("name"):
        return [str(host["name"])]
    listed = host.get("list")
    if listed:
        return [str(item) for item in listed]
    iteration = host.get("iter") or {}
    numbers = str(iteration.get("numbers") or "")
    if ".." not in numbers:
        return []
    start_text, end_text = numbers.split("..", 1)
    try:
        start, end = int(start_text), int(end_text)
    except ValueError:
        return []
    prefix = str(iteration.get("prefix") or "")
    postfix = str(iteration.get("postfix") or "")
    return ["%s%s%s" % (prefix, number, postfix) for number in range(start, end + 1)]


def _host_roles(host: Mapping[str, Any]) -> List[str]:
    return [str(role) for role in (host.get("roles") or [])]


def _find_host(hosts: Sequence[Any], identity: str) -> Optional[MutableMapping[str, Any]]:
    matches = [
        host
        for host in hosts
        if isinstance(host, MutableMapping) and identity in _host_names(host)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ConfigEditError("host %s matched multiple entries" % identity)
    host = matches[0]
    names = _host_names(host)
    if host.get("iter") and len(names) > 1:
        raise ConfigEditError(
            "spa config move cannot target %s because that identity is generated by an iter range"
            % identity
        )
    return host


def _require_host_name(value: str, label: str) -> str:
    if not value or not _HOST_NAME_RE.match(value):
        raise ConfigEditError("%s must be a legal hostname identity" % label)
    return value


def config_move_role(
    config_path: Path,
    spa_home: Path,
    role: str,
    *,
    from_host: Optional[str] = None,
    to_host: Optional[str] = None,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    from spa.hosts import allowed_role_names

    allowed = allowed_role_names()
    if role not in allowed:
        raise ConfigEditError("role must be one of: %s" % ", ".join(allowed))
    source_name = _require_host_name(from_host or "", "--from")
    dest_name = _require_host_name(to_host or "", "--to")

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        del warnings
        hosts = document.setdefault("splunk_hosts", [])
        source = _find_host(hosts, source_name)
        if source is None:
            raise ConfigEditError("host %s does not exist" % source_name)
        if role not in _host_roles(source):
            raise ConfigEditError("host %s does not have role %s" % (source_name, role))
        extra: Dict[str, Any] = {}
        if role in _ROLES_NEEDING_IDXC and source.get("idxcluster"):
            extra["idxcluster"] = source["idxcluster"]
        if role in _ROLES_NEEDING_SHC and source.get("shcluster"):
            extra["shcluster"] = source["shcluster"]
        if role in _ROLES_WITH_SITE and source.get("site"):
            extra["site"] = source["site"]
        dest = _find_host(hosts, dest_name)
        source_roles = [item for item in _host_roles(source) if item != role]
        if source_roles:
            source["roles"] = source_roles
        else:
            hosts.remove(source)
        if dest is None:
            hosts.append({"name": dest_name, "roles": [role], **extra})
            return
        if role in _host_roles(dest):
            raise ConfigEditError("host %s already has role %s" % (dest_name, role))
        dest.setdefault("roles", []).append(role)
        for key, value in extra.items():
            if key not in dest:
                dest[key] = value

    return _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config move role",
    )


def _prefix_identity(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value
    return prefix + value


def _postfix_identity(value: str, postfix: str) -> str:
    if value.endswith(postfix):
        return value
    return value + postfix


def _affix_identity(
    value: str, *, prefix: Optional[str] = None, postfix: Optional[str] = None
) -> str:
    out = value
    if prefix:
        out = _prefix_identity(out, prefix)
    if postfix:
        out = _postfix_identity(out, postfix)
    return out


def _require_affix(value: str, label: str) -> str:
    if not value or not _AFFIX_RE.match(value):
        raise ConfigEditError("%s must be a hostname affix" % label)
    return value


def _rewrite_host_lists(node: Any, mapping: Mapping[str, str]) -> None:
    if isinstance(node, MutableMapping):
        for key, value in list(node.items()):
            if key in {"hosts_whitelist", "hosts_blacklist"} and isinstance(value, list):
                node[key] = [mapping.get(str(item), item) for item in value]
            else:
                _rewrite_host_lists(value, mapping)
    elif isinstance(node, list):
        for item in node:
            _rewrite_host_lists(item, mapping)


def config_move_host(
    config_path: Path,
    spa_home: Path,
    *,
    old_name: Optional[str] = None,
    new_name: Optional[str] = None,
    prefix: Optional[str] = None,
    postfix: Optional[str] = None,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    if prefix or postfix:
        if old_name or new_name:
            raise ConfigEditError(
                "spa config move host --prefix/--postfix cannot be combined with OLD or --to"
            )
        if prefix:
            _require_host_name(prefix, "--prefix")
        if postfix:
            _require_affix(postfix, "--postfix")
    else:
        if not old_name or not new_name:
            raise ConfigEditError(
                "spa config move host needs OLD --to NEW, or --prefix PREFIX, or --postfix POSTFIX"
            )
        _require_host_name(old_name, "OLD")
        _require_host_name(new_name, "--to")

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        del warnings
        hosts = document.setdefault("splunk_hosts", [])
        mapping: Dict[str, str] = {}
        if prefix or postfix:
            for host in hosts:
                if not isinstance(host, MutableMapping):
                    continue
                if host.get("name"):
                    before = str(host["name"])
                    after = _affix_identity(before, prefix=prefix, postfix=postfix)
                    host["name"] = after
                    mapping[before] = after
                iteration = host.get("iter")
                if isinstance(iteration, MutableMapping):
                    before_names = _host_names(host)
                    if prefix and iteration.get("prefix") is not None:
                        iteration["prefix"] = _affix_identity(
                            str(iteration.get("prefix") or ""),
                            prefix=prefix,
                        )
                    if postfix:
                        iteration["postfix"] = _affix_identity(
                            str(iteration.get("postfix") or ""),
                            postfix=postfix,
                        )
                    for before, after in zip(before_names, _host_names(host)):
                        mapping[before] = after
                listed = host.get("list")
                if isinstance(listed, list):
                    rewritten = []
                    for item in listed:
                        after = _affix_identity(str(item), prefix=prefix, postfix=postfix)
                        mapping[str(item)] = after
                        rewritten.append(after)
                    host["list"] = rewritten
        else:
            dest_taken = any(
                isinstance(host, Mapping) and new_name in _host_names(host) for host in hosts
            )
            if dest_taken:
                raise ConfigEditError("host %s already exists" % new_name)
            source = _find_host(hosts, old_name or "")
            if source is None:
                raise ConfigEditError("host %s does not exist" % old_name)
            before_names = _host_names(source)
            if source.get("name"):
                source["name"] = new_name
            elif source.get("list"):
                source["list"] = [
                    new_name if item == old_name else item for item in source["list"]
                ]
            elif source.get("iter"):
                source.pop("iter", None)
                source["name"] = new_name
            after_names = _host_names(source)
            if len(before_names) == 1 and len(after_names) == 1:
                mapping[before_names[0]] = after_names[0]
        _rewrite_host_lists(document, mapping)

    return _transact(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config move host",
    )


def _safe_read_value(document: MutableMapping[str, Any], path: str) -> Any:
    parent, leaf = _parent(document, path, create=False)
    if not leaf:
        return parent
    if leaf not in parent:
        raise ConfigEditError("%s is unset" % path)
    return parent[leaf]


def _identity_path(path: str) -> Optional[str]:
    parsed = _segments(path)
    last_selector = None
    for index, (_name, key, _value, _extras) in enumerate(parsed):
        if key:
            last_selector = index
    if last_selector is None:
        return None
    parts = []
    for name, key, value, extras in parsed[: last_selector + 1]:
        if key:
            filters = [(key, value), *list(extras)]
            rendered = ",".join("%s=%s" % (item_key, item_value) for item_key, item_value in filters)
            parts.append("%s[%s]" % (name, rendered))
        else:
            parts.append(name)
    return ".".join(parts)


def _selector_miss_reason(exc: ConfigEditError) -> str:
    message = str(exc)
    if "matched multiple items" in message:
        return "matched multiple items"
    return "matched no items"


def _outline(document: Mapping[str, Any], revision: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"revision": revision, "top_level_keys": list(document)}
    identities: Dict[str, Any] = {}
    for root, candidates in (
        ("splunk_hosts", ("name", "iter.prefix")),
        ("splunk_idxclusters", ("idxc_name",)),
        ("splunk_shclusters", ("shc_name",)),
        ("splunk_app_deployment.apps", ("app_id", "name")),
    ):
        current: Any = document
        for part in root.split("."):
            current = current.get(part) if isinstance(current, Mapping) else None
        rows = []
        for item in current or []:
            if not isinstance(item, Mapping):
                continue
            row = {}
            for candidate in candidates:
                value = _nested_get(item, candidate)
                if value is not None:
                    row[candidate] = value
                    break
            for field in ("roles", "target_roles", "premium_app"):
                if field in item:
                    row[field] = copy.deepcopy(item[field])
            rows.append(row)
        if rows:
            identities[root] = rows
    result["identities"] = identities
    return result


def config_get(
    config_path: Path,
    spa_home: Path,
    path: Optional[str] = None,
    *,
    effective: bool = False,
    full: bool = False,
) -> Dict[str, Any]:
    raw, document = _read(Path(config_path))
    revision = _revision(raw)
    if path is None:
        if full:
            redacted = copy.deepcopy(document)
            _redact_document(redacted)
            return {"revision": revision, "authored": redacted}
        return _outline(document, revision)
    detail = _schema_detail(path)
    identity = _identity_path(path)
    if identity:
        try:
            _safe_read_value(document, identity)
        except ConfigEditError as exc:
            missing = "not set" if _is_secret(path) else None
            return {
                "revision": revision,
                "path": path,
                "found": False,
                "reason": _selector_miss_reason(exc),
                "source": "unset",
                "authored": missing if _is_secret(path) else None,
                "effective": missing if _is_secret(path) else None,
            }
    if _is_secret(path):
        try:
            _safe_read_value(document, path)
            state = "set"
        except ConfigEditError:
            state = "not set"
        return {
            "revision": revision,
            "path": path,
            "found": state == "set",
            "source": "explicit" if state == "set" else "unset",
            "authored": state,
            "effective": state,
        }
    try:
        value = copy.deepcopy(_safe_read_value(document, path))
        return {
            "revision": revision,
            "path": path,
            "found": True,
            "source": "explicit",
            "authored": value,
            "effective": value,
        }
    except ConfigEditError:
        payload = {
            "revision": revision,
            "path": path,
            "found": identity is not None,
            "source": "unset",
            "authored": None,
            "effective": None,
        }
        if effective and detail and "default" in detail:
            payload["source"] = "schema_default"
            payload["effective"] = copy.deepcopy(detail["default"])
        return payload


def config_audit(config_path: Path, *, check_hand_edits: bool = False) -> Dict[str, Any]:
    if not check_hand_edits:
        raise ConfigEditError(
            "spa config audit needs --check-hand-edits.\n"
            "Compare the config SHA-256 to the last spa write stamp: "
            "spa config audit --check-hand-edits"
        )
    raw, _document = _read(Path(config_path))
    current = _revision(raw)
    stamp_file = _stamp_path(config_path)
    if not stamp_file.is_file():
        return {
            "status": "unknown",
            "revision": current,
            "stamped_revision": None,
        }
    try:
        stamp = json.loads(stamp_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "unknown",
            "revision": current,
            "stamped_revision": None,
        }
    if not isinstance(stamp, Mapping):
        return {
            "status": "unknown",
            "revision": current,
            "stamped_revision": None,
        }
    stamped = stamp.get("sha256")
    status = "ok" if stamped == current else "hand_edited"
    result: Dict[str, Any] = {
        "status": status,
        "revision": current,
        "stamped_revision": stamped,
    }
    if stamp.get("timestamp"):
        result["stamped_at"] = stamp.get("timestamp")
    if stamp.get("command"):
        result["stamped_command"] = stamp.get("command")
    return result


def _redact_document(value: Any, path: str = "") -> None:
    if isinstance(value, MutableMapping):
        for key in list(value):
            child_path = "%s.%s" % (path, key) if path else str(key)
            if _is_secret(child_path):
                value[key] = "<redacted>"
            else:
                _redact_document(value[key], child_path)
    elif isinstance(value, list):
        for item in value:
            _redact_document(item, path)


_TEMPLATE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def merge_operand(template: Optional[str], file: Optional[str]) -> str:
    """One spelling: a shipped template name, or --file for a local fragment."""
    if template and file:
        raise ConfigEditError("spa config merge accepts a template name or --file, not both")
    if file:
        return file
    if not template:
        raise ConfigEditError("spa config merge needs TEMPLATE or --file FILE")
    looks_like_file = (
        template == "-"
        or "/" in template
        or "\\" in template
        or template.endswith((".yml", ".yaml", ".json"))
        or not _TEMPLATE_NAME.fullmatch(template)
    )
    if looks_like_file:
        raise ConfigEditError("A local fragment uses spa config merge --file FILE")
    return template


def _fragment_path(spa_home: Path, operand: str) -> Path:
    if "/" in operand or operand.endswith((".yml", ".yaml", ".json")):
        return Path(operand)
    return spa_home / "examples" / "templates" / ("%s.yml" % operand)


def template_merge_command(name: str) -> str:
    return "spa --agent config merge %s --yes" % name


def config_templates(spa_home: Path) -> Dict[str, Any]:
    rows = []
    directory = Path(spa_home) / "examples" / "templates"
    for path in sorted(directory.glob("*.yml")):
        summary = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                summary = line[1:].strip()
                if summary:
                    break
            elif line.strip():
                break
        command = template_merge_command(path.stem)
        rows.append(
            {
                "name": path.stem,
                "summary": summary,
                "command": command,
                "argv": shlex.split(command),
            }
        )
    return {"templates": rows}


def _load_fragment(spa_home: Path, operand: str, stdin_text: Optional[str]) -> Mapping[str, Any]:
    if operand == "-":
        text = stdin_text or ""
        if len(text.encode("utf-8")) > 1024 * 1024:
            raise ConfigEditError("stdin fragment exceeds 1 MiB")
    else:
        path = _fragment_path(spa_home, operand)
        if not path.is_file():
            raise ConfigEditError("Config fragment not found: %s" % path)
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ConfigEditError("Config fragment exceeds 8 MiB: %s" % path)
        text = path.read_text(encoding="utf-8")
    try:
        fragment = _yaml().load(text) or CommentedMap()
    except Exception as exc:
        raise ConfigEditError("Cannot parse config fragment: %s" % exc) from exc
    if not isinstance(fragment, Mapping):
        raise ConfigEditError("Config fragment must be a mapping")
    if "plugin" in fragment and fragment["plugin"] != "splunk-platform-automator":
        raise ConfigEditError("Fragment plugin must be splunk-platform-automator")
    _validate_fragment_secrets(fragment)
    return fragment


def _validate_fragment_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = "%s.%s" % (path, key) if path else str(key)
            if _is_secret(child_path) and child is not None:
                text = str(child)
                if "lookup('env'," not in text and not text.lstrip().startswith("!vault |"):
                    raise ConfigEditError("%s must use an environment lookup or vault reference" % child_path)
            _validate_fragment_secrets(child, child_path)
    elif isinstance(value, list):
        for child in value:
            _validate_fragment_secrets(child, path)


def _plain_scalar(value: Any) -> Any:
    """Drop ruamel quote-style wrappers so dumps do not quote identifier keys."""
    if isinstance(value, str):
        return str.__str__(value)
    return copy.deepcopy(value)


def _plain_fragment(value: Any) -> Any:
    """Drop ruamel comment metadata while retaining YAML 1.2 scalar values."""
    if isinstance(value, Mapping):
        return {
            _plain_scalar(key): _plain_fragment(child) for key, child in value.items()
        }
    if isinstance(value, list):
        return [_plain_fragment(child) for child in value]
    return _plain_scalar(value)


def _fragment_schema_path(parts: Sequence[str]) -> str:
    result = ""
    for part in parts:
        if part == "[]":
            result += "[]"
        else:
            result = "%s.%s" % (result, part) if result else part
    return result


def _omit_fragment_defaults(
    value: Any,
    *,
    parts: Tuple[str, ...] = (),
    omitted: List[Dict[str, Any]],
) -> Any:
    from spa.catalog import app_entry_field_detail, schema_key_details

    details = schema_key_details()
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, child in value.items():
            child_parts = parts + (str(key),)
            path = _fragment_schema_path(child_parts)
            detail = details.get(path)
            app_prefix = "splunk_app_deployment.apps[]."
            if detail is None and path.startswith(app_prefix):
                detail = app_entry_field_detail(path[len(app_prefix):])
            default = (detail or {}).get("default", _MISSING)
            if default is not _MISSING and child == default:
                omitted.append({"path": path, "value": _redacted_value(path, child)})
                continue
            result[key] = _omit_fragment_defaults(
                child, parts=child_parts, omitted=omitted
            )
        return result
    if isinstance(value, list):
        return [
            _omit_fragment_defaults(child, parts=parts + ("[]",), omitted=omitted)
            if isinstance(child, Mapping)
            else _plain_fragment(child)
            for child in value
        ]
    return _plain_fragment(value)


def config_merge(
    config_path: Path,
    spa_home: Path,
    operand: str,
    *,
    stdin_text: Optional[str] = None,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    explicit_default: bool = False,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
) -> Dict[str, Any]:
    if operand == "-" and resolve_file == "-":
        raise ConfigEditError("The primary fragment and --resolve-file cannot both read stdin")
    fragment = _plain_fragment(
        _load_fragment(Path(spa_home), operand, stdin_text)
    )
    omitted_defaults: List[Dict[str, Any]] = []
    if not explicit_default:
        fragment = _omit_fragment_defaults(
            fragment, omitted=omitted_defaults
        )

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        for item in omitted_defaults:
            warnings.append(
                "%s already has the schema default; use --explicit-default to author it"
                % item["path"]
            )
        _merge(document, fragment, (), warnings)

    result = _transact(
        Path(config_path),
        Path(spa_home),
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="config merge",
    )
    result["omitted_defaults"] = omitted_defaults
    return result


def resolve_topology_id(spa_home: Path, topology: str) -> str:
    """Return the example stem for a topology name. Does not write config."""
    from spa.init import resolve_example_pair

    if topology.startswith("topology."):
        from spa.catalog import load_features, resolve_feature
        from spa.usage import unknown_topology

        feature = resolve_feature(load_features(Path(spa_home)), topology)
        if not feature or feature.get("kind") != "topology" or not feature.get("template"):
            raise ConfigEditError(unknown_topology(topology))
        topology = str(feature["template"])
    topology_id, _provider_id = resolve_example_pair(Path(spa_home), topology, None)
    return topology_id


def config_topology(
    config_path: Path,
    spa_home: Path,
    topology: str,
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    from spa.init import _load_yaml_mapping

    topology_id = resolve_topology_id(spa_home, topology)
    example = _load_yaml_mapping(Path(spa_home) / "examples" / "topologies" / ("%s.yml" % topology_id))

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        for key in _TOPOLOGY_ROOTS:
            if key in example and example[key] is not None:
                document[key] = copy.deepcopy(example[key])
            elif key != "splunk_hosts":
                document.pop(key, None)

    result = _transact(
        Path(config_path), Path(spa_home), mutate,
        dry_run=dry_run, expect_revision=expect_revision, validate=validate,
        resolve=resolve, resolve_file=resolve_file, stdin_text=stdin_text,
        command="config topology",
    )
    result["topology"] = topology_id
    return result


def _inventory_names(env_dir: Path) -> set:
    """Host names already present in inventory/hosts."""
    path = env_dir / "inventory" / "hosts"
    if not path.is_file():
        return set()
    names = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.add(stripped.split()[0])
    return names


def config_provider(
    config_path: Path,
    spa_home: Path,
    provider: str,
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    from spa.init import _load_yaml_mapping, resolve_example_pair

    if provider.startswith("provider."):
        from spa.catalog import load_features, resolve_feature

        feature = resolve_feature(load_features(Path(spa_home)), provider)
        if not feature or feature.get("kind") != "provider" or not feature.get("template"):
            from spa.usage import unknown_provider

            raise ConfigEditError(unknown_provider(provider))
        provider = str(feature["template"])
    _, provider_id = resolve_example_pair(Path(spa_home), "single_node", provider)
    example = _load_yaml_mapping(Path(spa_home) / "examples" / "providers" / ("%s.yml" % provider_id))
    env_dir = Path(config_path).resolve().parent.parent
    if provider_id == "external" and (
        (env_dir / "terraform" / "aws" / "terraform.tfstate").is_file()
        or (env_dir / ".vagrant").exists()
    ):
        raise ConfigEditError(
            "Terraform or Vagrant state still exists. Run spa destroy --yes before switching this env to external."
        )

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        for key in _PROVIDER_ROOTS:
            document.pop(key, None)
        registered = _inventory_names(env_dir)
        if provider_id == "external":
            from spa.providers.external import _register_sentence

            document["external"] = None
            for host in document.get("splunk_hosts") or []:
                if not isinstance(host, dict) or not host.get("name"):
                    continue
                name = str(host["name"])
                if name not in registered:
                    warnings.append(_register_sentence(name))
            return
        for host in document.get("splunk_hosts") or []:
            if not isinstance(host, dict):
                continue
            if str(host.get("name") or "") in registered:
                continue
            host.pop("external", None)
            host.pop("provider", None)
        for key, value in example.items():
            if key != "plugin" and value is not None:
                document[key] = copy.deepcopy(value)

    result = _transact(
        Path(config_path), Path(spa_home), mutate,
        dry_run=dry_run, expect_revision=expect_revision,
        validate=validate,
        resolve=resolve, resolve_file=resolve_file, stdin_text=stdin_text,
        command="config provider",
    )
    result["provider"] = provider_id
    return result


def _app_identity(entry: Mapping[str, Any]) -> Tuple[str, Any]:
    if entry.get("app_id") is not None:
        return "app_id", entry["app_id"]
    if entry.get("name"):
        return "name", entry["name"]
    raise ConfigEditError("App entry needs app_id or name")


def _roles_key(roles: Any) -> Tuple[str, ...]:
    return tuple(sorted(str(role) for role in (roles or [])))


def _format_roles_flag(roles: Any) -> str:
    return ",".join(str(role) for role in (roles or []))


def _defined_twice_error(app_id_or_name: Any, copies: Sequence[Mapping[str, Any]]) -> ConfigEditError:
    options = []
    for app in copies:
        options.append("--roles %s" % _format_roles_flag(app.get("target_roles")))
    return ConfigEditError(
        "App %s is defined twice; pass %s" % (app_id_or_name, " or ".join(options))
    )


def _app_copies(apps: Sequence[Any], app_id_or_name: str) -> List[MutableMapping[str, Any]]:
    return [
        app
        for app in apps
        if isinstance(app, MutableMapping)
        and (
            str(app.get("app_id")) == str(app_id_or_name)
            or str(app.get("name")) == str(app_id_or_name)
        )
    ]


def _replace_supplied_fields(current: MutableMapping[str, Any], supplied: Mapping[str, Any]) -> None:
    for key, value in supplied.items():
        if isinstance(value, Mapping) and isinstance(current.get(key), MutableMapping):
            _replace_supplied_fields(current[key], value)
        else:
            current[key] = copy.deepcopy(value)


def config_app_add(
    config_path: Path,
    spa_home: Path,
    entry: Mapping[str, Any],
    *,
    force_new: bool = False,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    identity_key, identity_value = _app_identity(entry)
    dependencies: List[int] = []

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        deployment = document.setdefault("splunk_app_deployment", CommentedMap())
        if entry.get("source", "splunkbase") == "splunkbase":
            deployment.setdefault(
                "splunkbase_username",
                "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}",
            )
            deployment.setdefault(
                "splunkbase_password",
                "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}",
            )
        apps = deployment.setdefault("apps", CommentedSeq())
        needs_itsi = (
            entry.get("itsi_content_pack") is True
            and entry.get("app_id") != 1841
            and entry.get("premium_app") != "itsi"
        )
        if needs_itsi and not any(app.get("app_id") == 1841 for app in apps if isinstance(app, Mapping)):
            apps.append(
                CommentedMap(
                    {
                        "name": "Splunk IT Service Intelligence",
                        "app_id": 1841,
                        "premium_app": "itsi",
                    }
                )
            )
            dependencies.append(1841)
        copies = [
            app
            for app in apps
            if isinstance(app, MutableMapping)
            and str(app.get(identity_key)) == str(identity_value)
        ]
        match: Optional[MutableMapping[str, Any]] = None
        if force_new:
            match = None
        elif not copies:
            match = None
        elif len(copies) == 1:
            match = copies[0]
        else:
            incoming_roles = entry.get("target_roles")
            if not incoming_roles:
                raise _defined_twice_error(identity_value, copies)
            wanted = _roles_key(incoming_roles)
            role_hits = [
                app for app in copies if _roles_key(app.get("target_roles")) == wanted
            ]
            if not role_hits:
                raise ConfigEditError(
                    "App %s has no copy with those roles; pass --new to add another"
                    % identity_value
                )
            if len(role_hits) > 1:
                raise ConfigEditError("%s matched multiple items" % identity_value)
            match = role_hits[0]
        if match is None:
            apps.append(copy.deepcopy(entry))
            return
        if entry.get("app_id") == 5391:
            current_all = match.get("install_all_apps") is True
            incoming_all = entry.get("install_all_apps") is True
            current_named = bool(match.get("content_pack_apps"))
            incoming_named = bool(entry.get("content_pack_apps"))
            if (current_all and incoming_named) or (current_named and incoming_all):
                raise ConfigEditError("Content Library 5391 already uses the other install policy")
            if current_named and incoming_named:
                current_names = {
                    str(item.get("name"))
                    for item in match.get("content_pack_apps") or []
                    if isinstance(item, Mapping)
                }
                for item in entry.get("content_pack_apps") or []:
                    if str(item.get("name")) not in current_names:
                        match["content_pack_apps"].append(copy.deepcopy(item))
                supplied = {key: value for key, value in entry.items() if key != "content_pack_apps"}
                _replace_supplied_fields(match, supplied)
                return
        _replace_supplied_fields(match, entry)

    result = _transact(
        Path(config_path),
        Path(spa_home),
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="apps add",
    )
    result["dependencies"] = dependencies
    return result


def config_app_remove(
    config_path: Path,
    spa_home: Path,
    app_id_or_name: str,
    *,
    content_pack: Optional[str] = None,
    roles: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
    validate: bool = True,
    resolve: Optional[Sequence[Sequence[str]]] = None,
    resolve_file: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> Dict[str, Any]:
    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        deployment = document.get("splunk_app_deployment")
        apps = deployment.get("apps") if isinstance(deployment, MutableMapping) else None
        if not isinstance(apps, list):
            raise ConfigEditError("App %s is not authored in splunk_config.yml" % app_id_or_name)
        copies = _app_copies(apps, app_id_or_name)
        if not copies:
            raise ConfigEditError("App %s is not authored in splunk_config.yml" % app_id_or_name)
        if roles:
            wanted = ",".join(str(role) for role in roles)
            role_hits = [
                app for app in copies if _roles_match(app.get("target_roles"), wanted)
            ]
            if not role_hits:
                raise ConfigEditError(
                    "App %s --roles %s matched no items" % (app_id_or_name, wanted)
                )
            if len(role_hits) > 1:
                raise ConfigEditError(
                    "App %s --roles %s matched multiple items" % (app_id_or_name, wanted)
                )
            match = role_hits[0]
        elif len(copies) > 1:
            raise _defined_twice_error(app_id_or_name, copies)
        else:
            match = copies[0]
        if content_pack is not None:
            if str(match.get("app_id")) != "5391":
                raise ConfigEditError("--content-pack removal is only valid for app 5391")
            packs = match.get("content_pack_apps")
            if not isinstance(packs, list):
                raise ConfigEditError("Content Library 5391 has no named content packs")
            for index, pack in enumerate(packs):
                if isinstance(pack, Mapping) and str(pack.get("name")) == content_pack:
                    del packs[index]
                    return
            raise ConfigEditError("Content pack %s is not authored under app 5391" % content_pack)
        apps.remove(match)

    result = _transact(
        Path(config_path),
        Path(spa_home),
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        validate=validate,
        resolve=resolve,
        resolve_file=resolve_file,
        stdin_text=stdin_text,
        command="apps remove",
    )
    result["note"] = "Configuration removed; already deployed app files are not uninstalled."
    return result
