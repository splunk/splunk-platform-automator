"""Facts for the architecture host page at generate time."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from spa.licenses import scan_licenses
from spa.paths import SpaPaths, resolve_spa_paths


def snapshot_extras(paths: Optional[SpaPaths] = None) -> Dict[str, Any]:
    """Configured license rows and CCM TTL. Never GUID, path, or deployment id."""
    resolved = paths or resolve_spa_paths()
    return {
        "linkpage_licenses": _configured_licenses(resolved),
        "linkpage_ccm_ttl": _ccm_ttl(resolved.spa_env_dir),
    }


def _ccm_ttl(env_dir: Path) -> str:
    state_path = env_dir / "ccm" / "state.json"
    if not state_path.is_file():
        return ""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("ttl") or "")


def _configured_licenses(paths: SpaPaths) -> List[Dict[str, str]]:
    scan = scan_licenses(
        paths.spa_home,
        software_dir=str(paths.software_dir),
        config_path=paths.config_file,
        env_recommend=False,
    )
    discovered = {
        str(row.get("basename") or ""): row
        for row in (scan.get("discovered_files") or [])
        if isinstance(row, dict) and row.get("basename")
    }
    rows: List[Dict[str, str]] = []
    for name in scan.get("configured_splunk_license_file") or []:
        record = discovered.get(str(name)) or {}
        rows.append(
            {
                "basename": str(name),
                "expires_at": str(record.get("expires_at") or ""),
                "status": str(record.get("status") or "missing"),
            }
        )
    return rows
