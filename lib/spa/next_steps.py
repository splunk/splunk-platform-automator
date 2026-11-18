"""Stable data.next items for agent AskQuestion follow-ups."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

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


CONTENT_PACK_API_ASKS = (
    (
        "enabled",
        "Enable all objects in this content pack? Default is false.",
        "true",
        None,
    ),
    (
        "saved_search_action",
        "Saved search action for this content pack?",
        "disable",
        {"allowed": ["disable", "enable"]},
    ),
    (
        "backfill",
        "Backfill this content pack?",
        "true",
        None,
    ),
    (
        "resolution",
        "Resolution when objects already exist?",
        "overwrite",
        {"allowed": ["overwrite", "skip"]},
    ),
    (
        "prefix",
        "Object-name prefix for this content pack (ITSI GUI Prefix)? "
        "Default is empty. Skip to omit, or replace PREFIX in the command.",
        "PREFIX",
        None,
    ),
)


def _pack_items(
    entry: Optional[Mapping[str, Any]], content_packs: Sequence[str]
) -> List[Mapping[str, Any]]:
    items = {
        str(item.get("name")): item
        for item in ((entry or {}).get("content_pack_apps") or [])
        if isinstance(item, Mapping)
    }
    rows: List[Mapping[str, Any]] = []
    for name in content_packs:
        pack = items.get(str(name))
        if isinstance(pack, Mapping):
            rows.append(pack)
    return rows


def _pack_install_yes(pack: Mapping[str, Any]) -> bool:
    return pack.get("content_pack_install") is True


def _named_packs_install_yes(
    entry: Optional[Mapping[str, Any]], content_packs: Sequence[str]
) -> bool:
    if not content_packs:
        return False
    packs = _pack_items(entry, content_packs)
    if len(packs) != len(list(content_packs)):
        return False
    return all(_pack_install_yes(pack) for pack in packs)


def _named_packs_install_false(
    entry: Optional[Mapping[str, Any]], content_packs: Sequence[str]
) -> bool:
    packs = _pack_items(entry, content_packs)
    return bool(packs) and all(pack.get("content_pack_install") is False for pack in packs)


def _pack_api_has(
    entry: Optional[Mapping[str, Any]], content_packs: Sequence[str], key: str
) -> bool:
    packs = _pack_items(entry, content_packs)
    if not packs:
        api = (entry or {}).get("content_pack_api") if isinstance(entry, Mapping) else None
        return isinstance(api, Mapping) and key in api
    return all(
        isinstance(pack.get("content_pack_api"), Mapping)
        and key in pack["content_pack_api"]
        for pack in packs
    )


def _content_pack_set_command(
    app_id: Optional[int], content_packs: Sequence[str], assignments: Sequence[Sequence[str]]
) -> str:
    flags = " ".join("--content-pack %s" % pack for pack in content_packs)
    sets = " ".join("--set %s %s" % (field, value) for field, value in assignments)
    prefix = "spa --agent apps add %s" % (app_id or "APP_ID")
    if flags:
        return "%s %s %s --yes" % (prefix, flags, sets)
    return "%s %s --yes" % (prefix, sets)


def apps_add_next(
    *,
    kind: str,
    app_id: Optional[int],
    playbooks: Optional[Sequence[Any]] = None,
    customize: bool = False,
    content_packs: Optional[Sequence[str]] = None,
    config: Optional[Mapping[str, Any]] = None,
    entry: Optional[Mapping[str, Any]] = None,
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
    pack_kind = bool(content_packs) or kind == "itsi_content_pack_single"
    if content_packs and _named_packs_install_false(entry, content_packs):
        rows.append(item("apps.add.another", "Add another app?"))
        return rows
    if pack_kind and content_packs and not _named_packs_install_yes(entry, content_packs):
        rows.append(
            item(
                "apps.content-pack.install",
                "Install this content pack into ITSI? Yes writes content_pack_install "
                "and content_pack_api.install_all true. No extracts files only.",
                _content_pack_set_command(
                    app_id,
                    content_packs,
                    (
                        ("content_pack_install", "true"),
                        ("content_pack_api.install_all", "true"),
                    ),
                ),
                required=False,
            )
        )
        rows.append(item("apps.add.another", "Add another app?"))
        return rows
    if pack_kind and (
        not content_packs
        or _named_packs_install_yes(entry, content_packs)
    ):
        if not content_packs:
            api = (entry or {}).get("content_pack_api") if isinstance(entry, Mapping) else None
            installed = isinstance(api, Mapping) and api.get("install_all") is True
            if not installed:
                rows.append(
                    item(
                        "apps.content-pack.install",
                        "Install this content pack into ITSI? Yes writes "
                        "content_pack_api.install_all true. No extracts files only.",
                        _content_pack_set_command(
                            app_id,
                            (),
                            (("content_pack_api.install_all", "true"),),
                        ),
                        required=False,
                    )
                )
                rows.append(item("apps.add.another", "Add another app?"))
                return rows
        for key, ask, value, choice in CONTENT_PACK_API_ASKS:
            if _pack_api_has(entry, content_packs or (), key):
                continue
            rows.append(
                item(
                    "apps.content-pack.api.%s" % key,
                    ask,
                    _content_pack_set_command(
                        app_id,
                        content_packs or (),
                        (("content_pack_api.%s" % key, value),),
                    ),
                    required=False,
                    choice=choice,
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


def licenses_add_next(
    result: Mapping[str, Any],
    *,
    config_exists: bool = False,
    configured: Optional[Sequence[str]] = None,
    existing_canonicals: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """After add: list, then config set when an env config exists."""
    rows = [
        item(
            "licenses.list",
            "Review Software licenses?",
            "spa --agent licenses list",
            required=False,
        )
    ]
    if not config_exists:
        return rows
    names: List[str] = []
    if result.get("replaced"):
        canonical = str(result.get("canonical") or "")
        if canonical:
            names.append(canonical)
        for extra in existing_canonicals or []:
            if extra and extra not in names:
                names.append(str(extra))
    else:
        for extra in configured or []:
            if extra and extra not in names:
                names.append(str(extra))
        for extra in existing_canonicals or []:
            if extra and extra not in names:
                names.append(str(extra))
        copied = str(result.get("basename") or "")
        if copied and copied not in names:
            names.append(copied)
    if not names:
        return rows
    listed = json.dumps(names, separators=(",", ":"))
    rows.append(
        item(
            "config.set.license_file",
            "Add license files %s?" % ", ".join(names),
            "spa --agent config set splunk_defaults.splunk_license_file '%s' --yes" % listed,
            required=False,
        )
    )
    return rows


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


def _agent_form(command: str) -> str:
    text = str(command or "").strip()
    if text.startswith("spa --agent ") or text == "spa --agent":
        return text
    if text.startswith("spa "):
        return "spa --agent " + text[4:]
    return text


def _discover_command_for_path(path: str, commands: Sequence[str]) -> str:
    leaf = str(path or "").rsplit(".", 1)[-1].lower().replace("_", "-")
    tokens = [part for part in leaf.split("-") if len(part) >= 3]
    for command in commands:
        for word in command.lower().split()[1:]:
            normalized = word.replace("_", "-")
            if leaf and (leaf in normalized or (len(normalized) >= 3 and normalized in leaf)):
                return command
            word_parts = [part for part in normalized.split("-") if len(part) >= 3]
            if tokens and any(token in word_parts for token in tokens):
                return command
    return commands[0]


def explain_choice_next(
    *,
    path: str,
    allowed: Optional[Sequence[Any]] = None,
    discover: Optional[Sequence[str]] = None,
    mutation_command: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """One follow-up when explain has a closed set or a discovery command."""
    commands = [str(command).strip() for command in (discover or []) if str(command).strip()]
    if commands:
        command = _discover_command_for_path(path, commands)
        if command == mutation_command:
            return []
        ident = ".".join(part for part in command.split()[1:] if part) or "discover"
        return [item(ident, "Find live values?", _agent_form(command))]
    if allowed:
        return [item(path, "Choose a value?", choice={"allowed": list(allowed)})]
    return []


def _aws_block(config: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    terraform = config.get("terraform") if isinstance(config, Mapping) else None
    aws = terraform.get("aws") if isinstance(terraform, Mapping) else None
    return aws if isinstance(aws, Mapping) else {}


def _write_path(path: str) -> str:
    text = str(path or "")
    marker = "].terraform.aws."
    if marker in text:
        return "terraform.aws." + text.split(marker, 1)[1]
    return text


def latest_ami_next() -> Dict[str, Any]:
    return item(
        "provider.aws.latest-ami",
        "Find a current AMI for this region?",
        "spa --agent provider aws latest-ami",
    )


def ssh_username_next() -> Dict[str, Any]:
    return item(
        "terraform.aws.ssh_username",
        "Set terraform.aws.ssh_username to match the AMI?",
        "spa --agent config set terraform.aws.ssh_username USER --yes",
    )


def config_write_next(
    operations: Sequence[Mapping[str, Any]],
    document: Optional[Mapping[str, Any]] = None,
    *,
    command: str = "",
) -> List[Dict[str, Any]]:
    """One related follow-up after a successful config set / add / provider."""
    if command == "config provider":
        if _aws_block(document):
            return [latest_ami_next()]
        if isinstance(document, Mapping) and isinstance(document.get("ccm"), Mapping):
            settled = document["ccm"]
            for row in ccm_hardware_next():
                ident = str(row.get("id") or "")
                leaf = ident.rsplit(".", 1)[-1]
                if leaf and not settled.get(leaf):
                    return [row]
        return []
    paths = {
        _write_path(str(row.get("path") or ""))
        for row in operations
        if isinstance(row, Mapping) and row.get("op") in {"set", "add"}
    }
    if "terraform.aws.region" in paths:
        return [latest_ami_next()]
    if "terraform.aws.ami_id" in paths:
        if not _aws_block(document).get("ssh_username"):
            return [ssh_username_next()]
        return []
    return []


_REQUIRED_PATH = re.compile(
    r"\b([A-Za-z][\w]*(?:\.[A-Za-z][\w]*)+)\s+is required\b"
)
_REQUIRED_FIELD = re.compile(r"(?:Value error, )?([A-Za-z][\w]*) is required\b")
_SECRET_LEAF = re.compile(r"password|secret|token|private_key", re.IGNORECASE)


def _required_paths(error: Optional[str]) -> List[str]:
    found: List[str] = []
    for line in str(error or "").splitlines():
        if "is required" not in line:
            continue
        dotted = _REQUIRED_PATH.search(line)
        if dotted:
            path = dotted.group(1)
            if path not in found:
                found.append(path)
            continue
        if ":" not in line:
            continue
        loc_part, msg = line.split(":", 1)
        field = _REQUIRED_FIELD.search(msg)
        if not field:
            continue
        parts = [
            part.strip()
            for part in loc_part.lstrip(" -").split("->")
            if part.strip() and not part.strip().isdigit()
        ]
        parts.append(field.group(1))
        path = ".".join(part for part in parts if part)
        if path and path not in found:
            found.append(path)
    return found


def _required_next(path: str) -> Dict[str, Any]:
    if _SECRET_LEAF.search(path):
        env_name = (
            "SPLUNK_ADMIN_PASSWORD" if path.endswith("splunk_admin_password") else "NAME"
        )
        return item(
            path,
            "Set required %s from the environment?" % path,
            "spa --agent config set %s --from-env %s --yes" % (path, env_name),
            required=True,
        )
    return item(
        path,
        "Set required %s?" % path,
        "spa --agent config set %s VALUE --yes" % path,
        required=True,
    )


def os_packages_next() -> Dict[str, Any]:
    listed = json.dumps(["acl", "polkit"], separators=(",", ":"))
    return item(
        "os.packages",
        "Set guest OS packages (acl and polkit/policykit-1)?",
        "spa --agent config set os.packages '%s' --yes" % listed,
    )


def _hosts(config: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    hosts = config.get("splunk_hosts")
    if not isinstance(hosts, list):
        return []
    return [host for host in hosts if isinstance(host, Mapping)]


def _every_host_has(
    config: Mapping[str, Any], predicate: Callable[[Mapping[str, Any]], bool]
) -> bool:
    hosts = _hosts(config)
    return bool(hosts) and all(predicate(host) for host in hosts)


def _host_ssh_username(host: Mapping[str, Any]) -> bool:
    terraform = host.get("terraform")
    aws = terraform.get("aws") if isinstance(terraform, Mapping) else None
    return isinstance(aws, Mapping) and bool(aws.get("ssh_username"))


def _host_os_packages(host: Mapping[str, Any]) -> bool:
    os_cfg = host.get("os")
    return isinstance(os_cfg, Mapping) and bool(os_cfg.get("packages"))


def validate_guidance_next(
    config: Optional[Mapping[str, Any]] = None,
    error: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Missing required keys and known catalog gaps. Not Ansible or other schema errors."""
    rows = [_required_next(path) for path in _required_paths(error)]
    seen = {row["id"] for row in rows}
    if not isinstance(config, Mapping):
        return rows
    aws = _aws_block(config)
    if (
        aws
        and not aws.get("ssh_username")
        and not _every_host_has(config, _host_ssh_username)
        and "terraform.aws.ssh_username" not in seen
    ):
        rows.append(ssh_username_next())
        seen.add("terraform.aws.ssh_username")
    os_cfg = config.get("os") if isinstance(config.get("os"), Mapping) else {}
    if (
        aws
        and not (os_cfg or {}).get("packages")
        and not _every_host_has(config, _host_os_packages)
        and "os.packages" not in seen
    ):
        rows.append(os_packages_next())
    return rows


def remaining_next(remaining: Iterable[str]) -> List[Dict[str, Any]]:
    mapping = {
        "hardware": item(
            "hardware",
            "Set instance size?",
            "spa --agent config search instance_type",
        ),
        "os": item(
            "os",
            "Set guest OS packages?",
            "spa --agent config explain os",
        ),
        "aws": item(
            "aws",
            "Find a current AMI and SSH user for this region?",
            "spa --agent provider aws latest-ami",
        ),
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
