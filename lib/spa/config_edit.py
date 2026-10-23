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
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


class ConfigEditError(RuntimeError):
    """A safe, operator-facing config edit error."""


_SEGMENT = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<key>[^=\]]+)=(?P<value>[^\]]+)\])?$")
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
_PROVIDER_ROOTS = ("terraform", "virtualbox", "aws")
_TOPOLOGY_ROOTS = ("splunk_hosts", "splunk_idxclusters", "splunk_shclusters", "splunk_environments")
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


def _segments(path: str) -> List[Tuple[str, Optional[str], Optional[str]]]:
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
        parsed.append((match.group("name"), match.group("key"), match.group("value")))
    return parsed


def _normalized_path(path: str) -> str:
    return ".".join("%s[]" % name if key else name for name, key, _ in _segments(path))


def _nested_get(item: Mapping[str, Any], path: str) -> Any:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _select(items: Any, key: str, value: str, path: str) -> MutableMapping[str, Any]:
    if not isinstance(items, list):
        raise ConfigEditError("%s is not a list" % path)
    matches = []
    for item in items:
        if not isinstance(item, MutableMapping):
            continue
        actual = _nested_get(item, key)
        if str(actual) == value:
            matches.append(item)
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
    for name, selector_key, selector_value in parsed[:-1]:
        walked.append(name)
        if not isinstance(current, MutableMapping):
            raise ConfigEditError("%s is not a mapping" % ".".join(walked[:-1]))
        if name not in current or current.get(name) is None:
            if selector_key or not create:
                raise ConfigEditError("%s does not exist" % ".".join(walked))
            current[name] = CommentedMap()
        current = current[name]
        if selector_key:
            current = _select(current, selector_key, str(selector_value), ".".join(walked))
    leaf, selector_key, selector_value = parsed[-1]
    if selector_key:
        if not isinstance(current, MutableMapping) or leaf not in current:
            raise ConfigEditError("%s does not exist" % path)
        selected = _select(current[leaf], selector_key, str(selector_value), path)
        return selected, ""
    if not isinstance(current, MutableMapping):
        raise ConfigEditError("Parent of %s is not a mapping" % path)
    return current, leaf


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


def _parse_value(path: str, raw: str) -> Any:
    detail = _schema_detail(path)
    type_name = str((detail or {}).get("type") or "string")
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
    for name, selector_key, selector_value in parsed[:-1]:
        if not isinstance(current, MutableMapping) or name not in current:
            return
        if selector_key:
            current = _select(current[name], selector_key, str(selector_value), path)
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
        names = tuple(name for name, _, _ in _segments(prefix))
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
        warnings: List[str] = []
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
            else {"ready": True, "requirements": [], "repairs": []}
        )
        document = _ordered(document)
        operations = _leaf_operations(before, document)
        diff = _redacted_diff(before, document) if operations else ""
        if not dependency["ready"]:
            return {
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
            }
        if not operations:
            return {
                "changed": False,
                "ready": True,
                "revision_before": before_revision,
                "operations": [],
                "diff": "",
                "warnings": warnings,
                "omitted_defaults": [],
                "validation": "ok",
                "requirements": [],
            }
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
            return result
        finally:
            if temp_path.exists():
                temp_path.unlink()


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
    omitted = default is not _MISSING and parsed == default and not explicit_default

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        if omitted:
            warnings.append("%s already has the schema default; use --explicit-default to author it" % path)
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
    )
    if omitted:
        result["omitted_defaults"] = [{"path": path, "value": _redacted_value(path, parsed)}]
    return result


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
            "spa aws --region %s --describe-ami --ami-id %s can identify it."
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
    names = tuple(name for name, _, _ in parsed)
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
    for name, selector_key, selector_value in _segments(path)[:-1]:
        walked.append(name)
        if not isinstance(current, MutableMapping):
            raise ConfigEditError("%s is not a mapping" % ".".join(walked[:-1]))
        if selector_key:
            if name not in current:
                raise ConfigEditError("%s does not exist" % ".".join(walked))
            current = _select(current[name], selector_key, str(selector_value), ".".join(walked))
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
                for name, selector_key, selector_value in parsed[:-1]:
                    if not isinstance(current, MutableMapping) or name not in current:
                        raise ConfigEditError("%s does not exist" % path)
                    current = current[name]
                    if selector_key:
                        current = _select(
                            current, selector_key, str(selector_value), path
                        )
                name, selector_key, selector_value = parsed[-1]
                if not isinstance(current, MutableMapping) or name not in current:
                    raise ConfigEditError("%s does not exist" % path)
                selected = _select(
                    current[name], str(selector_key), str(selector_value), path
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
    )


