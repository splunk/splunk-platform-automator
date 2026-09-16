"""Cup-style agent detection and JSON envelope."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional


SCHEMA_VERSION = 1


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


def envelope(ok: bool, data: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": ok, "schema_version": SCHEMA_VERSION}
    if data is not None:
        payload["data"] = data
    if error:
        payload["error"] = error
    return payload


def emit(ok: bool, data: Any = None, error: Optional[str] = None, as_agent: bool = False) -> None:
    if as_agent:
        sys.stdout.write(json.dumps(envelope(ok, data, error), indent=2, default=str) + "\n")
        return
    if error:
        print(error, file=sys.stderr)
    elif data is not None and not isinstance(data, str):
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, str):
        print(data)


COMMAND_SCHEMA = {
    "name": "spa",
    "schema_version": SCHEMA_VERSION,
    "commands": [
        {"name": "init", "summary": "Scaffold or migrate an env dir (spa init --example TOPOLOGY --provider aws|virtualbox ENV)"},
        {
            "name": "features",
            "summary": "Choose from concise topology/provider/setting records; use show ID --keys only for per-key types and constraints",
            "example": "spa --json features show setting.ssl --keys",
        },
        {
            "name": "validate",
            "summary": "Validate splunk_config.yml (schema, Software/baseconfig/local apps, inventory)",
        },
        {"name": "doctor", "summary": "Host prerequisite checks"},
        {"name": "env", "summary": "Print export statements for direnv"},
        {
            "name": "provision",
            "summary": "Provision infrastructure using the provider selected by splunk_config.yml",
            "requires_confirmation": True,
            "flags": [{"long": "--yes", "short": "-y", "help": "Confirm provision"}],
            "example": "spa provision --yes && spa deploy --yes",
        },
        {
            "name": "deploy",
            "summary": "Deploy Splunk (deploy_site.yml); requires Software/baseconfig and local app sources",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm deploy (required in agent mode)"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                {
                    "long": "--allow-unprovisioned",
                    "help": "Skip the check that every config host is in inventory",
                },
            ],
        },
        {
            "name": "destroy",
            "summary": "Destroy infrastructure using the configured provider",
            "requires_confirmation": True,
            "flags": [{"long": "--yes", "short": "-y", "help": "Confirm destroy"}],
        },
        {
            "name": "suspend",
            "summary": "Stop managed instances without destroying disks or provider state",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm power change"},
                {"long": "--no-wait", "help": "Return after requesting stop"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
            ],
        },
        {
            "name": "resume",
            "summary": "Start managed instances and refresh inventory if needed",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm power change"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
            ],
        },
        {
            "name": "hosts list",
            "summary": "List inventory hosts and roles",
            "flags": [
                {"long": "--status", "help": "Include runtime power state and connectivity"},
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
            ],
            "example": "spa hosts list --status",
        },
        {"name": "hosts ssh", "summary": "SSH using inventory", "example": "spa hosts ssh idx1"},
        {"name": "hosts copy", "summary": "Copy files with scp: SRC DST, remote side HOST:PATH (-r for directories)", "example": "spa hosts copy local.txt idx1:/tmp/"},
        {"name": "shell", "summary": "Alias of spa hosts ssh"},
        {"name": "aws", "summary": "AWS discovery for terraform.aws"},
        {
            "name": "licenses",
            "summary": "Inspect license type, expiration and ITSI/ES entitlements",
        },
        {
            "name": "run",
            "summary": "Run a playbook by stem. Discover: spa --json run --list then spa run NAME --help. Honor data[].requires_confirmation with --yes.",
            "flags": [
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                {"long": "--list", "help": "Catalog playbooks with summaries"},
                {"long": "--yes", "short": "-y", "help": "Confirm a mutating playbook (required in agent mode)"},
            ],
            "example": "spa run --list",
        },
        {
            "name": "apps search",
            "summary": "Search Splunkbase (compact rows: app_id, name, title, type, kind, version, summary)",
            "flags": [
                {"long": "--limit", "help": "Max hits (default 10)"},
                {
                    "long": "--type",
                    "help": "Filter Splunkbase type (app, addon)",
                },
                {
                    "long": "--kind",
                    "help": "Filter SPA kind (ta, premium_itsi, itsi_content_library, itsi_content_pack_single, es_not_premium)",
                },
            ],
            "example": "spa --json apps search unix",
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
                },
                {"long": "--local", "help": "Shorthand for --source local"},
            ],
            "example": "spa --json apps snippet 833",
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
        {"name": "agent schema", "summary": "This schema"},
    ],
}
