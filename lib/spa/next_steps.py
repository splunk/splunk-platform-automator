"""Stable data.next items for agent AskQuestion follow-ups."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from spa.apps import CONTENT_LIBRARY_ID, ES_ID, ITSI_ID

LICENSE_MANAGER_FILE_WARNING = {
    "id": "license_manager.license_file",
    "message": (
        "license manager is set and no license file is configured; "
        "Splunk will run trial until files are added."
    ),
}
ITSI_LICENSE_FILE_WARNING = {
    "id": "itsi.license_file",
    "message": (
        "ITSI (1841) is configured without an ITSI license; "
        "Splunk will run it as IT Essentials Work until an ITSI license is added."
    ),
}


def item(
    ident: str,
    ask: str,
    command: Optional[str] = None,
    *,
    required: bool = False,
    argv: Optional[Sequence[str]] = None,
    choice: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": ident, "ask": ask, "required": bool(required)}
    if command:
        row["command"] = command
        row["argv"] = list(argv) if argv is not None else shlex.split(command)
    if choice:
        row["choice"] = dict(choice)
    return row


def suggested_roles_for_app(app_id: Optional[int]) -> List[str]:
    if app_id == 833:
        return ["universal_forwarder", "heavy_forwarder"]
    return []


def roles_on_hosts(config: Any) -> List[str]:
    if not isinstance(config, Mapping):
        return []
    seen = []
    for host in config.get("splunk_hosts") or []:
        if not isinstance(host, Mapping):
            continue
        for role in host.get("roles") or []:
            name = str(role).strip()
            if name and name not in seen:
                seen.append(name)
    return seen


def apps_add_next(
    *,
    kind: str,
    app_id: Optional[int],
    playbooks: Optional[Sequence[Any]] = None,
    customize: bool = False,
    content_packs: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    if kind == "premium_itsi" or app_id == ITSI_ID:
        return [
            item(
                "licenses.list",
                "Add license files? Without them Splunk is trial-only, and ITSI runs as IT Essentials Work.",
                "spa --agent licenses list",
                required=False,
            ),
            item(
                "apps.content-packs.list",
                "Add ITSI content packs? None, list the 5391 packs, or the operator names folders.",
                "spa --agent apps content-packs list %s" % CONTENT_LIBRARY_ID,
                choice={"allowed": ["none", "list", "name"]},
            ),
        ]
    if kind == "es_not_premium" or app_id == ES_ID:
        return [
            item(
                "licenses.list",
                "Add Enterprise + ES license files?",
                "spa --agent licenses list",
                required=True,
            ),
        ]
    rows: List[Dict[str, Any]] = []
    if playbooks and not customize:
        if content_packs:
            flags = " ".join("--content-pack %s" % pack for pack in content_packs)
            retry = "spa --agent apps add %s %s --customize --yes" % (
                app_id or "APP_ID",
                flags,
            )
        elif kind in {"itsi_content_library", "itsi_content_pack_single"}:
            retry = "spa --agent apps add %s --customize --yes" % (app_id or "APP_ID")
        else:
            retry = "spa --agent apps add %s --roles ROLE --customize --yes" % (
                app_id or "APP_ID"
            )
        rows.append(
            item(
                "apps.customize",
                "Add curated customizations with --customize?",
                retry,
            )
        )
    rows.append(item("apps.add.another", "Add another app?"))
    return rows


def license_file_prompt() -> Dict[str, Any]:
    return item(
        "config.set.license_file",
        "Add license files? Without them Splunk is trial-only, and ITSI runs as IT Essentials Work.",
        "spa --agent licenses list",
        required=False,
    )


def attach_license_file_next(payload: Dict[str, Any]) -> None:
    warning_ids = {
        item.get("id")
        for item in (payload.get("warnings") or [])
        if isinstance(item, Mapping)
    }
    if not warning_ids & {
        LICENSE_MANAGER_FILE_WARNING["id"],
        ITSI_LICENSE_FILE_WARNING["id"],
    }:
        return
    rows = list(payload.get("next") or [])
    if any(row.get("id") == "config.set.license_file" for row in rows):
        return
    payload["next"] = [license_file_prompt()] + rows


def licenses_list_next(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    proposed = [str(name) for name in (scan.get("proposed_splunk_license_file") or []) if name]
    if not proposed:
        return []
    import json

    unsatisfied = bool(scan.get("unsatisfied_requirements"))
    listed = json.dumps(proposed, separators=(",", ":"))
    return [
        item(
            "config.set.license_file",
            "Add proposed license files %s?" % ", ".join(proposed),
            "spa --agent config set splunk_defaults.splunk_license_file '%s' --yes" % listed,
            required=False,
        ),
        item(
            "license_manager.placement",
            "Where should license_manager live (dedicated mc vs co-locate on cm)?",
            "spa --agent config add 'splunk_hosts[name=mc]' "
            '\'{"roles":["monitoring_console","license_manager"]}\' --yes',
            required=unsatisfied,
        ),
    ]


def deploy_next(env_dir: str) -> List[Dict[str, Any]]:
    path = str((Path(env_dir) / "config" / "index.html").resolve())
    return [
        item(
            "hosts.linkpage",
            "Paste %s into a browser to log in to Splunk hosts." % path,
            required=False,
        )
    ]


def provision_next(env_name: Optional[str] = None) -> List[Dict[str, Any]]:
    env = env_name or "NAME"
    follow = "spa --env %s logs --follow --wait --ansible-output --color" % env
    return [
        item(
            "logs.follow",
            "In another terminal, follow native Ansible while deploy runs (optional).",
            follow,
            required=False,
        ),
        item(
            "deploy",
            "Deploy Splunk software?",
            "spa --agent deploy --yes",
        ),
    ]


def architecture_plan_next(
    plan: Mapping[str, Any],
    *,
    architecture_file: str,
    environ: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Path B: the architecture file is the plan (write mode), then provider."""
    from spa.providers import provider_ids
    from spa.providers.ccm import token_present

    allowed = list(provider_ids())
    if not token_present(environ):
        allowed = [name for name in allowed if name != "ccm"]
    init = (
        "spa --agent environment init PARENT/NAME --architecture %s --provider"
        % architecture_file
    )
    rows = [
        item(
            "mode.write",
            "Architecture file is the plan. After the location/name gate, "
            "run spa environment init PARENT/NAME --architecture FILE --provider. "
            "Do not ask plan vs write.",
            init,
            required=True,
        ),
        item(
            "provider",
            "Which provider?",
            choice={"allowed": allowed},
            required=True,
        ),
    ]
    remaining = [name for name in (plan.get("remaining") or []) if name != "provider"]
    rows.extend(remaining_next(remaining))
    return rows


