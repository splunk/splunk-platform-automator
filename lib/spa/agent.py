"""Cup-style agent detection and JSON envelope."""

from __future__ import annotations

import contextvars
import json
import os
import sys
from typing import Any, Dict, Mapping, Optional

from spa.hosts import allowed_role_names
from spa.usage import (
    APP_ID_HELP,
    INIT_PROVIDER_HELP,
    PROVIDER_HELP,
    SELECTOR_HELP,
    SET_PATH_HELP,
    TOPOLOGY_HELP,
    UNSET_PATH_HELP,
)


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
        {"name": "init", "summary": "Alias of spa environment init (spa init --example TOPOLOGY [--provider aws|virtualbox|external] NAME)"},
        {
            "name": "init list",
            "summary": "List topology examples. Bare spa init still scaffolds; it does not list.",
            "example": "spa init list",
        },
        {
            "name": "config",
            "summary": "Read, explain, or transactionally edit splunk_config.yml. Agents use config search QUERY, then config explain PATH. Bare spa config exits 2.",
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
            "name": "config templates",
            "summary": "List shipped reusable config fragments and their leading summaries",
            "example": "spa --agent config templates",
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
                    "completes_from": "config templates",
                }
            ],
            "flags": [
                {"long": "--file", "help": "Local YAML or JSON fragment, or - for stdin"},
                {"long": "--explicit-default", "help": "Author values equal to schema defaults"},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config merge --file fragment.yml",
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
                {"long": "--yes", "short": "-y", "help": "Skip the human confirmation prompt"},
            ],
            "example": "spa --agent config provider aws",
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
                {"long": "--yes", "short": "-y", "help": "Confirm the header write (required in agent mode)"},
            ],
            "example": 'spa --agent config header set --intent config-test --deploy "spa provision --yes && spa deploy --yes" --yes',
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
        {"name": "doctor", "summary": "Host prerequisite checks"},
        {
            "name": "skills",
            "summary": "Install or remove SPA agent skills from $SPA_HOME/skills/spa/ into user IDE directories",
            "example": "spa skills install",
        },
        {
            "name": "skills install",
            "summary": "Link SPA skill packages into the user IDE skill directory. Platform defaults to SPA_SKILLS_PLATFORMS, then auto-detect.",
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
                {"long": "--example", "help": "Topology example id", "takes_value": True, "completes_from": "init list"},
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
            "example": "spa environment init --example cm_2idxc_sh --provider aws my-lab",
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
                    "help": "Save the default provider for init: aws, virtualbox, or external. Saved even for aws, so init then accepts no --provider",
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
            "summary": "Environment family (alias: env). spa resolves cwd or --env itself; --export is for external tools",
            "flags": [{"long": "--export", "help": "Print shell exports for external tools"}],
            "example": "spa environment --export",
        },
        {
            "name": "provision",
            "summary": "Provision infrastructure using the provider selected by splunk_config.yml",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm provision"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
                _FLAG_VERBOSE_NATIVE,
            ],
            "example": "spa provision --yes && spa deploy --yes",
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
            "summary": "Inventory actions. List hosts, SSH, or copy. Bare spa hosts exits 2.",
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
            "name": "hosts check",
            "summary": "Ansible ping with become to root, then compare splunk_architecture with the host. The check spa deploy runs. Does not deploy.",
            "flags": [
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
            ],
            "example": "spa hosts check",
        },
        {"name": "shell", "summary": "Alias of spa hosts ssh", "positionals": [{"name": "NAME", "required": False, "help": "Inventory hostname or role", "completes_from": "hosts"}]},
        {
            "name": "aws",
            "summary": "AWS discovery for terraform.aws. Catalogs are spa aws regions list and the other resource list commands.",
            "flags": [
                {"long": "--details", "help": "Include the full validation checks", "takes_value": False},
            ],
        },
        {
            "name": "aws regions list",
            "summary": "List enabled regions. Marks the region from --region, AWS_REGION, AWS_DEFAULT_REGION, or ~/.aws/config.",
            "example": "spa aws regions list --json",
        },
        {
            "name": "aws amis list",
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
            "example": "spa aws amis list --region eu-central-1 --json",
        },
        {
            "name": "aws instance-types list",
            "summary": "List instance types offered in a region",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                },
                {"long": "--family", "help": "Instance type family prefix (e.g. t3)"},
            ],
            "example": "spa aws instance-types list --region eu-central-1 --family t3",
        },
        {
            "name": "aws key-pairs list",
            "summary": "List EC2 key pairs",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                }
            ],
            "example": "spa aws key-pairs list --region eu-central-1",
        },
        {
            "name": "aws security-groups list",
            "summary": "List security groups",
            "flags": [
                {
                    "long": "--region",
                    "help": "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
                }
            ],
            "example": "spa aws security-groups list --region eu-central-1",
        },
        {
            "name": "licenses",
            "summary": "Inspect license type, expiration and ITSI/ES entitlements",
            "flags": [
                {"long": "--details", "help": "Include the full license inventory", "takes_value": False},
            ],
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
            "summary": "Search Splunkbase (compact rows: app_id, name, title, type, kind, version, summary)",
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
            "example": "spa --agent apps search unix",
        },
        {
            "name": "apps content-packs list",
            "summary": "Inspect Content Library 5391 from --archive, apps_dir, an existing install archive, or cached pack app.conf files. An install archive is left in place. --version selects the release (default latest).",
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
                    "long": "--source",
                    "help": "Use Splunkbase metadata, or a folder/archive already in apps_dir (default splunkbase). Mutually exclusive with --local",
                    "takes_value": True,
                    "choices": ["splunkbase", "local"],
                },
                {"long": "--local", "help": "Shorthand for --source local. Mutually exclusive with --source"},
                {
                    "long": "--customize",
                    "help": "Attach an exact matching curated SPA playbook to this top-level app entry",
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
                {"long": "--content-pack", "help": "Remove one named pack under Content Library 5391"},
                {"long": "--dry-run", "help": "Preview without writing"},
                {"long": "--expect-revision", "help": "Require the current SHA-256 revision"},
                {"long": "--resolve", "help": "Supply PATH VALUE for an unresolved dependency; repeatable"},
                {"long": "--resolve-file", "help": "Supply a sparse YAML/JSON dependency fragment"},
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
