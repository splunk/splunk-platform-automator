"""splunk.architecture schema 1: plan, overlay, and check against SPA config."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from spa.hosts import allowed_role_names

SUPPORTED_ARCHITECTURE_VERSION = 1
ARCHITECTURE_KIND = "splunk.architecture"
# Older architecture schema_version → callable(doc). Empty: no 0.4.0 migrator.
ARCHITECTURE_MIGRATORS: Dict[int, Any] = {}

SVA_TO_SPA_ROLE = {
    "cluster_master": "cluster_manager",
    "multisite_cluster_master": "cluster_manager",
    "indexer": "indexer",
    "indexer_cluster_peer": "indexer",
    "site_indexer_peer": "indexer",
    "search_head": "search_head",
    "cluster_search_head": "search_head",
    "multisite_search_head": "search_head",
    "shc_member": "search_head",
    "es_search_head": "search_head",
    "shc_deployer": "deployer",
    "license_master": "license_manager",
    "deployment_server": "deployment_server",
    "monitoring_console": "monitoring_console",
    "universal_forwarder": "universal_forwarder",
    "heavy_forwarder": "heavy_forwarder",
}

DEDICATED_HOST = {
    "license_manager": "lm",
    "monitoring_console": "mc",
    "deployment_server": "dsrv",
    "universal_forwarder": "uf",
    "heavy_forwarder": "hf",
    "cluster_manager": "cm",
    "deployer": "ds",
}

REPEATING_ROLES = frozenset({"indexer", "search_head"})
ROLES_NEEDING_IDXC = frozenset({"cluster_manager", "indexer"})
ROLES_NEEDING_SHC = frozenset({"deployer", "search_head"})
SKIPPED_FIELDS = ("apps.by_role", "delivery")


def _folder_names_from_by_role(by_role: Any) -> List[str]:
    names: List[str] = []
    if not isinstance(by_role, Mapping):
        return names
    for value in by_role.values():
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = str(item or "").strip()
            if text and text not in names:
                names.append(text)
    return names

ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
ORG_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
SVA_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]*$")
HOST_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
SECRET_VALUE_RE = re.compile(
    r"-----BEGIN|AKIA|ghp_|sk_live_|sk_test_|eyJ[^\s.]*\.[^\s.]+\.[^\s.]+"
)
CREDENTIAL_KEY_RE = re.compile(r"password|secret|token|credential|key", re.IGNORECASE)
REQUIRED_ROOTS = (
    "kind",
    "schema_version",
    "confirmed",
    "generator",
    "sva",
    "environment",
    "deployment",
    "apps",
    "extensions",
)


class ArchitectureError(ValueError):
    """The architecture file cannot be read or is not valid for this spa."""


def load_architecture_file(path: Path) -> Dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ArchitectureError("cannot read architecture file: %s" % exc.strerror) from exc
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ArchitectureError("architecture file is not valid JSON: %s" % exc) from exc
    if not isinstance(doc, dict):
        raise ArchitectureError("architecture file must be a JSON object")
    return doc


def gate_architecture_version(doc: Mapping[str, Any]) -> None:
    kind = doc.get("kind")
    version = doc.get("schema_version")
    if not kind or version is None or version == "":
        raise ArchitectureError("architecture file needs kind and schema_version")
    if kind != ARCHITECTURE_KIND:
        raise ArchitectureError("architecture file kind must be splunk.architecture")
    if isinstance(version, bool):
        raise ArchitectureError("schema_version must be an integer, not a boolean")
    if not isinstance(version, int):
        raise ArchitectureError("schema_version must be an integer")
    if version == SUPPORTED_ARCHITECTURE_VERSION:
        return
    if version > SUPPORTED_ARCHITECTURE_VERSION:
        raise ArchitectureError(
            "this spa reads architecture schema_version %s; the file is %s. Upgrade spa."
            % (SUPPORTED_ARCHITECTURE_VERSION, version)
        )
    migrator = ARCHITECTURE_MIGRATORS.get(version)
    if migrator is None:
        raise ArchitectureError(
            "architecture schema_version %s is not supported; this spa reads %s"
            % (version, SUPPORTED_ARCHITECTURE_VERSION)
        )
    migrator(doc)


def expand_host_names(host: Mapping[str, Any]) -> List[str]:
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


def host_roles(host: Mapping[str, Any]) -> List[str]:
    return [str(role) for role in (host.get("roles") or [])]


def occupied_names(hosts: Sequence[Mapping[str, Any]]) -> List[str]:
    names: List[str] = []
    for host in hosts:
        names.extend(expand_host_names(host))
    return names


def spa_role_for(sva_role: str) -> Optional[str]:
    mapped = SVA_TO_SPA_ROLE.get(sva_role)
    if mapped and mapped in set(allowed_role_names()):
        return mapped
    return None


def topology_feature_for_sva(spa_home: Path, code: str) -> Dict[str, Any]:
    from spa.catalog import load_features

    wanted = str(code or "").upper()
    matches = [
        item
        for item in load_features(spa_home)
        if item.get("kind") == "topology" and str(item.get("sva") or "").upper() == wanted
    ]
    if not matches:
        if SVA_CODE_RE.match(wanted):
            raise ArchitectureError(
                "sva.code %s has no catalog topology. List the ids: spa --agent init list."
                % wanted
            )
        raise ArchitectureError(
            "sva.code has no catalog topology. List the ids: spa --agent init list."
        )
    return matches[0]


def load_topology_config(spa_home: Path, template: str) -> Dict[str, Any]:
    path = Path(spa_home) / "examples" / "topologies" / ("%s.yml" % template)
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ArchitectureError("PyYAML is required to plan architecture") from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ArchitectureError("cannot read topology %s: %s" % (template, exc.strerror)) from exc
    if not isinstance(data, dict):
        raise ArchitectureError("topology %s is not a mapping" % template)
    return data


def parse_architecture(doc: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    try:
        gate_architecture_version(doc)
    except ArchitectureError as exc:
        return {}, [str(exc)], warnings
    _scan_credentials(doc, "", errors)
    missing = [key for key in REQUIRED_ROOTS if key not in doc]
    if missing:
        errors.append("architecture file is missing %s" % ", ".join(missing))
        return {}, errors, warnings
    if not isinstance(doc.get("confirmed"), bool):
        errors.append("confirmed must be a boolean")
    sva = doc.get("sva") if isinstance(doc.get("sva"), Mapping) else {}
    code = str(sva.get("code") or "")
    if not code:
        errors.append("sva.code is required")
    environment = doc.get("environment") if isinstance(doc.get("environment"), Mapping) else {}
    org_prefix = str(environment.get("org_prefix") or "")
    if org_prefix and not ORG_PREFIX_RE.match(org_prefix):
        errors.append("environment.org_prefix is not a valid SPA environment name")
    deployment = doc.get("deployment") if isinstance(doc.get("deployment"), Mapping) else {}
    roles_in = deployment.get("roles")
    if not isinstance(roles_in, list) or not roles_in:
        errors.append("deployment.roles must be a non-empty list")
        roles_in = []
    roles: List[Dict[str, Any]] = []
    allowed = allowed_role_names()
    for index, row in enumerate(roles_in):
        if not isinstance(row, Mapping) or not row.get("role"):
            errors.append("deployment.roles[%s] needs role and count" % index)
            continue
        sva_role = str(row["role"])
        count = row.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            errors.append("deployment.roles[%s].count must be an integer >= 1" % index)
            continue
        spa_role = spa_role_for(sva_role)
        if spa_role is None:
            errors.append(
                "architecture role %s has no SPA mapping. Allowed SPA roles: %s"
                % (sva_role, ", ".join(allowed))
            )
            continue
        by_site = row.get("by_site") if isinstance(row.get("by_site"), Mapping) else None
        roles.append(
            {
                "sva_role": sva_role,
                "spa_role": spa_role,
                "count": count,
                "by_site": {str(site): int(n) for site, n in (by_site or {}).items()}
                if by_site
                else None,
            }
        )
    apps = doc.get("apps") if isinstance(doc.get("apps"), Mapping) else {}
    if "by_role" not in apps:
        errors.append("apps.by_role is required")
    apps_by_role_folders = _folder_names_from_by_role(apps.get("by_role"))
    secrets = _secret_refs(doc.get("secrets"), errors)
    if errors:
        return {}, errors, warnings
    parsed = {
        "kind": ARCHITECTURE_KIND,
        "schema_version": SUPPORTED_ARCHITECTURE_VERSION,
        "confirmed": bool(doc.get("confirmed")),
        "sva_code": code.upper(),
        "clustering": bool(sva.get("clustering")),
        "multisite": bool(sva.get("multisite")),
        "search_head_cluster": bool(sva.get("search_head_cluster")),
        "org_prefix": org_prefix,
        "environment_name": str(environment.get("name") or ""),
        "roles": roles,
        "clusters": doc.get("clusters") if isinstance(doc.get("clusters"), Mapping) else {},
        "secrets": secrets,
        "has_delivery": "delivery" in doc,
        "apps_by_role_folders": apps_by_role_folders,
        "extensions": list(doc.get("extensions") or [])
        if isinstance(doc.get("extensions"), list)
        else [],
    }
    return parsed, errors, warnings


def plan_architecture(
    doc: Mapping[str, Any],
    env: Optional[Mapping[str, str]] = None,
    spa_home: Optional[Path] = None,
) -> Dict[str, Any]:
    parsed, errors, warnings = parse_architecture(doc)
    if errors:
        return _result(ok=False, errors=errors, warnings=warnings)
    if not parsed["confirmed"]:
        warnings.append("architecture file is not confirmed")
    home = Path(spa_home) if spa_home else Path(".")
    try:
        feature = topology_feature_for_sva(home, parsed["sva_code"])
        config = load_topology_config(home, str(feature["template"]))
    except ArchitectureError as exc:
        return _result(ok=False, errors=[str(exc)], warnings=warnings)
    report = overlay_architecture(config, parsed, warnings)
    skipped = list(SKIPPED_FIELDS)
    remaining = remaining_questions(config, has_provider=False)
    skipped_app_folders = list(parsed.get("apps_by_role_folders") or [])
    secrets = _secret_status(parsed["secrets"], env or {})
    return _result(
        ok=True,
        errors=[],
        warnings=warnings,
        extra={
            "kind": ARCHITECTURE_KIND,
            "schema_version": SUPPORTED_ARCHITECTURE_VERSION,
            "sva": parsed["sva_code"],
            "topology": feature["id"],
            "topology_id": feature["template"],
            "confirmed": parsed["confirmed"],
            "skipped": skipped,
            "skipped_app_folders": skipped_app_folders,
            "remaining": remaining,
            "placement": report["placement"],
            "ingested": report["ingested"],
            "hosts": list(config.get("splunk_hosts") or []),
            "config": config,
            "secrets": secrets,
        },
    )


def overlay_architecture(
    config: MutableMapping[str, Any],
    parsed: Mapping[str, Any],
    warnings: List[str],
    *,
    apply_schema: bool = False,
) -> Dict[str, Any]:
    hosts = config.setdefault("splunk_hosts", [])
    if parsed.get("org_prefix"):
        defaults = config.setdefault("splunk_defaults", {})
        defaults["splunk_env_name"] = parsed["org_prefix"]
    _overlay_clusters(config, parsed.get("clusters") or {}, warnings)
    placement: List[Dict[str, Any]] = []
    ingested_counts: Dict[str, int] = {}
    added: List[str] = []
    scaled: List[str] = []
    for row in parsed.get("roles") or []:
        spa_role = row["spa_role"]
        before = occupied_names([host for host in hosts if spa_role in host_roles(host)])
        cluster_keys = _cluster_keys(config, spa_role, hosts)
        if (
            apply_schema
            and spa_role == "license_manager"
            and not _has_license_file(config)
        ):
            placement.append(
                {
                    "sva_role": row["sva_role"],
                    "spa_role": spa_role,
                    "count": 0,
                    "hosts": [],
                    "existing": False,
                    "deferred": "needs a license file",
                }
            )
            warnings.append(
                "license_manager is required by the architecture file but not applied until a license file is set"
            )
            continue
        _ensure_role_count(hosts, spa_role, row["count"], row.get("by_site"), cluster_keys)
        after = occupied_names([host for host in hosts if spa_role in host_roles(host)])
        ingested_counts[spa_role] = len(after)
        if not before:
            added.extend(name for name in after if name not in before)
        elif set(after) != set(before):
            scaled.append(spa_role)
        placement.append(
            {
                "sva_role": row["sva_role"],
                "spa_role": spa_role,
                "count": len(after),
                "hosts": after,
                "existing": bool(before),
            }
        )
    shc = (parsed.get("clusters") or {}).get("search_head") or {}
    if isinstance(shc, Mapping) and shc.get("replication_factor") is not None:
        warnings.append(
            "clusters.search_head.replication_factor is not a SPA setting; not applied"
        )
    return {
        "placement": placement,
        "ingested": {
            "counts": ingested_counts,
            "org_prefix": parsed.get("org_prefix") or None,
            "hosts_added": added,
            "hosts_scaled": scaled,
        },
    }


def _has_license_file(config: Mapping[str, Any]) -> bool:
    defaults = config.get("splunk_defaults") or {}
    if defaults.get("splunk_license_file"):
        return True
    for environment in config.get("splunk_environments") or []:
        if isinstance(environment, Mapping) and (environment.get("splunk_defaults") or {}).get(
            "splunk_license_file"
        ):
            return True
    for host in config.get("splunk_hosts") or []:
        if isinstance(host, Mapping) and host.get("splunk_license_file"):
            return True
    return False


def remaining_questions(
    config: Optional[Mapping[str, Any]] = None, *, has_provider: bool = False
) -> List[str]:
    remaining: List[str] = []
    if not has_provider:
        remaining.append("provider")
    remaining.extend(["hardware", "os"])
    if config and (config.get("terraform") or {}).get("aws"):
        remaining.append("aws")
    remaining.extend(["apps", "licenses"])
    return remaining


def check_architecture(
    config: Mapping[str, Any], parsed: Mapping[str, Any], spa_home: Optional[Path] = None
) -> Dict[str, Any]:
    mismatches: List[Dict[str, Any]] = []
    hosts = list(config.get("splunk_hosts") or [])
    expected_shape = {
        "clustering": bool(parsed.get("clustering")),
        "search_head_cluster": bool(parsed.get("search_head_cluster")),
        "multisite": bool(parsed.get("multisite")),
    }
    found_shape = _config_shape(config)
    if found_shape != expected_shape:
        mismatches.append(
            {
                "path": "sva.code",
                "expected": parsed.get("sva_code"),
                "found": found_shape,
            }
        )
    extra_roles: Dict[str, List[str]] = {}
    required_spa = {row["spa_role"] for row in parsed.get("roles") or []}
    for row in parsed.get("roles") or []:
        spa_role = row["spa_role"]
        have = [
            (name, host)
            for host in hosts
            if spa_role in host_roles(host)
            for name in expand_host_names(host)
        ]
        if len(have) < row["count"]:
            mismatches.append(
                {
                    "path": "deployment.roles.%s.count" % row["sva_role"],
                    "expected": row["count"],
                    "found": len(have),
                }
            )
        by_site = row.get("by_site") or {}
        for site, needed in by_site.items():
            on_site = [
                name
                for host in hosts
                if spa_role in host_roles(host) and host.get("site") == site
                for name in expand_host_names(host)
            ]
            if len(on_site) < int(needed):
                mismatches.append(
                    {
                        "path": "deployment.roles.%s.by_site.%s" % (row["sva_role"], site),
                        "expected": int(needed),
                        "found": len(on_site),
                    }
                )
    for host in hosts:
        for role in host_roles(host):
            if role not in required_spa:
                extra_roles.setdefault(role, []).extend(expand_host_names(host))
    _check_clusters(config, parsed.get("clusters") or {}, mismatches)
    if parsed.get("org_prefix"):
        found = (config.get("splunk_defaults") or {}).get("splunk_env_name")
        if found != parsed["org_prefix"]:
            mismatches.append(
                {
                    "path": "environment.org_prefix",
                    "expected": parsed["org_prefix"],
                    "found": found,
                }
            )
    extra_hosts = [
        name
        for host in hosts
        for name in expand_host_names(host)
        if not required_spa.intersection(host_roles(host))
    ]
    extra = {"roles": extra_roles, "hosts": extra_hosts}
    if mismatches:
        return {"ok": False, "mismatches": mismatches, "extra": extra}
    matched = {
        "sva": parsed.get("sva_code"),
        "counts": {
            row["spa_role"]: len(
                occupied_names([host for host in hosts if row["spa_role"] in host_roles(host)])
            )
            for row in parsed.get("roles") or []
        },
    }
    return {"ok": True, "matched": matched, "extra": extra}


def check_mismatch_warnings(
    config: Mapping[str, Any],
    parsed: Mapping[str, Any],
    spa_home: Optional[Path] = None,
) -> List[str]:
    result = check_architecture(config, parsed, spa_home=spa_home)
    return [
        "architecture check: %s: expected %s, found %s"
        % (item.get("path"), item.get("expected"), item.get("found"))
        for item in result.get("mismatches") or []
    ]


def format_plan_text(plan: Mapping[str, Any]) -> str:
    lines: List[str] = []
    if plan.get("sva"):
        lines.append(
            "Architecture: %s (%s / %s)"
            % (plan.get("sva"), plan.get("topology"), plan.get("topology_id"))
        )
    lines.append("Confirmed: %s" % ("yes" if plan.get("confirmed") else "no"))
    lines.append("")
    lines.append("Hosts:")
    for host in plan.get("hosts") or []:
        names = expand_host_names(host)
        roles = ",".join(host_roles(host))
        for name in names:
            lines.append("  %s  %s" % (name, roles))
    skipped = plan.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append("Skipped: %s" % ", ".join(skipped))
    remaining = plan.get("remaining") or []
    if remaining:
        lines.append("Remaining: %s" % ", ".join(remaining))
    for row in plan.get("secrets") or []:
        lines.append("Env %s (%s): %s" % (row.get("name"), row.get("key"), row.get("state")))
    warnings = plan.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.append("  %s" % warning)
    errors = plan.get("errors") or []
    if errors:
        lines.append("")
        lines.append("Errors:")
        for error in errors:
            lines.append("  %s" % error)
    return "\n".join(lines) + "\n"


def apply_architecture_document(
    config_path: Path,
    spa_home: Path,
    parsed: Mapping[str, Any],
    *,
    dry_run: bool = False,
    expect_revision: Optional[str] = None,
) -> Dict[str, Any]:
    if not parsed.get("confirmed"):
        raise ArchitectureError("architecture file is not confirmed")
    from spa.config_edit import config_mutate

    warnings: List[str] = []
    report: Dict[str, Any] = {}
    remaining: List[str] = []

    def mutate(document: MutableMapping[str, Any], txn_warnings: List[str]) -> None:
        overlay = overlay_architecture(
            document, parsed, txn_warnings, apply_schema=True
        )
        txn_warnings.extend(check_mismatch_warnings(document, parsed, spa_home))
        report.update(overlay)
        remaining[:] = remaining_questions(document, has_provider=True)
        txn_warnings.extend(warnings)

    data = config_mutate(
        config_path,
        spa_home,
        mutate,
        dry_run=dry_run,
        expect_revision=expect_revision,
        command="architecture apply",
    )
    data["ingested"] = report.get("ingested") or {}
    data["placement"] = report.get("placement") or []
    data["skipped"] = list(SKIPPED_FIELDS)
    data["skipped_app_folders"] = list(parsed.get("apps_by_role_folders") or [])
    data["remaining"] = remaining or remaining_questions(None, has_provider=True)
    if any(item.get("deferred") for item in data.get("placement") or []):
        if "license_manager" not in data["remaining"]:
            data["remaining"].append("license_manager")
    return data


def _result(
    *,
    ok: bool,
    errors: List[str],
    warnings: List[str],
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
    }
    if extra:
        payload.update(extra)
    return payload


def _scan_credentials(node: Any, path: str, errors: List[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            here = "%s.%s" % (path, key) if path else str(key)
            if here == "secrets" or here.startswith("secrets."):
                continue
            if CREDENTIAL_KEY_RE.search(str(key)) and value not in (None, "", []):
                errors.append("%s looks like a credential and is not allowed" % here)
                continue
            if isinstance(value, str) and SECRET_VALUE_RE.search(value):
                errors.append("%s looks like a secret value and is not allowed" % here)
                continue
            _scan_credentials(value, here, errors)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _scan_credentials(item, "%s[%s]" % (path, index), errors)


def _secret_refs(raw: Any, errors: List[str]) -> List[Dict[str, str]]:
    if raw in (None, {}):
        return []
    if not isinstance(raw, Mapping):
        errors.append("secrets must be an object of env or vault references")
        return []
    refs: List[Dict[str, str]] = []
    for key, spec in raw.items():
        here = "secrets.%s" % key
        if not isinstance(spec, Mapping):
            errors.append("%s must be a {source, name} reference" % here)
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not ENV_NAME_RE.match(name):
            errors.append("%s.name must be an environment variable name" % here)
            continue
        refs.append({"key": str(key), "name": name, "source": str(spec.get("source") or "env")})
    return refs


def _secret_status(
    refs: Sequence[Mapping[str, str]], env: Mapping[str, str]
) -> List[Dict[str, str]]:
    rows = []
    for ref in refs:
        name = ref["name"]
        rows.append(
            {
                "key": ref["key"],
                "name": name,
                "state": "set" if (env.get(name) or "").strip() else "not set",
            }
        )
    return rows


def _cluster_keys(
    config: Mapping[str, Any], spa_role: str, hosts: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    keys: Dict[str, Any] = {}
    idxcs = config.get("splunk_idxclusters") or []
    shcs = config.get("splunk_shclusters") or []
    if spa_role in ROLES_NEEDING_IDXC and idxcs:
        keys["idxcluster"] = idxcs[0].get("idxc_name")
    if spa_role in ROLES_NEEDING_SHC and shcs:
        keys["shcluster"] = shcs[0].get("shc_name")
    peers = [host for host in hosts if spa_role in host_roles(host)]
    if peers:
        sample = peers[0]
        for field in ("idxcluster", "shcluster", "site"):
            if sample.get(field) and field not in keys:
                keys[field] = sample[field]
    return keys


def _ensure_role_count(
    hosts: List[Any],
    spa_role: str,
    count: int,
    by_site: Optional[Mapping[str, int]],
    cluster_keys: Mapping[str, Any],
) -> None:
    if by_site:
        _scale_by_site(hosts, spa_role, by_site, cluster_keys)
        return
    entries = [host for host in hosts if spa_role in host_roles(host)]
    current = sum(len(expand_host_names(host)) for host in entries)
    if current == count and entries:
        return
    if not entries:
        _add_role_hosts(hosts, spa_role, count, cluster_keys)
        return
    if len(entries) == 1 and entries[0].get("iter"):
        iteration = entries[0]["iter"]
        start = int(str(iteration.get("numbers") or "1..1").split("..")[0])
        iteration["numbers"] = "%s..%s" % (start, start + count - 1)
        return
    if current < count:
        _extend_hosts(hosts, entries, spa_role, count, cluster_keys)
        return
    if current > count:
        _shrink_hosts(hosts, spa_role, count)


def _scale_by_site(
    hosts: List[Any],
    spa_role: str,
    by_site: Mapping[str, int],
    cluster_keys: Mapping[str, Any],
) -> None:
    current = {}
    for host in hosts:
        if spa_role not in host_roles(host):
            continue
        site = str(host.get("site") or "")
        current[site] = current.get(site, 0) + len(expand_host_names(host))
    needed = {str(site): int(n) for site, n in by_site.items() if int(n) > 0}
    if current == needed:
        return
    prefix = "idx" if spa_role == "indexer" else "sh"
    new_entries: List[Dict[str, Any]] = []
    next_number = 1
    for site, n in needed.items():
        extra = dict(cluster_keys)
        sample = next(
            (
                host
                for host in hosts
                if spa_role in host_roles(host) and host.get("site") == site
            ),
            None,
        )
        if sample:
            for field in ("idxcluster", "shcluster"):
                if sample.get(field):
                    extra[field] = sample[field]
        extra["site"] = site
        start = next_number
        end = next_number + n - 1
        next_number = end + 1
        new_entries.append(
            {
                "iter": {"prefix": prefix, "numbers": "%s..%s" % (start, end)},
                "roles": [spa_role],
                **{key: value for key, value in extra.items() if value},
            }
        )
    _replace_role_entries(hosts, spa_role, new_entries)


def _replace_role_entries(hosts: List[Any], spa_role: str, new_entries: Sequence[Mapping[str, Any]]) -> None:
    indices = [index for index, host in enumerate(hosts) if spa_role in host_roles(host)]
    if not indices:
        hosts.extend(copy.deepcopy(list(new_entries)))
        return
    first = indices[0]
    for index in reversed(indices):
        del hosts[index]
    for offset, entry in enumerate(new_entries):
        hosts.insert(first + offset, copy.deepcopy(dict(entry)))


def _add_role_hosts(
    hosts: List[Any],
    spa_role: str,
    count: int,
    cluster_keys: Mapping[str, Any],
) -> None:
    extra = {key: value for key, value in cluster_keys.items() if value}
    if spa_role in REPEATING_ROLES:
        prefix = "idx" if spa_role == "indexer" else "sh"
        hosts.append(
            {
                "iter": {"prefix": prefix, "numbers": "1..%s" % count},
                "roles": [spa_role],
                **extra,
            }
        )
        return
    preferred = DEDICATED_HOST.get(spa_role, spa_role)
    taken = set(occupied_names(hosts))
    name = preferred
    if name in taken:
        name = _unique_name(taken, preferred)
    entry: Dict[str, Any] = {"name": name, "roles": [spa_role]}
    if spa_role in ROLES_NEEDING_IDXC and extra.get("idxcluster"):
        entry["idxcluster"] = extra["idxcluster"]
    if spa_role in ROLES_NEEDING_SHC and extra.get("shcluster"):
        entry["shcluster"] = extra["shcluster"]
    hosts.append(entry)


def _extend_hosts(
    hosts: List[Any],
    entries: Sequence[Mapping[str, Any]],
    spa_role: str,
    count: int,
    cluster_keys: Mapping[str, Any],
) -> None:
    current = sum(len(expand_host_names(host)) for host in entries)
    missing = count - current
    if missing <= 0:
        return
    last = entries[-1]
    extra = {key: value for key, value in cluster_keys.items() if value}
    for field in ("idxcluster", "shcluster", "site"):
        if last.get(field):
            extra[field] = last[field]
    if last.get("iter"):
        iteration = last["iter"]
        start, end = (int(part) for part in str(iteration["numbers"]).split(".."))
        iteration["numbers"] = "%s..%s" % (start, end + missing)
        return
    prefix = str(last.get("name") or ("idx" if spa_role == "indexer" else "sh"))
    prefix = re.sub(r"\d+$", "", prefix) or prefix
    taken = set(occupied_names(hosts))
    next_number = 1
    while missing > 0:
        candidate = "%s%s" % (prefix, next_number)
        next_number += 1
        if candidate in taken:
            continue
        hosts.append({"name": candidate, "roles": [spa_role], **extra})
        taken.add(candidate)
        missing -= 1


def _shrink_hosts(hosts: List[Any], spa_role: str, count: int) -> None:
    remaining = count
    keep: List[Any] = []
    for host in list(hosts):
        if spa_role not in host_roles(host):
            keep.append(host)
            continue
        names = expand_host_names(host)
        if remaining <= 0:
            continue
        if host.get("iter") and len(names) > remaining:
            iteration = host["iter"]
            start = int(str(iteration["numbers"]).split("..")[0])
            iteration["numbers"] = "%s..%s" % (start, start + remaining - 1)
            keep.append(host)
            remaining = 0
            continue
        if len(names) <= remaining:
            keep.append(host)
            remaining -= len(names)
            continue
    hosts[:] = keep


def _unique_name(taken: Iterable[str], preferred: str) -> str:
    occupied = set(taken)
    if preferred not in occupied:
        return preferred
    index = 2
    while "%s%s" % (preferred, index) in occupied:
        index += 1
    return "%s%s" % (preferred, index)


def _overlay_clusters(
    config: MutableMapping[str, Any], clusters: Mapping[str, Any], warnings: List[str]
) -> None:
    indexer = clusters.get("indexer") if isinstance(clusters.get("indexer"), Mapping) else None
    if indexer:
        rows = config.setdefault("splunk_idxclusters", [])
        target = _cluster_row(rows, "idxc_name", indexer.get("name"))
        old_name = target.get("idxc_name")
        if indexer.get("name"):
            target["idxc_name"] = indexer["name"]
        if indexer.get("replication_port"):
            target["idxc_replication_port"] = indexer["replication_port"]
        if indexer.get("replication_factor") is not None:
            target["idxc_rf"] = indexer["replication_factor"]
        if indexer.get("search_factor") is not None:
            target["idxc_sf"] = indexer["search_factor"]
        site_rf = indexer.get("site_replication_factor")
        if isinstance(site_rf, Mapping) and "origin" in site_rf and "total" in site_rf:
            target["idxc_site_rf"] = "origin:%s, total:%s" % (site_rf["origin"], site_rf["total"])
        site_sf = indexer.get("site_search_factor")
        if isinstance(site_sf, Mapping) and "origin" in site_sf and "total" in site_sf:
            target["idxc_site_sf"] = "origin:%s, total:%s" % (site_sf["origin"], site_sf["total"])
        if old_name and target.get("idxc_name") != old_name:
            _rewrite_host_field(config, "idxcluster", str(old_name), str(target["idxc_name"]))
    search = clusters.get("search_head") if isinstance(clusters.get("search_head"), Mapping) else None
    if search:
        rows = config.setdefault("splunk_shclusters", [])
        target = _cluster_row(rows, "shc_name", search.get("name"))
        old_name = target.get("shc_name")
        if search.get("name"):
            target["shc_name"] = search["name"]
        if search.get("replication_port"):
            target["shc_replication_port"] = search["replication_port"]
        if old_name and target.get("shc_name") != old_name:
            _rewrite_host_field(config, "shcluster", str(old_name), str(target["shc_name"]))


def _cluster_row(rows: List[Any], key: str, name: Any) -> MutableMapping[str, Any]:
    if name:
        for row in rows:
            if isinstance(row, MutableMapping) and row.get(key) == name:
                return row
    if rows and isinstance(rows[0], MutableMapping):
        return rows[0]
    created: Dict[str, Any] = {key: name} if name else {}
    rows.append(created)
    return created


def _rewrite_host_field(
    config: Mapping[str, Any], field: str, old: str, new: str
) -> None:
    for host in config.get("splunk_hosts") or []:
        if isinstance(host, MutableMapping) and host.get(field) == old:
            host[field] = new


def _config_shape(config: Mapping[str, Any]) -> Dict[str, bool]:
    hosts = config.get("splunk_hosts") or []
    idxcs = config.get("splunk_idxclusters") or []
    has_site = any(isinstance(host, Mapping) and host.get("site") for host in hosts)
    has_site_rf = any(
        isinstance(cluster, Mapping) and cluster.get("idxc_site_rf") for cluster in idxcs
    )
    return {
        "clustering": bool(idxcs),
        "search_head_cluster": bool(config.get("splunk_shclusters")),
        "multisite": bool(has_site or has_site_rf),
    }


def _check_clusters(
    config: Mapping[str, Any], clusters: Mapping[str, Any], mismatches: List[Dict[str, Any]]
) -> None:
    indexer = clusters.get("indexer") if isinstance(clusters.get("indexer"), Mapping) else None
    if indexer:
        rows = config.get("splunk_idxclusters") or []
        found = _cluster_row(list(rows), "idxc_name", indexer.get("name")) if rows else {}
        _eq(mismatches, "clusters.indexer.name", indexer.get("name"), found.get("idxc_name"))
        _eq(
            mismatches,
            "clusters.indexer.replication_port",
            indexer.get("replication_port"),
            found.get("idxc_replication_port"),
        )
        if indexer.get("replication_factor") is not None:
            _eq(
                mismatches,
                "clusters.indexer.replication_factor",
                indexer.get("replication_factor"),
                found.get("idxc_rf"),
            )
        if indexer.get("search_factor") is not None:
            _eq(
                mismatches,
                "clusters.indexer.search_factor",
                indexer.get("search_factor"),
                found.get("idxc_sf"),
            )
        site_rf = indexer.get("site_replication_factor")
        if isinstance(site_rf, Mapping):
            expected = "origin:%s, total:%s" % (site_rf.get("origin"), site_rf.get("total"))
            _eq(mismatches, "clusters.indexer.site_replication_factor", expected, found.get("idxc_site_rf"))
        site_sf = indexer.get("site_search_factor")
        if isinstance(site_sf, Mapping):
            expected = "origin:%s, total:%s" % (site_sf.get("origin"), site_sf.get("total"))
            _eq(mismatches, "clusters.indexer.site_search_factor", expected, found.get("idxc_site_sf"))
    search = clusters.get("search_head") if isinstance(clusters.get("search_head"), Mapping) else None
    if search:
        rows = config.get("splunk_shclusters") or []
        found = _cluster_row(list(rows), "shc_name", search.get("name")) if rows else {}
        _eq(mismatches, "clusters.search_head.name", search.get("name"), found.get("shc_name"))
        _eq(
            mismatches,
            "clusters.search_head.replication_port",
            search.get("replication_port"),
            found.get("shc_replication_port"),
        )


def _eq(mismatches: List[Dict[str, Any]], path: str, expected: Any, found: Any) -> None:
    if expected is None:
        return
    if found != expected:
        mismatches.append({"path": path, "expected": expected, "found": found})
