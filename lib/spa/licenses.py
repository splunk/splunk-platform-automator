#!/usr/bin/env python3
"""
Discover Splunk license files in the Software directory and propose splunk_license_file.

Files must live in splunk_software_dir (default ../Software relative to SPA_ENV_DIR).
SPA references licenses by basename only (e.g. Splunk_Enterprise.lic).

Examples:
  spa licenses --json
  spa licenses --config config/splunk_config.yml --json
  spa licenses --software-dir ../Software --propose --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ENTERPRISE_CANONICAL = "Splunk_Enterprise.lic"
ITSI_CANONICAL = "Splunk_ITSI.lic"
ES_CANONICAL = "Splunk_ES.lic"
LICENSE_SUFFIXES = (".lic", ".license")
MAX_LICENSE_BYTES = 5 * 1024 * 1024

EXPIRATION_FIELDS = (
    "expiration_time",
    "expiration",
    "expires_at",
    "expiry",
    "expiry_time",
)
CREATION_FIELDS = ("creation_time", "created_at", "issue_time", "issued_at")
TYPE_FIELDS = ("type", "license_type")
GROUP_FIELDS = ("group_id", "group")

ADDON_ALIASES = {
    "itsi": ("itsi", "it service intelligence", "sa-itoa"),
    "es": ("es", "splunk es", "enterprise security", "splunkenterprisesecuritysuite"),
}


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _output(data: Any, as_json: bool) -> None:
    print(json.dumps(data, indent=2, default=str))


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_env_root(project_root: Optional[Path] = None) -> Path:
    """Env root (SPA_ENV_DIR). Software may still fall back to the clone sibling."""
    try:
        from spa.paths import resolve_spa_paths
    except ImportError:
        return (project_root or repo_root_from_script()).resolve()
    return resolve_spa_paths().spa_env_dir


def resolve_software_dir(project_root: Path, explicit: Optional[str] = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (project_root / path).resolve()
        return path.resolve()
    try:
        from spa.paths import resolve_spa_paths
        return resolve_spa_paths().software_dir
    except ImportError:
        pass
    for candidate in (project_root / "../Software", project_root / "Software"):
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    return (project_root / "../Software").resolve()


def is_license_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in LICENSE_SUFFIXES


def _local_name(tag: str) -> str:
    """Return an XML local name without a namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def _element_values(root: ET.Element, names: Iterable[str]) -> List[str]:
    wanted = {name.lower() for name in names}
    values = []
    for elem in root.iter():
        if _local_name(elem.tag) not in wanted:
            continue
        text = (elem.text or "").strip()
        if text:
            values.append(text)
    return values


def _first_element_value(root: ET.Element, names: Iterable[str]) -> Optional[str]:
    values = _element_values(root, names)
    return values[0] if values else None


