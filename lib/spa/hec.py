"""Dest names and deployment-server grouping for the HEC baseconfig app."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


_ROLE_INFIX = (
    ("indexer", "idx"),
    ("heavy_forwarder", "hf"),
    ("search_head", "sh"),
)


def hec_listening_infix(roles: Optional[Iterable[Any]], app_infix: Optional[str] = None) -> str:
    """Infix for the installed app: row app_infix, else the listening role."""
    if app_infix:
        return str(app_infix)
    values = [str(getattr(role, "value", role)) for role in roles or []]
    for role, infix in _ROLE_INFIX:
        if role in values:
            return infix
    return "all"


def hec_dest_name(prefix: str, infix: str) -> str:
    """Installed app name from org_all_hec_inputs after prefix and infix replace."""
    return "%s_%s_hec_inputs" % (prefix, infix)


def hec_ds_apps(
    clients: Sequence[Any],
    host_hec: Mapping[str, Any],
    host_roles: Mapping[str, Any],
    hec_rows: Mapping[str, Any],
    prefix: str,
) -> List[Dict[str, Any]]:
    """Group DS clients by dest app (hec_name + infix)."""
    apps: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    for item in clients or []:
        client = item["server"] if isinstance(item, Mapping) else item
        hec_name = host_hec.get(client)
        if not hec_name:
            continue
        row = hec_rows.get(hec_name) or {}
        infix = hec_listening_infix(host_roles.get(client) or [], row.get("app_infix"))
        dest = hec_dest_name(prefix, infix)
        if dest not in index:
            entry = {"dest": dest, "hec_name": hec_name, "infix": infix, "clients": []}
            index[dest] = entry
            apps.append(entry)
        index[dest]["clients"].append(client)
    return apps
