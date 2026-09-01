#!/usr/bin/env python3
"""
Discover Splunk license files in the Software directory and propose splunk_license_file.

Files must live in splunk_software_dir (default ../Software relative to repo root).
SPA references licenses by basename only (e.g. Splunk_Enterprise.lic).

Examples:
  python3 bin/splunk_config_licenses.py --json
  python3 bin/splunk_config_licenses.py --config config/splunk_config.yml --json
  python3 bin/splunk_config_licenses.py --software-dir ../Software --propose --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ENTERPRISE_CANONICAL = "Splunk_Enterprise.lic"
ITSI_CANONICAL = "Splunk_ITSI.lic"
LICENSE_SUFFIXES = (".lic", ".license")


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _output(data: Any, as_json: bool) -> None:
    print(json.dumps(data, indent=2, default=str))


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_software_dir(project_root: Path, explicit: Optional[str] = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (project_root / path).resolve()
        return path.resolve()
    for candidate in (project_root / "../Software", project_root / "Software"):
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    return (project_root / "../Software").resolve()


def is_license_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in LICENSE_SUFFIXES


def discover_license_files(software_dir: Path) -> List[Dict[str, Any]]:
    if not software_dir.is_dir():
        return []
    items: List[Dict[str, Any]] = []
    for entry in sorted(software_dir.iterdir(), key=lambda p: p.name.lower()):
        if not is_license_file(entry):
            continue
        items.append(
            {
                "basename": entry.name,
                "path": str(entry.resolve()),
                "size_bytes": entry.stat().st_size,
            }
        )
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
    """Lightweight scan when PyYAML is unavailable — ITSI / LM / license file hints only."""
    text = path.read_text(encoding="utf-8", errors="replace")
    itsi = bool(
        re.search(r"premium_app:\s*itsi\b", text, re.I)
        or re.search(r"app_id:\s*1841\b", text)
        or re.search(r"itsi_content_pack:\s*true", text, re.I)
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


def config_has_itsi(config: Dict[str, Any]) -> bool:
    dep = config.get("splunk_app_deployment") or {}
    apps = dep.get("apps") or []
    for app in apps:
        if not isinstance(app, dict):
            continue
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


def propose_license_files(
    discovered: List[Dict[str, Any]],
    itsi_in_config: bool,
    lab_recommend: bool = True,
) -> Dict[str, Any]:
    reasons: List[str] = []
    proposed: List[str] = []

    enterprise = pick_canonical(discovered, ENTERPRISE_CANONICAL, "enterprise")
    if enterprise:
        proposed.append(enterprise)
        reasons.append(f"Enterprise license found in Software: {enterprise}")

    if itsi_in_config:
        itsi = pick_canonical(discovered, ITSI_CANONICAL, "itsi")
        if itsi:
            if itsi not in proposed:
                proposed.append(itsi)
            reasons.append(f"ITSI in config — include ITSI license: {itsi}")
        else:
            reasons.append("ITSI in config but no ITSI license file found in Software (expected Splunk_ITSI.lic)")
    elif lab_recommend:
        itsi = pick_canonical(discovered, ITSI_CANONICAL, "itsi")
        if itsi and itsi not in proposed:
            reasons.append(f"Optional: {itsi} found in Software (not required unless ITSI is deployed)")

    return {
        "proposed_splunk_license_file": proposed,
        "reasons": reasons,
        "enterprise_license": enterprise,
        "itsi_license": pick_canonical(discovered, ITSI_CANONICAL, "itsi") if itsi_in_config else None,
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


def scan_licenses(
    project_root: Path,
    software_dir: Optional[str] = None,
    config_path: Optional[Path] = None,
    lab_recommend: bool = True,
) -> Dict[str, Any]:
    sw_dir = resolve_software_dir(project_root, software_dir)
    discovered = discover_license_files(sw_dir)

    itsi_in_config = False
    has_lm = False
    configured: Optional[List[str]] = None
    config_error: Optional[str] = None
    config_scan_mode: Optional[str] = None

    if config_path and config_path.is_file():
        try:
            if yaml is not None:
                config = load_config(config_path)
                itsi_in_config = config_has_itsi(config)
                has_lm = config_has_license_manager(config)
                configured = current_license_files(config)
                config_scan_mode = "yaml"
            else:
                scanned = scan_config_text(config_path)
                itsi_in_config = scanned["itsi_in_config"]
                has_lm = scanned["license_manager_in_config"]
                configured = scanned["configured_splunk_license_file"]
                config_scan_mode = scanned["config_scan_mode"]
        except Exception as exc:
            config_error = str(exc)
            config_scan_mode = None

    proposal = propose_license_files(discovered, itsi_in_config, lab_recommend=lab_recommend)

    result: Dict[str, Any] = {
        "ok": sw_dir.is_dir(),
        "software_dir": str(sw_dir),
        "software_dir_exists": sw_dir.is_dir(),
        "discovered_files": discovered,
        "itsi_in_config": itsi_in_config,
        "license_manager_in_config": has_lm,
        "configured_splunk_license_file": configured,
        **proposal,
        "yaml_snippet": build_yaml_snippet(proposal["proposed_splunk_license_file"]),
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

    if itsi_in_config and proposal.get("itsi_license") is None:
        result["warnings"] = result.get("warnings", []) + [
            "ITSI in config but Splunk_ITSI.lic not found in Software directory."
        ]

    if not discovered and lab_recommend:
        result["warnings"] = result.get("warnings", []) + [
            "No .lic files in Software — lab deploy may use trial license only, or add licenses to ../Software."
        ]

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Discover Splunk licenses in Software and propose splunk_license_file")
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument(
        "--software-dir",
        help="Software directory (default: ../Software from repo root, SPA splunk_software_dir)",
    )
    p.add_argument("--config", help="splunk_config.yml path to detect ITSI and current license settings")
    p.add_argument(
        "--no-lab-recommend",
        action="store_true",
        help="Do not mention optional licenses when ITSI is not in config",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    project_root = repo_root_from_script()
    config_path = None
    if args.config:
        config_path = Path(args.config).expanduser()
        if not config_path.is_absolute():
            config_path = (project_root / config_path).resolve()

    try:
        result = scan_licenses(
            project_root,
            software_dir=args.software_dir,
            config_path=config_path,
            lab_recommend=not args.no_lab_recommend,
        )
    except Exception as exc:
        _err(str(exc))
        return 1

    _output(result, args.json)
    return 0 if result.get("software_dir_exists") or result.get("discovered_files") else 0


if __name__ == "__main__":
    sys.exit(main())