def _parse_time(value: Optional[str]) -> tuple:
    """Return (UTC ISO value, epoch seconds, perpetual) for a license time."""
    if value is None or not value.strip():
        return None, None, False
    raw = value.strip()
    if raw.lower() in {"never", "perpetual", "none", "unlimited"}:
        return None, None, True
    try:
        epoch = float(raw)
        if epoch == 0:
            return None, None, True
        # Be tolerant of millisecond timestamps.
        if epoch > 100_000_000_000:
            epoch /= 1000
        parsed = datetime.fromtimestamp(epoch, tz=timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z"), epoch, False
    except (OverflowError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z"), parsed.timestamp(), False
    except ValueError:
        return None, None, False


def _normalize_addons(root: ET.Element) -> List[str]:
    values: Set[str] = set()
    for elem in root.iter():
        local = _local_name(elem.tag)
        if "add_on" not in local and "addon" not in local:
            continue
        for nested in elem.iter():
            text = (nested.text or "").strip()
            if text:
                values.add(text)
            for key in ("name", "id", "type"):
                attr = (nested.attrib.get(key) or "").strip()
                if attr:
                    values.add(attr)

    normalized: Set[str] = set()
    for value in values:
        folded = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        compact = folded.replace(" ", "")
        for capability, aliases in ADDON_ALIASES.items():
            normalized_aliases = [
                re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip() for alias in aliases
            ]
            matches = False
            for alias in normalized_aliases:
                alias_compact = alias.replace(" ", "")
                if len(alias_compact) <= 3:
                    matches = folded == alias or compact == alias_compact
                else:
                    matches = alias in folded or alias_compact in compact
                if matches:
                    break
            if matches:
                normalized.add(capability)
    return sorted(normalized)


def _license_capabilities(license_type: Optional[str], group_id: Optional[str], addons: List[str]) -> List[str]:
    capabilities = set(addons)
    type_value = (license_type or "").lower()
    group_value = (group_id or "").lower()
    # "Enterprise Security" is an add-on, not proof of the Enterprise base
    # entitlement. Prefer type and accept only non-ES Enterprise group names.
    enterprise_type = "enterprise" in type_value and "security" not in type_value
    enterprise_group = "enterprise" in group_value and "security" not in group_value
    if enterprise_type or enterprise_group:
        capabilities.add("enterprise")
    return sorted(capabilities)


def parse_license_file(path: Path, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Parse a license without exposing its signature, GUID, or raw payload."""
    stat = path.stat()
    result: Dict[str, Any] = {
        "basename": path.name,
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
    }
    try:
        if stat.st_size > MAX_LICENSE_BYTES:
            raise ValueError("license file exceeds %s bytes" % MAX_LICENSE_BYTES)
        raw = path.read_bytes()
        upper = raw[:4096].upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ValueError("XML declarations with DTD/entities are not allowed")
        root = ET.fromstring(raw)
        payload = next((elem for elem in root.iter() if _local_name(elem.tag) == "payload"), root)
        license_type = _first_element_value(payload, TYPE_FIELDS)
        group_id = _first_element_value(payload, GROUP_FIELDS)
        expiration_raw = _first_element_value(payload, EXPIRATION_FIELDS)
        creation_raw = _first_element_value(payload, CREATION_FIELDS)
        expires_at, expires_epoch, perpetual = _parse_time(expiration_raw)
        created_at, _, _ = _parse_time(creation_raw)
        addons = _normalize_addons(payload)
        current = now or datetime.now(timezone.utc)
        current_epoch = current.astimezone(timezone.utc).timestamp()
        if perpetual:
            status = "perpetual"
        elif expires_epoch is None:
            status = "unknown-expiration"
        elif expires_epoch <= current_epoch:
            status = "expired"
        elif expires_epoch <= current_epoch + (30 * 86400):
            status = "expiring"
        else:
            status = "valid"
        result.update(
            {
                "license_type": license_type,
                "group_id": group_id,
                "addons": addons,
                "capabilities": _license_capabilities(license_type, group_id, addons),
                "created_at": created_at,
                "expires_at": expires_at,
                "status": status,
                "_expires_epoch": expires_epoch,
            }
        )
    except (ET.ParseError, OSError, ValueError) as exc:
        result.update(
            {
                "license_type": None,
                "group_id": None,
                "addons": [],
                "capabilities": [],
                "created_at": None,
                "expires_at": None,
                "status": "invalid",
                "parse_error": str(exc),
                "_expires_epoch": None,
            }
        )
    return result


def _public_license(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal ranking fields from CLI/agent output."""
    return {key: value for key, value in record.items() if not key.startswith("_")}


def discover_license_files(software_dir: Path) -> List[Dict[str, Any]]:
    if not software_dir.is_dir():
        return []
    items: List[Dict[str, Any]] = []
    for entry in sorted(software_dir.iterdir(), key=lambda p: p.name.lower()):
        if not is_license_file(entry):
            continue
        items.append(parse_license_file(entry))
    return items


def _name_matches(name: str, pattern: str) -> bool:
    return pattern.lower() in name.lower()


def pick_canonical(discovered: List[Dict[str, Any]], canonical: str, fallback_pattern: str) -> Optional[str]:
    basenames = [d["basename"] for d in discovered]
    if canonical in basenames:
        return canonical
    for basename in basenames:
        if _name_matches(basename, fallback_pattern):
            return basename
    return None


def scan_config_text(path: Path) -> Dict[str, Any]:
    """Lightweight scan when PyYAML is unavailable — app / LM / license hints only."""
    text = path.read_text(encoding="utf-8", errors="replace")
    itsi = bool(
        re.search(r"premium_app:\s*itsi\b", text, re.I)
        or re.search(r"app_id:\s*1841\b", text)
        or re.search(r"itsi_content_pack:\s*true", text, re.I)
    )
    es = bool(
        re.search(r"premium_app:\s*(?:es|enterprise_security)\b", text, re.I)
        or re.search(r"app_id:\s*263\b", text)
        or re.search(r"name:\s*[\"']?Splunk Enterprise Security\b", text, re.I)
    )
    has_lm = bool(re.search(r"-\s*license_manager\b", text) or re.search(r"roles:.*license_manager", text))

    configured: Optional[List[str]] = None
    license_names: List[str] = []
    in_license_list = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(r"^\s*splunk_license_file:\s*$", line):
            in_license_list = True
            continue
        scalar = re.match(r"^\s*splunk_license_file:\s+(.+)$", line)
        if scalar:
            in_license_list = False
            license_names.append(scalar.group(1).strip().strip('"').strip("'"))
            continue
        if in_license_list:
            item = re.match(r"^\s*-\s*['\"]?([^'\"]+)['\"]?\s*$", line)
            if item:
                license_names.append(item.group(1).strip())
                continue
            if stripped and not line.startswith((" ", "\t")):
                in_license_list = False
    if license_names:
        configured = license_names

    return {
        "itsi_in_config": itsi,
        "es_in_config": es,
        "license_manager_in_config": has_lm,
        "configured_splunk_license_file": configured,
        "config_scan_mode": "text",
    }


def load_config(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required. Install with: pip install PyYAML")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


def _installed_apps(config: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    dep = config.get("splunk_app_deployment") or {}
    for app in dep.get("apps") or []:
        if isinstance(app, dict) and str(app.get("state", "installed")).strip().lower() != "absent":
            yield app


def config_has_itsi(config: Dict[str, Any]) -> bool:
    for app in _installed_apps(config):
        if app.get("itsi_content_pack"):
            return True
        premium = (app.get("premium_app") or "").strip().lower()
        if premium == "itsi":
            return True
        app_id = str(app.get("app_id", "")).strip()
        if app_id == "1841":
            return True
        name = (app.get("name") or "").lower()
        if "itsi" in name or "it service intelligence" in name:
            return True
    return False


def config_has_es(config: Dict[str, Any]) -> bool:
    """Detect ES as a selected app without claiming premium_app: es support."""
    for app in _installed_apps(config):
        premium = (app.get("premium_app") or "").strip().lower()
        if premium in {"es", "enterprise_security", "enterprise-security"}:
            return True
        if str(app.get("app_id", "")).strip() == "263":
            return True
        name = (app.get("name") or "").strip().lower()
        if name in {"splunk enterprise security", "splunkenterprisesecuritysuite"}:
            return True
    return False


def required_capabilities(itsi_in_config: bool, es_in_config: bool) -> List[str]:
    required = ["enterprise"]
    if itsi_in_config:
        required.append("itsi")
    if es_in_config:
        required.append("es")
    return required


def config_has_license_manager(config: Dict[str, Any]) -> bool:
    for host in config.get("splunk_hosts") or []:
        roles = host.get("roles") or []
        if "license_manager" in roles:
            return True
    return False


def current_license_files(config: Dict[str, Any]) -> Optional[List[str]]:
    defaults = config.get("splunk_defaults") or {}
    raw = defaults.get("splunk_license_file")
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return None


def _candidate_rank(record: Dict[str, Any], required: Set[str], canonical: str) -> tuple:
    status_rank = {
        "perpetual": 4,
        "valid": 3,
        "expiring": 2,
        "unknown-expiration": 1,
    }.get(record.get("status"), 0)
    capabilities = set(record.get("capabilities") or [])
    return (
        status_rank,
        record.get("_expires_epoch") or 0,
        len(capabilities & required),
        record.get("basename") == canonical,
        record.get("basename", ""),
    )


def _select_for_capability(
    discovered: List[Dict[str, Any]], capability: str, required: Set[str]
) -> Optional[Dict[str, Any]]:
    canonical = {
        "enterprise": ENTERPRISE_CANONICAL,
        "itsi": ITSI_CANONICAL,
        "es": ES_CANONICAL,
    }[capability]
    candidates = [
        record
        for record in discovered
        if capability in (record.get("capabilities") or [])
        and record.get("status") not in {"expired", "invalid"}
    ]
    return max(candidates, key=lambda record: _candidate_rank(record, required, canonical)) if candidates else None


def propose_license_files(
    discovered: List[Dict[str, Any]],
    itsi_in_config: bool,
    es_in_config: bool = False,
    env_recommend: bool = True,
) -> Dict[str, Any]:
    reasons: List[str] = []
    proposed: List[str] = []
    required = set(required_capabilities(itsi_in_config, es_in_config))
    selected: List[Dict[str, Any]] = []

    for capability in ("enterprise", "itsi", "es"):
        if capability not in required:
            continue
        existing = next(
            (record for record in selected if capability in (record.get("capabilities") or [])),
            None,
        )
        if existing is not None:
            reasons.append(
                "%s requirement also satisfied by %s"
                % (capability.upper(), existing["basename"])
            )
            continue
        candidate = _select_for_capability(discovered, capability, required)
        if candidate is None:
            reasons.append("No usable license satisfies required capability: %s" % capability)
            continue
        if candidate not in selected:
            selected.append(candidate)
            proposed.append(candidate["basename"])
        reasons.append(
            "%s requirement satisfied by %s (%s)"
            % (capability.upper(), candidate["basename"], candidate["status"])
        )

    unsatisfied = [
        capability
        for capability in sorted(required)
        if not any(capability in (record.get("capabilities") or []) for record in selected)
    ]

    if env_recommend:
        optional = sorted(
            {
                capability
                for record in discovered
                if record.get("status") not in {"expired", "invalid"}
                for capability in (record.get("capabilities") or [])
                if capability in {"itsi", "es"} and capability not in required
            }
        )
        if optional:
            reasons.append(
                "Optional add-on license(s) found but not selected by config: %s"
                % ", ".join(optional)
            )

    return {
        "proposed_splunk_license_file": proposed,
        "reasons": reasons,
        "required_capabilities": sorted(required),
        "unsatisfied_requirements": unsatisfied,
        "selected_licenses": [_public_license(record) for record in selected],
        "enterprise_license": next(
            (r["basename"] for r in selected if "enterprise" in (r.get("capabilities") or [])),
            None,
        ),
        "itsi_license": next(
            (r["basename"] for r in selected if "itsi" in (r.get("capabilities") or [])),
            None,
        ),
        "es_license": next(
            (r["basename"] for r in selected if "es" in (r.get("capabilities") or [])),
            None,
        ),
    }


def build_yaml_snippet(proposed: List[str]) -> str:
    if not proposed:
        return "# splunk_license_file: Splunk_Enterprise.lic  # place file in ../Software"
    if len(proposed) == 1:
        return f"splunk_license_file: {proposed[0]}"
    lines = ["splunk_license_file:"]
    for name in proposed:
        lines.append(f"  - {name}")
    return "\n".join(lines)


def validate_configured_license_files(
    discovered: List[Dict[str, Any]],
    configured: Optional[List[str]],
    required: Iterable[str],
    enforce_requirements: bool,
) -> Dict[str, List[str]]:
    """Validate configured files against parsed capability and expiry metadata."""
    errors: List[str] = []
    warnings: List[str] = []
    by_name = {record["basename"]: record for record in discovered}
    selected = []

    for name in configured or []:
        record = by_name.get(name)
        if record is None:
            errors.append("Configured license file not found in Software: %s" % name)
            continue
        selected.append(record)
        status = record.get("status")
        if status == "invalid":
            errors.append("Configured license is not valid XML: %s" % name)
        elif status == "expired":
            errors.append(
                "Configured license expired%s: %s"
                % (" on " + record["expires_at"] if record.get("expires_at") else "", name)
            )
        elif status == "expiring":
            warnings.append("Configured license expires soon on %s: %s" % (record["expires_at"], name))
        elif status == "unknown-expiration":
            warnings.append("Could not determine license expiration: %s" % name)

    if enforce_requirements:
        capabilities = {
            capability
            for record in selected
            if record.get("status") not in {"invalid", "expired"}
            for capability in (record.get("capabilities") or [])
        }
        for capability in required:
            if capability not in capabilities:
                errors.append(
                    "Configured license files do not provide required capability: %s" % capability
                )
    return {"errors": errors, "warnings": warnings}


def scan_licenses(
    project_root: Path,
    software_dir: Optional[str] = None,
    config_path: Optional[Path] = None,
    env_recommend: bool = True,
) -> Dict[str, Any]:
    sw_dir = resolve_software_dir(project_root, software_dir)
    discovered = discover_license_files(sw_dir)

    itsi_in_config = False
    es_in_config = False
    has_lm = False
    configured: Optional[List[str]] = None
    config_error: Optional[str] = None
    config_scan_mode: Optional[str] = None

    if config_path and config_path.is_file():
        try:
            if yaml is not None:
                config = load_config(config_path)
                itsi_in_config = config_has_itsi(config)
                es_in_config = config_has_es(config)
                has_lm = config_has_license_manager(config)
                configured = current_license_files(config)
                config_scan_mode = "yaml"
            else:
                scanned = scan_config_text(config_path)
                itsi_in_config = scanned["itsi_in_config"]
                es_in_config = scanned["es_in_config"]
                has_lm = scanned["license_manager_in_config"]
                configured = scanned["configured_splunk_license_file"]
                config_scan_mode = scanned["config_scan_mode"]
        except Exception as exc:
            config_error = str(exc)
            config_scan_mode = None

    proposal = propose_license_files(
        discovered,
        itsi_in_config,
        es_in_config=es_in_config,
        env_recommend=env_recommend,
    )
    configured_validation = validate_configured_license_files(
        discovered,
        configured,
        proposal["required_capabilities"],
        enforce_requirements=bool(configured or has_lm or itsi_in_config or es_in_config),
    )
    recommended_additions = [
        name
        for name in proposal["proposed_splunk_license_file"]
        if name not in (configured or [])
    ]
    if configured and recommended_additions:
        configured_validation["warnings"].append(
            "Recommended license candidate(s) not currently configured: %s. "
            "Review before replacing files; additional commercial licenses may be stackable."
            % ", ".join(recommended_additions)
        )

    result: Dict[str, Any] = {
        "ok": sw_dir.is_dir(),
        "software_dir": str(sw_dir),
        "software_dir_exists": sw_dir.is_dir(),
        "discovered_files": [_public_license(record) for record in discovered],
        "itsi_in_config": itsi_in_config,
        "es_in_config": es_in_config,
        "license_manager_in_config": has_lm,
        "configured_splunk_license_file": configured,
        **proposal,
        "yaml_snippet": build_yaml_snippet(proposal["proposed_splunk_license_file"]),
        "license_validation": configured_validation,
        "recommended_additions": recommended_additions,
    }

    if config_error:
        result["config_read_error"] = config_error

    if config_scan_mode:
        result["config_scan_mode"] = config_scan_mode
        if config_scan_mode == "text":
            result["warnings"] = result.get("warnings", []) + [
                "Config scanned via text fallback (install PyYAML for full parse)."
            ]

    if itsi_in_config and not has_lm:
        result["warnings"] = result.get("warnings", []) + [
            "ITSI requires license_manager role on a host (schema validation)."
        ]

    if es_in_config and not has_lm:
        result["warnings"] = result.get("warnings", []) + [
            "Enterprise Security is selected but no license_manager role is configured."
        ]

    if configured and not has_lm:
        result["warnings"] = result.get("warnings", []) + [
            "splunk_license_file is set but no license_manager role on any host — "
            "add license_manager to a host (for example co-locate on cm or mc) or remove "
            "splunk_license_file for trial-only labs (schema validation)."
        ]

    if has_lm and not configured:
        result["warnings"] = result.get("warnings", []) + [
            "license_manager role is set but splunk_license_file is missing from splunk_defaults "
            "(schema validation)."
        ]

    for capability in proposal.get("unsatisfied_requirements") or []:
        result["warnings"] = result.get("warnings", []) + [
            "No non-expired, parseable license provides required capability: %s." % capability
        ]

    if not discovered and env_recommend:
        result["warnings"] = result.get("warnings", []) + [
            "No .lic files in Software — lab deploy may use trial license only, or add licenses to ../Software."
        ]

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spa licenses",
        description=(
            "Inspect Splunk license type, expiration, and add-ons; "
            "propose splunk_license_file for the selected apps"
        ),
    )
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument(
        "--software-dir",
        help="Software directory (default: ../Software from SPA_ENV_DIR, SPA splunk_software_dir)",
    )
    p.add_argument(
        "--config",
        help="splunk_config.yml path to detect ITSI/ES and validate current license settings",
    )
    p.add_argument(
        "--no-env-recommend",
        dest="no_env_recommend",
        action="store_true",
        help="Do not mention optional licenses when ITSI is not in config",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = resolve_env_root()
    config_path = None
    if args.config:
        config_path = Path(args.config).expanduser()
        if not config_path.is_absolute():
            config_path = (Path.cwd() / config_path).resolve()
            if not config_path.is_file():
                config_path = (repo_root_from_script() / args.config).resolve()

    try:
        result = scan_licenses(
            project_root,
            software_dir=args.software_dir,
            config_path=config_path,
            env_recommend=not args.no_env_recommend,
        )
    except Exception as exc:
        _err(str(exc))
        return 1

    _output(result, args.json)
    return 0 if result.get("software_dir_exists") or result.get("discovered_files") else 0


if __name__ == "__main__":
    sys.exit(main())
