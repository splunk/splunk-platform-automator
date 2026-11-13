"""Stable data.next items for agent AskQuestion follow-ups."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from spa.apps import CONTENT_LIBRARY_ID, ES_ID, ITSI_ID

JAVA_21_RHEL = "java-21-openjdk"
JAVA_21_DEBIAN = "openjdk-21-jdk"
_DEBIAN_OS_MARKERS = ("ubuntu", "debian", "policykit-1")

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


def _os_blob(config: Mapping[str, Any]) -> str:
    parts: List[str] = []
    ccm = config.get("ccm")
    if isinstance(ccm, Mapping) and ccm.get("operating_system"):
        parts.append(str(ccm["operating_system"]))
    terraform = config.get("terraform")
    aws = terraform.get("aws") if isinstance(terraform, Mapping) else None
    if isinstance(aws, Mapping):
        for key in ("ssh_username", "ami_name", "ami_id"):
            if aws.get(key):
                parts.append(str(aws[key]))
    os_cfg = config.get("os")
    if isinstance(os_cfg, Mapping):
        for package in os_cfg.get("packages") or []:
            parts.append(str(package))
    virtualbox = config.get("virtualbox")
    if isinstance(virtualbox, Mapping):
        for key in ("box", "image"):
            if virtualbox.get(key):
                parts.append(str(virtualbox[key]))
    return " ".join(parts).lower()


def java_package_for_config(config: Optional[Mapping[str, Any]]) -> str:
    """Java 21 package for the guest family. RHEL/AL default; Ubuntu/Debian otherwise."""
    if isinstance(config, Mapping) and any(
        marker in _os_blob(config) for marker in _DEBIAN_OS_MARKERS
    ):
        return JAVA_21_DEBIAN
    return JAVA_21_RHEL


def search_head_packages_selector(config: Optional[Mapping[str, Any]]) -> Optional[str]:
    """First search-head host selector for os.packages. Never the global os block."""
    if not isinstance(config, Mapping):
        return None
    for index, host in enumerate(config.get("splunk_hosts") or []):
        if not isinstance(host, Mapping):
            continue
        roles = [str(role) for role in (host.get("roles") or [])]
        if "search_head" not in roles:
            continue
        if host.get("name"):
            return "splunk_hosts[name=%s].os.packages" % host["name"]
        iteration = host.get("iter")
        if isinstance(iteration, Mapping) and iteration.get("prefix"):
            return "splunk_hosts[iter.prefix=%s].os.packages" % iteration["prefix"]
        return "splunk_hosts[%s].os.packages" % index
    return None


def _java_search_heads_next(config: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    selector = search_head_packages_selector(config)
    if not selector:
        return None
    package = java_package_for_config(config)
    listed = json.dumps([package], separators=(",", ":"))
    command = "spa --agent config set %s %s --yes" % (
        shlex.quote(selector),
        shlex.quote(listed),
    )
    return item(
        "os.java.search_heads",
        "Install Java 21 on search-head hosts only (%s)? Do not set global os.packages."
        % package,
        command,
    )


def apps_add_next(
    *,
    kind: str,
    app_id: Optional[int],
    playbooks: Optional[Sequence[Any]] = None,
    customize: bool = False,
    content_packs: Optional[Sequence[str]] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if kind == "premium_itsi" or app_id == ITSI_ID:
        rows: List[Dict[str, Any]] = []
        java = _java_search_heads_next(config)
        if java:
            rows.append(java)
        rows.extend(
            [
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
        )
        return rows
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
                "Configure / set up / customize this app with --customize? "
                "That flag does not change target_roles.",
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


def hosts_status_next(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """When any host is unprovisioned, deploy creates them. Do not provision separately."""
    rows = [
        row
        for row in (report.get("hosts") or [])
        if isinstance(row, Mapping)
        and (
            row.get("ansible") == "unprovisioned"
            or row.get("provider_status") == "unprovisioned"
        )
    ]
    if not rows:
        return []
    return [
        item(
            "deploy",
            "Hosts are not created yet. spa deploy creates them and installs Splunk. "
            "Do not run a separate provision step.",
            "spa --agent deploy --yes",
        )
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