def ccm_hardware_next() -> List[Dict[str, Any]]:
    """One OS, instance type, and disk for every CCM host. Not per role."""
    return [
        item(
            "ccm.operating_system",
            "Set one OS for all hosts? CCM has no per-host operating system.",
            "spa --agent config set ccm.operating_system OS --yes",
        ),
        item(
            "ccm.instance_type",
            "Set one instance type for all hosts? CCM has no per-host instance type.",
            "spa --agent config set ccm.instance_type TYPE --yes",
        ),
        item(
            "ccm.disk_storage",
            "Set one disk size for all hosts? CCM has no per-host disk.",
            "spa --agent config set ccm.disk_storage SIZE --yes",
        ),
    ]


def remaining_next(remaining: Iterable[str]) -> List[Dict[str, Any]]:
    mapping = {
        "apps": item("apps.search", "Add apps?", "spa --agent apps search QUERY"),
        "licenses": item(
            "licenses.list",
            "Scan Software licenses?",
            "spa --agent licenses list",
            required=True,
        ),
        "license_manager": item(
            "license_manager.placement",
            "Where should license_manager live (dedicated mc vs co-locate on cm)?",
            "spa --agent config add 'splunk_hosts[name=mc]' "
            '\'{"roles":["monitoring_console","license_manager"]}\' --yes',
        ),
    }
    return [mapping[name] for name in remaining if name in mapping]