def _safe_read_value(document: MutableMapping[str, Any], path: str) -> Any:
    parent, leaf = _parent(document, path, create=False)
    if not leaf:
        return parent
    if leaf not in parent:
        raise ConfigEditError("%s is unset" % path)
    return parent[leaf]


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
    if _is_secret(path):
        try:
            _safe_read_value(document, path)
            state = "set"
        except ConfigEditError:
            state = "not set"
        return {
            "revision": revision,
            "path": path,
            "source": "explicit" if state == "set" else "unset",
            "authored": state,
            "effective": state,
        }
    try:
        value = copy.deepcopy(_safe_read_value(document, path))
        return {
            "revision": revision,
            "path": path,
            "source": "explicit",
            "authored": value,
            "effective": value,
        }
    except ConfigEditError:
        if effective and detail and "default" in detail:
            return {
                "revision": revision,
                "path": path,
                "source": "schema_default",
                "authored": None,
                "effective": copy.deepcopy(detail["default"]),
            }
        return {
            "revision": revision,
            "path": path,
            "source": "unset",
            "authored": None,
            "effective": None,
        }


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
        rows.append({"name": path.stem, "summary": summary})
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


def _plain_fragment(value: Any) -> Any:
    """Drop ruamel comment metadata while retaining YAML 1.2 scalar values."""
    if isinstance(value, Mapping):
        return {key: _plain_fragment(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_plain_fragment(child) for child in value]
    return copy.deepcopy(value)


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
    )
    result["omitted_defaults"] = omitted_defaults
    return result


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
    from spa.init import _load_yaml_mapping, resolve_example_pair

    if topology.startswith("topology."):
        from spa.catalog import load_features, resolve_feature

        feature = resolve_feature(load_features(Path(spa_home)), topology)
        if not feature or feature.get("kind") != "topology" or not feature.get("template"):
            raise ConfigEditError("Unknown topology feature: %s" % topology)
        topology = str(feature["template"])
    topology_id, _, _ = resolve_example_pair(Path(spa_home), topology, None)
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
    )
    result["topology"] = topology_id
    return result


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
            raise ConfigEditError("Unknown provider feature: %s" % provider)
        provider = str(feature["template"])
    _, provider_id, _ = resolve_example_pair(Path(spa_home), "single_node", provider)
    example = _load_yaml_mapping(Path(spa_home) / "examples" / "providers" / ("%s.yml" % provider_id))

    def mutate(document: MutableMapping[str, Any], warnings: List[str]) -> None:
        for key in _PROVIDER_ROOTS:
            document.pop(key, None)
        for key, value in example.items():
            if key != "plugin" and value is not None:
                document[key] = copy.deepcopy(value)

    result = _transact(
        Path(config_path), Path(spa_home), mutate,
        dry_run=dry_run, expect_revision=expect_revision, validate=validate,
        resolve=resolve, resolve_file=resolve_file, stdin_text=stdin_text,
    )
    result["provider"] = provider_id
    return result


def _app_identity(entry: Mapping[str, Any]) -> Tuple[str, Any]:
    if entry.get("app_id") is not None:
        return "app_id", entry["app_id"]
    if entry.get("name"):
        return "name", entry["name"]
    raise ConfigEditError("App entry needs app_id or name")


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
        match = next(
            (
                app
                for app in apps
                if isinstance(app, MutableMapping)
                and str(app.get(identity_key)) == str(identity_value)
            ),
            None,
        )
        if match is None:
            apps.append(copy.deepcopy(entry))
            return
        if entry.get("app_id") == 5391:
            current_all = bool((match.get("content_pack_api") or {}).get("install_all_apps"))
            incoming_all = bool((entry.get("content_pack_api") or {}).get("install_all_apps"))
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
    )
    result["dependencies"] = dependencies
    return result


def config_app_remove(
    config_path: Path,
    spa_home: Path,
    app_id_or_name: str,
    *,
    content_pack: Optional[str] = None,
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
        match = next(
            (
                app
                for app in apps
                if isinstance(app, MutableMapping)
                and (
                    str(app.get("app_id")) == str(app_id_or_name)
                    or str(app.get("name")) == str(app_id_or_name)
                )
            ),
            None,
        )
        if match is None:
            raise ConfigEditError("App %s is not authored in splunk_config.yml" % app_id_or_name)
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
    )
    result["note"] = "Configuration removed; already deployed app files are not uninstalled."
    return result
