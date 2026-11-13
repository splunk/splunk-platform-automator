"""Cup-style agent detection and JSON envelope."""

from __future__ import annotations

import contextvars
import json
import os
import sys
from typing import Any, Dict, Mapping, Optional

from spa.hosts import allowed_role_names
from spa.providers import format_provider_choice, provider_ids
from spa.usage import (
    APP_ID_HELP,
    DOCTOR_PROVIDER_HELP,
    INIT_PROVIDER_HELP,
    PROVIDER_HELP,
    SELECTOR_HELP,
    SET_PATH_HELP,
    TOPOLOGY_HELP,
    UNSET_PATH_HELP,
)

_PROVIDER_PIPE = "|".join(provider_ids())
_PROVIDER_CHOICE = format_provider_choice()


SCHEMA_VERSION = 1

# Bound for the duration of one command that accepts --env. emit() reads it
# when the caller does not pass identity, so every success path (including
# direct emit() in venv and logs) shares one value. Failures ignore it.
_ACTIVE_IDENTITY: contextvars.ContextVar[Optional[Mapping[str, Any]]] = contextvars.ContextVar(
    "spa_envelope_identity",
    default=None,
)

# Human playbook output. Agents stay on compact progress / spa logs JSONL.
_FLAG_ANSIBLE_OUTPUT = {
    "long": "--ansible-output",
    "help": "Show captured Ansible output live or from stored logs (not in agent output)",
}
_FLAG_TIMESTAMPS = {
    "long": "--timestamps",
    "help": "Prefix --ansible-output lines with their stored event time",
}
_FLAG_COLOR = {
    "long": "--color",
    "help": "Color --ansible-output. Live runs use Ansible color; stored logs are recolored",
}
_FLAG_VERBOSE_NATIVE = {
    "long": "--verbose",
    "short": "-v",
    "help": "Increase Ansible verbosity and show native output; repeat through -vvvv",
}


AGENT_ENV_VARS = (
    "SPA_AGENT",
    "CLAUDECODE",
    "CLAUDE_CODE",
    "CURSOR_AGENT",
    "CURSOR_TRACE_ID",
    "CODEX_THREAD_ID",
)


def detect_agent() -> bool:
    for name in AGENT_ENV_VARS:
        if (os.environ.get(name) or "").strip():
            return True
    return False


def agent_mode(force_agent: bool = False, force_human: bool = False) -> bool:
    if force_human:
        return False
    if force_agent:
        return True
    return detect_agent()


def envelope(
    ok: bool,
    data: Any = None,
    error: Optional[str] = None,
    identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": ok, "schema_version": SCHEMA_VERSION}
    # Failures stay {ok, schema_version, error} plus any command data already
    # present. Identity is a success-only prefix, immediately before data.
    if ok and identity is not None:
        payload["resolved_env_name"] = identity.get("resolved_env_name")
        payload["env_dir"] = identity.get("env_dir")
        payload["config_file"] = identity.get("config_file")
    if data is not None:
        payload["data"] = data
    if error:
        payload["error"] = error
    return payload


def emit(
    ok: bool,
    data: Any = None,
    error: Optional[str] = None,
    as_agent: bool = False,
    identity: Optional[Mapping[str, Any]] = None,
) -> None:
    if error:
        from spa.runlog import redact

        error = str(redact(error))
    if as_agent:
        bound = identity
        if bound is None:
            bound = _ACTIVE_IDENTITY.get()
        # Compact: agents parse it, and indentation is a third of the payload.
        sys.stdout.write(
            json.dumps(
                envelope(ok, data, error, identity=bound),
                separators=(",", ":"),
                default=str,
            )
            + "\n"
        )
        return
    if error:
        print(error, file=sys.stderr)
    elif data is not None and not isinstance(data, str):
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, str):
        print(data)


def bind_envelope_identity(identity: Optional[Mapping[str, Any]]):
    """Install success-envelope identity for the current command."""
    return _ACTIVE_IDENTITY.set(identity)


def clear_envelope_identity() -> None:
    _ACTIVE_IDENTITY.set(None)


