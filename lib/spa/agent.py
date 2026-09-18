"""Cup-style agent detection and JSON envelope."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional


SCHEMA_VERSION = 1

# Human playbook output. Agents stay on compact progress / spa logs JSONL.
_FLAG_ANSIBLE_OUTPUT = {
    "long": "--ansible-output",
    "help": "Show redacted Ansible-style output rebuilt from JSONL (not in agent output)",
}
_FLAG_VERBOSE_NATIVE = {
    "long": "--verbose",
    "short": "-v",
    "help": "Stream Ansible's own unredacted output; may print secrets (verbosity: -- -vv)",
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


def envelope(ok: bool, data: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": ok, "schema_version": SCHEMA_VERSION}
    if data is not None:
        payload["data"] = data
    if error:
        payload["error"] = error
    return payload


def emit(ok: bool, data: Any = None, error: Optional[str] = None, as_agent: bool = False) -> None:
    if error:
        from spa.runlog import redact

        error = str(redact(error))
    if as_agent:
        # Compact: agents parse it, and indentation is a third of the payload.
        sys.stdout.write(
            json.dumps(envelope(ok, data, error), separators=(",", ":"), default=str) + "\n"
        )
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
        {"name": "init", "summary": "Alias of spa environment init (spa init --example TOPOLOGY [--provider aws|virtualbox] NAME)"},
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
        {
            "name": "venv",
            "summary": "Inspect or manage the shared SPA_HOME/.venv (default) or this environment's .venv",
            "requires_confirmation": True,
            "flags": [
                {"long": "--path", "help": "Print the target venv path (default; no confirmation)"},
                {"long": "--create", "help": "Create the venv when missing"},
                {"long": "--reinstall", "help": "Install requirements into the existing venv"},
                {"long": "--upgrade", "help": "Upgrade packages and Ansible collections in the existing venv"},
                {"long": "--rebuild", "help": "Delete, recreate, and install the venv"},
                {"long": "--shared", "help": "Target SPA_HOME/.venv (default)"},
                {"long": "--environment", "help": "Target this environment's .venv"},
                {"long": "--python", "help": "Python interpreter used to create the venv"},
                {"long": "--no-install", "help": "Create/rebuild without package or collection installs"},
                {"long": "--yes", "short": "-y", "help": "Confirm creating or changing the venv"},
            ],
            "example": "spa venv --shared --rebuild --yes",
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
                {"long": "--example", "help": "Topology example id"},
                {"long": "--provider", "help": "aws or virtualbox (default aws, or providers.yml)"},
                {"long": "--env-dir", "help": "One-off parent (requires --name); does not change the default parent"},
                {"long": "--name", "help": "Registry name (default: folder basename)"},
                {"long": "--force", "help": "Adopt/refresh an existing env and register it (keep splunk_config.yml unless --example)"},
                {"long": "--software-dir", "help": "Shared installers directory (saved in paths.yml)"},
            ],
            "example": "spa environment init --example cm_2idxc_sh_uf my-lab",
        },
        {
            "name": "environment set",
            "summary": "User-level defaults in paths.yml (env parent, Software, baseconfig, apps) and providers.yml (only when not aws)",
            "flags": [
                {"long": "--env-dir", "help": "Default parent for name-only init"},
                {"long": "--software-dir", "help": "Shared installers directory (also sets baseconfig_dir if unset)"},
                {"long": "--baseconfig-dir", "help": "PS baseconfig apps directory"},
                {"long": "--apps-dir", "help": "Local apps directory"},
                {"long": "--default", "help": "Registered environment used when cwd does not select one"},
                {"long": "--provider", "help": "Default provider (aws|virtualbox)"},
            ],
            "example": "spa environment set --software-dir ~/Software --apps-dir ~/labs/apps",
        },
        {
            "name": "environment remove",
            "summary": "Unregister and delete the env directory (not spa destroy)",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm deleting the env directory"},
                {"long": "--force", "help": "Allow deleting a dir that looks deployed (local only)"},
            ],
        },
        {
            "name": "environment",
            "summary": "Environment family (alias: env). spa resolves cwd or --env itself; --export is for external tools",
            "flags": [{"long": "--export", "help": "Print shell exports for external tools"}],
            "example": "spa env --export",
        },
        {
            "name": "provision",
            "summary": "Provision infrastructure using the provider selected by splunk_config.yml",
            "requires_confirmation": True,
            "flags": [
                {"long": "--yes", "short": "-y", "help": "Confirm provision"},
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_VERBOSE_NATIVE,
            ],
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
                _FLAG_ANSIBLE_OUTPUT,
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
                _FLAG_VERBOSE_NATIVE,
            ],
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
                {
                    "long": "--apps-playbook",
                    "help": "For splunk_apps_playbook_run: curated stem or env-relative path (sets apps_playbook and app_name)",
                },
                _FLAG_ANSIBLE_OUTPUT,
                _FLAG_VERBOSE_NATIVE,
            ],
            "example": "spa run --list",
        },
        {
            "name": "logs",
            "summary": "List or show per-environment run transcripts under $SPA_ENV_DIR/logs (newest first)",
            "flags": [
                {"long": "--last", "help": "Show the most recent run"},
                {"long": "--follow", "help": "Follow the latest jsonl file"},
                _FLAG_ANSIBLE_OUTPUT,
                {
                    "long": "--verbose",
                    "short": "-v",
                    "help": "Same reconstruction as --ansible-output (stored runs have no native stream)",
                },
            ],
            "example": "spa logs --last",
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
                {
                    "long": "--customize",
                    "help": "Include matching curated apps_playbooks customizations in the YAML",
                },
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
        "Playbooks are not listed here. Discover them with `spa --json run --list`",
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
        example = cmd.get("example")
        if example:
            lines.append("Example:")
            lines.append("")
            lines.append("```bash")
            lines.append(str(example))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