COMMAND_SCHEMA = {
    "name": "spa",
    "schema_version": SCHEMA_VERSION,
    "commands": [
        {
            "name": "init",
            "summary": "Alias of spa environment init (spa init --example TOPOLOGY or --architecture FILE [--provider %s] NAME)" % _PROVIDER_PIPE,
            "flags": [
                {"long": "--example", "help": "Topology example id (exclusive with --architecture)", "takes_value": True, "completes_from": "init list"},
                {
                    "long": "--architecture",
                    "help": "Confirmed schema 1 architecture JSON (exclusive with --example)",
                    "takes_value": True,
                },
                {
                    "long": "--provider",
                    "help": INIT_PROVIDER_HELP,
                    "takes_value": True,
                    "completes_from": "providers",
                },
            ],
            "example": "spa init --architecture examples/architectures/c3.json --provider aws my-lab",
        },
        {
            "name": "init list",
            "summary": "List topology examples. Bare spa init still scaffolds; it does not list.",
            "example": "spa init list",
        },
        {
            "name": "config",
            "summary": "Read, explain, or transactionally edit splunk_config.yml. Agents use config search QUERY, then config explain PATH. Bare spa config exits 2. Writes include set, add, unset, merge, move, topology, provider, and migrate.",
            "example": "spa --agent config explain",
        },
        {
            "name": "config explain",
            "summary": "Describe one config path and its immediate fields. A deeper level is a longer path. The same data is the future GUI payload.",
            "read_only": True,
            "positionals": [{"name": "PATH", "required": False, "help": "User path such as splunk_hosts or os.packages"}],
            "example": "spa --agent config explain splunk_hosts",
        },
        {
            "name": "config search",
            "summary": "Find config paths. Each hit is a path and a one-line description.",
            "read_only": True,
            "positionals": [{"name": "QUERY", "required": True, "help": "Search text"}],
            "example": "spa --agent config search packages",
        },
        {
            "name": "config keys",
            "summary": "Catalog coverage of schema keys. Maintainer check, not the discovery walk.",
            "read_only": True,
            "example": "spa config keys",
        },
        {
            "name": "config schema",
            "summary": "Human documentation generation for docs/config.md. Not an agent payload. Agents use config search QUERY, then config explain PATH.",
            "flags": [
                {
                    "long": "--markdown",
                    "help": "Print GitHub-flavored markdown (human stdout only; regenerate docs/config.md)",
                },
            ],
            "example": "spa --no-agent config schema --markdown",
        },
        {
            "name": "config get",
            "summary": "Read authored config state; pathless agent output is a compact identity outline",
            "read_only": True,
            "positionals": [{"name": "PATH", "required": False, "help": "Schema path with optional identity selectors"}],
            "flags": [
                {"long": "--effective", "help": "Report the schema default when the path is unset"},
                {"long": "--full", "help": "Return the full redacted authored document"},
            ],
            "example": "spa --agent config get splunk_defaults.splunk_version",
        },
        {
            "name": "config audit",
            "summary": "Compare the config SHA-256 to the last spa write stamp",
            "read_only": True,
            "flags": [
                {
                    "long": "--check-hand-edits",
                    "help": "Report ok, hand_edited, or unknown from the spa write stamp",
                },
            ],
            "example": "spa --agent config audit --check-hand-edits",
        },
        {
            "name": "config templates",
            "summary": "Shipped fragment catalog. Bare spa config templates exits 2.",
            "example": "spa --agent config templates list",
        },
        {
            "name": "config templates list",
            "summary": "List shipped reusable config fragments and their leading summaries",
            "read_only": True,
            "example": "spa --agent config templates list",
        },
        {
            "name": "config set",
            "summary": "Transactionally replace one schema-backed value",
            "idempotent": True,
            "positionals": [
                {"name": "PATH", "required": True, "help": SET_PATH_HELP},
                {"name": "VALUE", "required": False, "help": "String or strict JSON value"},
            ],
            "flags": [
                {"long": "--value-file", "help": "Read a JSON or YAML 1.2 value"},
                {"long": "--from-env", "help": "Write an environment lookup for a secret path"},
                {"long": "--explicit-default", "help": "Author a value equal to its schema default"},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config set os.time_zone Europe/Berlin",
        },
        {
            "name": "config add",
            "summary": "Append one new non-app identity-list entry. Fails when that identity already exists.",
            "idempotent": False,
            "positionals": [
                {"name": "SELECTOR", "required": True, "help": SELECTOR_HELP},
                {"name": "JSON_OBJECT", "required": False, "help": "Strict JSON object for the new entry"},
            ],
            "flags": [
                {"long": "--value-file", "help": "Read a JSON or YAML 1.2 object"},
                {"long": "--from-env", "help": "FIELD NAME. Write an environment lookup for a secret field; repeatable"},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config add 'splunk_hosts[name=lm]' '{\"roles\":[\"license_manager\"]}'",
        },
        {
            "name": "config unset",
            "summary": "Transactionally remove one or more authored paths",
            "idempotent": True,
            "positionals": [{"name": "PATH", "required": True, "repeatable": True, "help": UNSET_PATH_HELP}],
            "flags": [
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config unset os.time_zone",
        },
        {
            "name": "config merge",
            "summary": "Transactionally merge a partial splunk_config.yml",
            "idempotent": True,
            "positionals": [
                {
                    "name": "TEMPLATE",
                    "required": False,
                    "help": "Shipped fragment name from examples/templates",
                    "completes_from": "config templates list",
                }
            ],
            "flags": [
                {"long": "--file", "help": "Local YAML or JSON fragment, or - for stdin"},
                {"long": "--explicit-default", "help": "Author values equal to schema defaults"},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config merge remote-provider --yes",
        },
        {
            "name": "config move",
            "summary": "Move a role between hosts, or rename host identities. Bare spa config move exits 2 and names role and host.",
            "example": "spa --agent config move role license_manager --from cm --to lm --yes",
        },
        {
            "name": "config move role",
            "summary": "Move one AllowedRole instance from a host onto another host in one transaction.",
            "idempotent": False,
            "requires_confirmation": True,
            "positionals": [
                {"name": "ROLE", "required": True, "help": "AllowedRole to relocate", "completes_from": "roles"},
            ],
            "flags": [
                {"long": "--from", "help": "Host that currently has ROLE", "takes_value": True, "completes_from": "hosts"},
                {"long": "--to", "help": "Destination host name (created if missing)", "takes_value": True},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config move role license_manager --from cm --to lm --yes",
        },
        {
            "name": "config move host",
            "summary": "Rename one host, or prefix/postfix every host identity. Rewrites hosts_whitelist and hosts_blacklist.",
            "idempotent": True,
            "requires_confirmation": True,
            "positionals": [
                {"name": "OLD", "required": False, "help": "Current host name", "completes_from": "hosts"},
            ],
            "flags": [
                {"long": "--to", "help": "New host name (with OLD)", "takes_value": True},
                {"long": "--prefix", "help": "Prepend to every host name, iter.prefix, and list entry", "takes_value": True},
                {"long": "--postfix", "help": "Append to every host name, iter.postfix, and list entry. A leading hyphen needs --postfix=-lab", "takes_value": True},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config move host --prefix acme- --yes",
        },
        {
            "name": "config topology",
            "summary": "List catalog topology ids, or replace topology-owned sections from one",
            "idempotent": True,
            "positionals": [
                {
                    "name": "TOPOLOGY",
                    "required": False,
                    "help": TOPOLOGY_HELP,
                    "completes_from": "init list",
                }
            ],
            "flags": [
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config topology topology.c1",
        },
        {
            "name": "config provider",
            "summary": "Replace provider-owned config sections from an example template",
            "idempotent": True,
            "positionals": [
                {
                    "name": "PROVIDER",
                    "required": True,
                    "help": PROVIDER_HELP,
                    "completes_from": "providers",
                }
            ],
            "flags": [
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config provider aws",
        },
        {
            "name": "config migrate",
            "summary": "Stamp schema_version to the current schema and apply pending migrations. Does not change operator config_version.",
            "idempotent": True,
            "flags": [
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config migrate --yes",
        },
        {
            "name": "config header set",
            "summary": "Replace the leading comment on splunk_config.yml. Omitted fields are removed.",
            "idempotent": True,
            "requires_confirmation": True,
            "flags": [
                {"long": "--intent", "help": "Why this environment exists", "takes_value": True},
                {"long": "--requirements", "help": "Constraints the design must meet", "takes_value": True},
                {"long": "--sva", "help": "SVA target for this environment", "takes_value": True},
                {"long": "--placement", "help": "Where the deployment runs", "takes_value": True},
                {"long": "--license", "help": "How Splunk is licensed", "takes_value": True},
                {"long": "--installer", "help": "Installer used for Splunk", "takes_value": True},
                {"long": "--os", "help": "Operating system for the hosts", "takes_value": True},
                {"long": "--aws", "help": "AWS placement notes", "takes_value": True},
                {"long": "--deploy", "help": "Command that deploys this environment", "takes_value": True},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision", "takes_value": True},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Confirm the header write (required in agent mode)"},
            ],
            "example": 'spa --agent config header set --intent config-test --deploy "spa deploy --yes" --yes',
        },
        {
            "name": "validate",
            "summary": "Validate splunk_config.yml (schema, Software/baseconfig/local apps, inventory)",
            "flags": [
                {"long": "--config", "help": "Validate this file instead of the environment config"},
                {"long": "--details", "help": "Include the full license inventory", "takes_value": False},
                {
                    "long": "--splunk-config",
                    "help": "Check this provider's selections from the environment config. aws today.",
                    "takes_value": True,
                },
            ],
            "example": "spa validate --splunk-config aws",
        },
        {
            "name": "doctor",
            "summary": "Host prerequisite checks",
            "flags": [
                {
                    "long": "--provider",
                    "help": DOCTOR_PROVIDER_HELP,
                    "takes_value": True,
                    "completes_from": "providers",
                },
                {"long": "--strict", "help": "Treat optional-tool warnings as failures", "takes_value": False},
            ],
        },
        {
            "name": "skills",
            "summary": "Install or remove SPA agent skills from $SPA_HOME/skills/spa/ into user IDE directories",
            "example": "spa skills install",
        },
        {
            "name": "skills install",
            "summary": "Copy SPA skill packages into the user IDE skill directory. Platform defaults to SPA_SKILLS_PLATFORMS, then auto-detect.",
            "positionals": [
                {
                    "name": "PLATFORM",
                    "required": False,
                    "help": "One platform or a comma-separated list (cursor,claude), or all",
                    "completes_from": "skills platforms",
                },
            ],
            "flags": [
                {"long": "--name", "help": "Install one package", "takes_value": True},
                {"long": "--all", "help": "Install every SPA skill package (default)"},
            ],
            "example": "spa skills install cursor",
        },
        {
            "name": "skills remove",
            "summary": "Remove SPA skill packages from the user IDE skill directory. Other skill names are left alone.",
            "requires_confirmation": True,
            "positionals": [
                {
                    "name": "PLATFORM",
                    "required": False,
                    "help": "One platform or a comma-separated list (cursor,claude), or all",
                    "completes_from": "skills platforms",
                },
            ],
            "flags": [
                {"long": "--name", "help": "Remove one package", "takes_value": True},
                {"long": "--all", "help": "Remove every SPA skill package (default)"},
                {"long": "--yes", "short": "-y", "help": "Confirm removing SPA skills"},
            ],
            "example": "spa skills remove --all --yes",
        },
        {
            "name": "venv",
            "summary": "Inspect or manage the shared SPA_HOME/.venv (default) or this environment's .venv",
            "example": "spa venv path",
        },
        {
            "name": "venv path",
            "summary": "Print the shared SPA_HOME/.venv path, or this environment's .venv with --environment",
            "read_only": True,
            "flags": [
                {"long": "--shared", "help": "Target SPA_HOME/.venv (default)"},
                {"long": "--environment", "help": "Target this environment's .venv", "takes_value": False},
            ],
            "example": "spa venv path",
        },
        {
            "name": "venv create",
            "summary": "Create the venv when missing",
            "requires_confirmation": True,
            "flags": [
                {"long": "--shared", "help": "Target SPA_HOME/.venv (default)"},
                {"long": "--environment", "help": "Target this environment's .venv", "takes_value": False},
                {"long": "--python", "help": "Python interpreter used to create the venv"},
                {"long": "--no-install", "help": "Create without package or collection installs"},
                {"long": "--yes", "short": "-y", "help": "Confirm creating the venv"},
            ],
            "example": "spa venv create --shared --yes",
        },
        {
            "name": "venv reinstall",
            "summary": "Install requirements into the existing venv",
            "requires_confirmation": True,
            "flags": [
                {"long": "--shared", "help": "Target SPA_HOME/.venv (default)"},
                {"long": "--environment", "help": "Target this environment's .venv", "takes_value": False},
                {"long": "--python", "help": "Python interpreter used when the venv must be created"},
                {"long": "--no-install", "help": "Skip package and collection installs"},
                {"long": "--yes", "short": "-y", "help": "Confirm reinstalling the venv"},
            ],
            "example": "spa venv reinstall --shared --yes",
        },
        {
            "name": "venv upgrade",
            "summary": "Upgrade packages and Ansible collections in the existing venv",
            "requires_confirmation": True,
            "flags": [
                {"long": "--shared", "help": "Target SPA_HOME/.venv (default)"},
                {"long": "--environment", "help": "Target this environment's .venv", "takes_value": False},
                {"long": "--python", "help": "Python interpreter used when the venv must be created"},
                {"long": "--no-install", "help": "Skip package and collection installs"},
                {"long": "--yes", "short": "-y", "help": "Confirm upgrading the venv"},
            ],
            "example": "spa venv upgrade --shared --yes",
        },
        {
            "name": "venv rebuild",
            "summary": "Delete, recreate, and install the venv",
            "requires_confirmation": True,
            "flags": [
                {"long": "--shared", "help": "Target SPA_HOME/.venv (default)"},
                {"long": "--environment", "help": "Target this environment's .venv", "takes_value": False},
                {"long": "--python", "help": "Python interpreter used to create the venv"},
                {"long": "--no-install", "help": "Rebuild without package or collection installs"},
                {"long": "--yes", "short": "-y", "help": "Confirm rebuilding the venv"},
            ],
            "example": "spa venv rebuild --shared --yes",
        },
        {
            "name": "environment list",
            "summary": "List registered environments (alias: spa env list)",
            "example": "spa environment list",
        },
        {
            "name": "environment init",
            "summary": "Scaffold or migrate an env dir; name-only uses the default parent (~/Splunk-Platform-Automator or paths.yml env_dir)",
            "flags": [
                {"long": "--example", "help": "Topology example id (exclusive with --architecture)", "takes_value": True, "completes_from": "init list"},
                {
                    "long": "--architecture",
                    "help": "Confirmed schema 1 architecture JSON (exclusive with --example)",
                    "takes_value": True,
                },
                {
                    "long": "--provider",
                    "help": INIT_PROVIDER_HELP,
                    "takes_value": True,
                    "completes_from": "providers",
                },
                {"long": "--env-dir", "help": "One-off parent (requires --name); does not change the default parent"},
                {"long": "--name", "help": "Registry name (default: folder basename)"},
                {"long": "--force", "help": "Adopt/refresh an existing env and register it (keep splunk_config.yml unless --example)"},
                {"long": "--software-dir", "help": "Shared installers directory (saved in paths.yml)"},
            ],
            "example": "spa environment init --architecture examples/architectures/c3.json --provider aws my-lab",
        },
        {
            "name": "environment init list",
            "summary": "List topology examples (same catalog as spa init list)",
            "example": "spa environment init list",
        },
        {
            "name": "environment set",
            "summary": "User-level defaults in paths.yml (env parent, Software, baseconfig, apps) and the default provider for init in providers.yml",
            "flags": [
                {"long": "--env-dir", "help": "Default parent for name-only init"},
                {"long": "--software-dir", "help": "Shared installers directory (also sets baseconfig_dir if unset)"},
                {"long": "--baseconfig-dir", "help": "PS baseconfig apps directory"},
                {"long": "--apps-dir", "help": "Local apps directory"},
                {
                    "long": "--default",
                    "help": "Registered environment used when cwd does not select one",
                    "takes_value": True,
                    "completes_from": "environment list",
                },
                {
                    "long": "--provider",
                    "help": "Save the default provider for init: %s. Saved even for aws, so init then accepts no --provider" % _PROVIDER_CHOICE,
                    "takes_value": True,
                    "completes_from": "providers",
                },
            ],
            "example": "spa environment set --software-dir ~/Software --apps-dir ~/labs/apps",
        },
        {
            "name": "environment cleanup",
            "summary": "Remove registry entries whose env directory is missing. Lists them first; no directories are deleted",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Remove the listed registry entries (no directories are deleted)"},
            ],
            "example": "spa environment cleanup --yes",
        },
        {
            "name": "environment remove",
            "summary": "Unregister and delete the env directory (not spa destroy)",
            "requires_confirmation": True,
            "positionals": [
                {
                    "name": "NAME",
                    "required": True,
                    "help": "Registered environment name",
                    "completes_from": "environment list",
                }
            ],
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm deleting the env directory"},
                {"long": "--force", "help": "Allow deleting a dir that looks deployed (local only)"},
            ],
        },
        {
            "name": "environment",
            "summary": "Environment family. spa resolves cwd or --env itself; --export is for external tools",
            "flags": [{"long": "--export", "help": "Print shell exports for external tools"}],
            "example": "spa environment --export",
        },
        {
            "name": "deploy",
            "summary": "Deploy Splunk (deploy_site.yml). After you confirm, ping with become before the playbook. Requires Software/baseconfig and local app sources",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm deploy (required in agent mode)"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
        },
        {
            "name": "destroy",
            "summary": "Destroy infrastructure using the configured provider",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm destroy"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
        },
        {
            "name": "suspend",
            "summary": "Stop managed instances without destroying disks or provider state",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm power change"},
                {"long": "--no-wait", "help": "Return after requesting stop"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
        },
        {
            "name": "resume",
            "summary": "Start managed instances and refresh inventory if needed",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm power change"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
        },
        {
            "name": "hosts",
            "summary": "Inventory actions. List hosts, SSH, provision, or copy. Bare spa hosts exits 2.",
            "example": "spa hosts list",
        },
        {
            "name": "hosts list",
            "summary": "List inventory hosts and roles",
            "flags": [
                {"long": "--status", "short": "-s", "help": "Include runtime power state and connectivity"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
            ],
            "example": "spa hosts list --status",
        },
        {"name": "hosts ssh", "summary": "SSH using inventory", "positionals": [{"name": "NAME", "required": True, "help": "Inventory hostname or role", "completes_from": "hosts"}], "example": "spa hosts ssh idx1"},
        {"name": "hosts copy", "summary": "Copy files with scp: SRC DST, remote side HOST:PATH (-r for directories)", "example": "spa hosts copy local.txt idx1:/tmp/"},
        {
            "name": "hosts register",
            "summary": "Register an existing Linux host over SSH. Does not create the machine.",
            "requires_confirmation": True,
            "positionals": [
                {"name": "NAME", "required": True, "help": "Inventory hostname", "completes_from": "hosts"},
            ],
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm register"},
                {
                    "long": "--ssh-host",
                    "help": "IP, hostname, or FQDN. Must be reachable by SSH.",
                    "takes_value": True,
                },
                {"long": "--ssh-port", "help": "SSH port", "takes_value": True},
                {
                    "long": "--ip-addr",
                    "help": "Address other Splunk hosts use. Omit to use the SSH host.",
                    "takes_value": True,
                },
                {"long": "--user", "help": "SSH login user", "takes_value": True},
                {"long": "--key", "help": "Path to the SSH private key", "takes_value": True},
                {
                    "long": "--role",
                    "help": "Splunk role. Repeat to add more.",
                    "takes_value": True,
                    "choices": allowed_role_names(),
                },
            ],
            "example": "spa hosts register NAME --ssh-host HOST --user USER --key PATH --yes",
        },
        {
            "name": "hosts unregister",
            "summary": "Remove one external host from inventory. The config entry stays. Does not shut the machine down.",
            "requires_confirmation": True,
            "positionals": [
                {"name": "NAME", "required": True, "help": "Inventory hostname", "completes_from": "hosts"},
            ],
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm unregister"},
            ],
            "example": "spa hosts unregister NAME --yes",
        },
        {
            "name": "hosts provision",
            "summary": "Create or update managed hosts. SSH is ready before this returns. Lab bring-up is spa deploy --yes.",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm hosts provision"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
            "example": "spa hosts provision --yes",
        },
        {
            "name": "hosts check",
            "summary": "Ansible ping with become to root, then compare splunk_architecture with the host. The check spa deploy runs. Does not deploy.",
            "flags": [
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
            ],
            "example": "spa hosts check",
        },
        {
            "name": "shell",
            "summary": "Alias of spa hosts ssh. Extra ssh arguments after --.",
            "positionals": [
                {"name": "NAME", "required": True, "help": "Inventory hostname or role", "completes_from": "hosts"},
            ],
            "example": "spa shell idx1 -- -L 8000:localhost:8000",
        },
        {
            "name": "provider",
            "summary": "Provider discovery. Bare spa provider exits 2 and names AWS, then CCM when CCM is in play.",
            "example": "spa --agent provider aws check-auth",
        },
        {
            "name": "provider aws",
            "summary": "AWS discovery for terraform.aws. Bare spa provider aws exits 2.",
            "example": "spa --agent provider aws check-auth",
        },
        {
            "name": "provider aws check-auth",
            "summary": "Verify AWS credentials via STS. No --region required.",
            "example": "spa --agent provider aws check-auth",
        },
        {
            "name": "provider aws latest-ami",
            "summary": "Resolve the latest AMI for a recommended OS.",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
                {
                    "long": "--os",
                    "help": "Recommended OS: rhel, ubuntu, amazon_linux, debian (or all). Aliases: al2023, rhel10, ubuntu2404",
                },
            ],
            "example": "spa provider aws latest-ami --os rhel --region eu-central-1",
        },
        {
            "name": "provider aws describe-ami",
            "summary": "Describe one AMI.",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
                {"long": "--ami-id", "help": "AMI ID"},
            ],
            "example": "spa provider aws describe-ami --ami-id ami-xxx",
        },
        {
            "name": "provider aws validate",
            "summary": "Validate AMI, key pair, security groups, and instance type in a region.",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
                {"long": "--details", "help": "Include the full validation checks", "takes_value": False},
                {"long": "--ami-id", "help": "AMI ID for validate"},
                {"long": "--key-name", "help": "Key pair name for validate"},
                {"long": "--security-groups", "help": "Comma-separated security group names for validate"},
                {"long": "--instance-type", "help": "Instance type for validate"},
            ],
            "example": "spa provider aws validate --region eu-central-1 --security-groups Splunk_Basic",
        },
        {
            "name": "provider aws survey",
            "summary": "Combined discovery report for a region.",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
            ],
            "example": "spa provider aws survey --region eu-central-1",
        },
        {
            "name": "provider aws regions list",
            "summary": "List enabled regions. Marks the region from --region, AWS_REGION, AWS_DEFAULT_REGION, or ~/.aws/config.",
            "example": "spa provider aws regions list --json",
        },
        {
            "name": "provider aws amis list",
            "summary": "List AMIs in a region",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
                {"long": "--name-filter", "help": "AMI name wildcard"},
                {"long": "--owners", "help": "Comma-separated AMI owners"},
                {"long": "--max-results", "help": "Max AMIs to return"},
                {"long": "--os", "help": "Recommended OS, or all"},
            ],
            "example": "spa provider aws amis list --region eu-central-1 --json",
        },
        {
            "name": "provider aws instance-types list",
            "summary": "List instance types offered in a region",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
                {"long": "--family", "help": "Instance type family prefix (e.g. t3)"},
            ],
            "example": "spa provider aws instance-types list --region eu-central-1 --family t3",
        },
        {
            "name": "provider aws key-pairs list",
            "summary": "List EC2 key pairs",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                }
            ],
            "example": "spa provider aws key-pairs list --region eu-central-1",
        },
        {
            "name": "provider aws security-groups list",
            "summary": "List security groups",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                }
            ],
            "example": "spa provider aws security-groups list --region eu-central-1",
        },
        {
            "name": "provider ccm",
            "summary": "CCM discovery. Bare spa provider ccm exits 2.",
            "example": "spa --agent provider ccm check-auth",
        },
        {
            "name": "provider ccm check-auth",
            "summary": "Verify CCM_TOKEN is set and CCM accepts Bearer via GET /api/v1/deployments. Reports the env var as set / not set.",
            "example": "spa --agent provider ccm check-auth",
        },
        {
            "name": "provider ccm survey",
            "summary": "Combined CCM meta dump plus GUI closed sets (operating systems, instance types, disk storage, business purposes, operation hours).",
            "example": "spa --agent provider ccm survey",
        },
        {
            "name": "provider ccm operating-systems list",
            "summary": "List CCM operating systems from GET /api/v1/meta.",
            "example": "spa --agent provider ccm operating-systems list",
        },
        {
            "name": "provider ccm instance-types list",
            "summary": "List CCM instance types from GET /api/v1/meta.",
            "example": "spa --agent provider ccm instance-types list",
        },
        {
            "name": "provider ccm disk-storage list",
            "summary": "List CCM disk storage sizes from GET /api/v1/meta.",
            "example": "spa --agent provider ccm disk-storage list",
        },
        {
            "name": "provider ccm business-purposes list",
            "summary": "List GUI business purposes. Not a CCM meta attribute.",
            "example": "spa --agent provider ccm business-purposes list",
        },
        {
            "name": "provider ccm operation-hours list",
            "summary": "List GUI/API operation hours. Not a CCM meta attribute.",
            "example": "spa --agent provider ccm operation-hours list",
        },
        {
            "name": "provider ccm operation-hours set",
            "summary": "PATCH the CCM deployment operation_hours. Mutating. Does not change hours on spa resume.",
            "requires_confirmation": True,
            "positionals": [
                {
                    "name": "HOURS",
                    "required": True,
                    "help": "manual or business_hours",
                    "choices": ["manual", "business_hours"],
                }
            ],
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm without prompting"},
            ],
            "example": "spa --agent provider ccm operation-hours set manual --yes",
        },
        {
            "name": "provider ccm ssh-keys list",
            "summary": "List CCM SSH key names and fingerprints, and whether ccm.ssh_private_key_file exists locally. Never prints public_key bodies.",
            "example": "spa --agent provider ccm ssh-keys list",
        },
        {
            "name": "provider ccm ttl extend",
            "summary": "PATCH the CCM deployment ttl to now plus --days (1-30). Mutating. Fail if not provisioned or already terminated.",
            "requires_confirmation": True,
            "flags": [
                {
                    "long": "--days",
                    "help": "New TTL in days from now (1-30)",
                    "takes_value": True,
                },
                {"long": "--yes", "short": "-y", "help": "Confirm without prompting"},
            ],
            "example": "spa --agent provider ccm ttl extend --days 7 --yes",
        },
        {
            "name": "architecture",
            "summary": "Architecture file actions. Bare spa architecture exits 2 and names plan, apply, and check.",
            "example": "spa --agent architecture plan examples/architectures/c3.json",
        },
        {
            "name": "architecture plan",
            "summary": "Validate a splunk.architecture schema 1 file and print the overlay plan (read-only). Needs no environment.",
            "positionals": [
                {"name": "FILE", "required": True, "help": "Architecture JSON file"},
            ],
            "example": "spa --agent architecture plan examples/architectures/c3.json",
        },
        {
            "name": "architecture apply",
            "summary": "Overlay a confirmed architecture file onto the current environment config.",
            "requires_confirmation": True,
            "positionals": [
                {"name": "FILE", "required": True, "help": "Architecture JSON file"},
            ],
            "flags": [
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Confirm without prompting"},
            ],
            "example": "spa --agent architecture apply examples/architectures/c3.json --yes",
        },
        {
            "name": "architecture check",
            "summary": "Subset-match a splunk.architecture schema 1 file against the current environment config.",
            "positionals": [
                {"name": "FILE", "required": True, "help": "Architecture JSON file"},
            ],
            "example": "spa --agent architecture check examples/architectures/c3.json",
        },
        {
            "name": "licenses",
            "summary": "License discovery. List Software licenses. Bare spa licenses exits 2.",
            "example": "spa --agent licenses list",
        },
        {
            "name": "licenses list",
            "summary": "Inspect license type, expiration and ITSI/ES entitlements",
            "flags": [
                {
                    "long": "--software-dir",
                    "help": "Software directory (default: ../Software from SPA_ENV_DIR, SPA splunk_software_dir)",
                },
                {
                    "long": "--config",
                    "help": "splunk_config.yml path to detect ITSI/ES and validate current license settings",
                },
                {"long": "--details", "help": "Include the full license inventory", "takes_value": False},
                {
                    "long": "--no-env-recommend",
                    "help": "Do not mention optional licenses when ITSI is not in config",
                    "takes_value": False,
                },
            ],
            "example": "spa --agent licenses list",
        },
        {
            "name": "run",
            "summary": "Run a playbook by stem. Discover: spa --agent run list then spa run NAME --help. Honor data[].requires_confirmation with --yes.",
            "positionals": [
                {
                    "name": "NAME",
                    "required": False,
                    "help": "Playbook stem from spa run list",
                    "completes_from": "run list",
                }
            ],
            "flags": [
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                {"long": "--yes", "short": "-y", "help": "Confirm a mutating playbook (required in agent mode)"},
                {
                    "long": "--apps-playbook",
                    "help": "For splunk_apps_playbook_run: curated stem or env-relative path (sets apps_playbook and app_name)",
                    "takes_value": True,
                    "completes_from": "apps playbooks",
                },
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
            "example": "spa run NAME --help",
        },
        {
            "name": "run list",
            "summary": "Catalog playbooks with summaries. --dir is valid here and on spa run NAME.",
            "flags": [
                {"long": "--dir", "help": "Extra playbook directory"},
            ],
            "example": "spa run list",
        },
        {
            "name": "logs",
            "summary": "List or show per-environment run transcripts under $SPA_ENV_DIR/logs (newest first)",
            "positionals": [
                {
                    "name": "RUN_ID",
                    "required": False,
                    "help": "Run id from spa logs list",
                    "completes_from": "logs list",
                }
            ],
            "flags": [
                {"long": "--last", "help": "Show the most recent run"},
                {"long": "--follow", "help": "Follow the latest jsonl file"},
                {
                    "long": "--wait",
                    "help": "With --follow, wait for a jsonl newer than this invocation",
                    "takes_value": False,
                },
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
            ],
            "example": "spa logs --last",
        },
        {
            "name": "logs list",
            "summary": "Index of run transcripts, newest first. Do not combine with --last or --follow.",
            "example": "spa logs list",
        },
        {
            "name": "apps",
            "summary": "Discover, configure, or download Splunk apps and ITSI content packs.",
            "example": "spa --agent apps search unix",
        },
        {
            "name": "apps search",
            "summary": "Search Splunkbase (compact rows: app_id, name, title, type, kind, version, summary). An itsi query lists Core ITSI 1841 and Content Library 5391 first. ITSI content packs are not in search rows: list the packs in 5391 with spa apps content-packs list 5391.",
            "flags": [
                {"long": "--limit", "help": "Max hits (default 10)"},
                {
                    "long": "--type",
                    "help": "Filter Splunkbase type (app, addon)",
                    "takes_value": True,
                    "choices": ["app", "addon"],
                },
                {
                    "long": "--kind",
                    "help": "Filter SPA kind (ta, premium_itsi, itsi_content_library, itsi_content_pack_single, es_not_premium)",
                    "takes_value": True,
                    "choices": [
                        "ta",
                        "premium_itsi",
                        "itsi_content_library",
                        "itsi_content_pack_single",
                        "es_not_premium",
                    ],
                },
            ],
            "example": "spa --agent apps search itsi",
        },
        {
            "name": "apps content-packs list",
            "summary": "List ITSI content packs in Content Library 5391 from --archive, apps_dir, an existing install archive, or cached pack app.conf files. An install archive is left in place. --version selects the release (default latest).",
            "flags": [
                {
                    "long": "--version",
                    "help": "Content Library release to inspect (default latest). A newer latest release replaces the cached app.conf files.",
                },
                {
                    "long": "--archive",
                    "help": "Inspect a local 5391 archive without environment credentials",
                },
            ],
            "example": "spa --agent apps content-packs list 5391",
        },
        {
            "name": "apps snippet",
            "summary": "Print apps[] YAML for a Splunkbase app_id or local custom app folder",
            "flags": [
                {"long": "--version", "help": "Release version (default latest)"},
                {"long": "--roles", "help": "Comma-separated target_roles (TA only)"},
                {
                    "long": "--source",
                    "help": "Snippet source: splunkbase or local; local checks apps_dir",
                    "takes_value": True,
                    "choices": ["splunkbase", "local"],
                },
                {"long": "--local", "help": "Shorthand for --source local"},
                {
                    "long": "--customize",
                    "help": "Include matching curated apps_playbooks customizations in the YAML",
                },
                {"long": "--set", "help": "Set another schema-backed app FIELD VALUE; repeatable"},
            ],
            "example": "spa --agent apps snippet 833",
        },
        {
            "name": "apps add",
            "summary": "Idempotently add or update one apps[] entry; edits config and does not deploy",
            "idempotent": True,
            "flags": [
                {
                    "long": "--version",
                    "help": "Release or local archive version to author (default latest)",
                },
                {
                    "long": "--roles",
                    "help": "Comma-separated target_roles; required only for normal apps and rejected for ITSI/content packs",
                },
                {
                    "long": "--new",
                    "help": "Append another apps[] row for this app_id; without it, extra copies match by exact --roles",
                    "takes_value": False,
                },
                {
                    "long": "--source",
                    "help": "Use Splunkbase metadata, or a folder/archive already in apps_dir (default splunkbase). Mutually exclusive with --local",
                    "takes_value": True,
                    "choices": ["splunkbase", "local"],
                },
                {"long": "--local", "help": "Shorthand for --source local. Mutually exclusive with --source"},
                {
                    "long": "--customize",
                    "help": "Attach matching curated SPA playbook(s) to the app entry or named content pack",
                },
                {
                    "long": "--set",
                    "help": "Set another schema-backed app FIELD from strict JSON; repeatable",
                },
                {
                    "long": "--content-pack",
                    "help": "5391 only: add exact bundled folder NAME; repeatable and mutually exclusive with --install-all-content-packs",
                },
                {
                    "long": "--install-all-content-packs",
                    "help": "5391 only: install every bundled pack; mutually exclusive with --content-pack",
                    "takes_value": False,
                },
                {
                    "long": "--explicit-default",
                    "help": "Write omit-safe default values that SPA normally leaves absent",
                },
                {
                    "long": "--dry-run",
                    "help": "Plan dependencies and show the result without prompting or writing",
                },
                {
                    "long": "--expect-revision",
                    "help": "Write only when the config still has this SHA-256 revision",
                },
                {
                    "long": "--resolve",
                    "help": "Supply one unresolved dependency PATH VALUE; VALUE uses strict JSON; repeatable",
                },
                {
                    "long": "--resolve-file",
                    "help": "Supply unresolved dependencies from sparse YAML/JSON; use - for stdin",
                },
                {
                    "long": "--show-diff",
                    "help": "Print the redacted unified diff after the status line (no-op in agent mode)",
                },
                {
                    "long": "--yes",
                    "short": "-y",
                    "help": "Skip the human config-edit confirmation; agent mode never prompts",
                },
            ],
            "example": "spa --agent apps add 833 --roles search_head,indexer",
        },
        {
            "name": "apps remove",
            "summary": "Remove an authored app entry; does not uninstall deployed files",
            "idempotent": True,
            "positionals": [
                {
                    "name": "APP_ID_OR_NAME",
                    "required": True,
                    "help": APP_ID_HELP,
                }
            ],
            "flags": [
                {
                    "long": "--roles",
                    "help": "When the app is defined more than once, remove the copy whose target_roles match (one role or the exact set)",
                },
                {"long": "--content-pack", "help": "Remove one named pack under Content Library 5391"},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--show-diff", "help": "Print the redacted unified diff after the status line (no-op in agent mode)"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent apps remove 833",
        },
        {
            "name": "apps download",
            "summary": "Download a Splunkbase archive into apps_dir (does not edit config or print a snippet)",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm download (required in agent mode)"},
                {"long": "--version", "help": "Release version (default latest)"},
                {
                    "long": "--extract",
                    "help": "Safely extract a folder-backed app into apps_dir and delete the archive (TA/ES only)",
                },
                {
                    "long": "--overwrite",
                    "help": "With --extract, replace an existing app folder in apps_dir",
                },
            ],
            "example": "spa apps download 833 --yes",
        },
        {
            "name": "agent schema",
            "summary": "This schema (JSON envelope; --markdown prints a human catalog)",
            "flags": [
                {
                    "long": "--markdown",
                    "help": "Print GitHub-flavored markdown instead of JSON (human stdout; regenerate docs/commands.md)",
                },
            ],
            "example": "spa --no-agent agent schema --markdown",
        },
        {
            "name": "completion",
            "summary": "Print a bash or zsh completion function. Human shell setup. Bare spa completion exits 2. Agents use spa agent schema.",
            "example": "spa completion zsh",
        },
        {
            "name": "completion bash",
            "summary": "Print a bash function for eval. Does not edit the shell startup file. Agents use spa agent schema.",
            "read_only": True,
            "example": "spa completion bash",
        },
        {
            "name": "completion zsh",
            "summary": "Print a zsh function for eval. Does not edit the shell startup file. Agents use spa agent schema.",
            "read_only": True,
            "example": "spa completion zsh",
        },
    ],
}


def _markdown_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def format_schema_markdown(schema: Optional[Dict[str, Any]] = None) -> str:
    """Render COMMAND_SCHEMA as the checked-in docs/commands.md catalog."""
    src = schema if schema is not None else COMMAND_SCHEMA
    lines = [
        "<!-- Generated by spa agent schema --markdown. Do not edit by hand. -->",
        "",
        "# spa commands",
        "",
        "Generated from `spa agent schema`. Do not edit this file; regenerate with",
        "`spa --no-agent agent schema --markdown`. Workflows stay in the [user guide](user-guide.md).",
        "",
        "Playbooks are not listed here. Discover them with `spa --agent run list`",
        "and `spa run NAME --help`.",
        "",
    ]
    for cmd in src.get("commands") or []:
        name = cmd.get("name") or ""
        lines.append(f"## `{name}`")
        lines.append("")
        summary = str(cmd.get("summary") or "").strip()
        if summary:
            lines.append(summary)
            lines.append("")
        if cmd.get("requires_confirmation"):
            lines.append("Requires confirmation: yes (`--yes`).")
            lines.append("")
        flags = cmd.get("flags") or []
        if flags:
            lines.append("| Flag | Description |")
            lines.append("| --- | --- |")
            for flag in flags:
                long = flag.get("long") or ""
                short = flag.get("short")
                label = f"`{long}`" if long else ""
                if short:
                    label = f"`{short}`, `{long}`" if long else f"`{short}`"
                lines.append(f"| {label} | {_markdown_cell(flag.get('help') or '')} |")
            lines.append("")
        positionals = cmd.get("positionals") or []
        if positionals:
            lines.append("| Argument | Required | Description |")
            lines.append("| --- | --- | --- |")
            for positional in positionals:
                required = "yes" if positional.get("required") else "no"
                lines.append(
                    "| `%s` | %s | %s |"
                    % (
                        _markdown_cell(positional.get("name") or ""),
                        required,
                        _markdown_cell(positional.get("help") or ""),
                    )
                )
            lines.append("")
        example = cmd.get("example")
        if example:
            lines.append("Example:")
            lines.append("")
            lines.append("```bash")
            lines.append(str(example))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
