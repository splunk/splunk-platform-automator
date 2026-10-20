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
            "name": "init list",
            "summary": "List topology examples. Bare spa init still scaffolds; it does not list.",
            "example": "spa init list",
        },
        {
            "name": "features",
            "summary": "Look up settings. Agents use search QUERY, then show SELECTOR [--keys]. schema --markdown is a human docs dump, not an agent payload.",
            "example": "spa --json features search splunk",
        },
        {
            "name": "features list",
            "summary": "Full feature catalog",
            "example": "spa features list",
        },
        {
            "name": "features search",
            "summary": "Search the catalog. In zsh, quote a selector that contains [], or omit the brackets.",
            "positionals": [
                {"name": "QUERY", "required": True, "help": "Search text"},
            ],
            "example": "spa --json features search cluster",
        },
        {
            "name": "features show",
            "summary": "Show one feature. Agents use this after features search.",
            "positionals": [
                {"name": "SELECTOR", "required": True, "help": "Schema path or layout id"},
            ],
            "flags": [
                {
                    "long": "--keys",
                    "help": "Include per-key types, constraints, guidance, and apply metadata",
                },
            ],
            "example": "spa --json features show splunk_defaults.splunk_ssl --keys",
        },
        {
            "name": "features keys",
            "summary": "Catalog coverage of schema keys",
            "example": "spa features keys",
        },
        {
            "name": "features schema",
            "summary": "Human documentation generation for docs/config.md. Not an agent payload. Agents use features search QUERY, then features show SELECTOR [--keys].",
            "flags": [
                {
                    "long": "--markdown",
                    "help": "Print GitHub-flavored markdown (human stdout only; regenerate docs/config.md)",
                },
            ],
            "example": "spa --no-agent features schema --markdown",
        },
        {
            "name": "validate",
            "summary": "Validate splunk_config.yml (schema, Software/baseconfig/local apps, inventory)",
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
                },
            ],
            "flags": [
                {"long": "--name", "help": "Install one package"},
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
                },
            ],
            "flags": [
                {"long": "--name", "help": "Remove one package"},
                {"long": "--all", "help": "Remove every SPA skill package (default)"},
                {"long": "--yes", "short": "-y", "help": "Confirm removing SPA skills"},
            ],
            "example": "spa skills remove --all --yes",
        },
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
            "name": "environment init list",
            "summary": "List topology examples (same catalog as spa init list)",
            "example": "spa environment init list",
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
                _FLAG_TIMESTAMPS,
                _FLAG_COLOR,
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
        {"name": "hosts ssh", "summary": "SSH using inventory", "example": "spa hosts ssh idx1"},
        {"name": "hosts copy", "summary": "Copy files with scp: SRC DST, remote side HOST:PATH (-r for directories)", "example": "spa hosts copy local.txt idx1:/tmp/"},
        {"name": "shell", "summary": "Alias of spa hosts ssh"},
        {"name": "aws", "summary": "AWS discovery for terraform.aws. Catalogs are spa aws list KIND."},
        {
            "name": "aws list regions",
            "summary": "List enabled regions. Does not require --region.",
            "example": "spa aws list regions --json",
        },
        {
            "name": "aws list amis",
            "summary": "List AMIs in a region",
            "flags": [
                {"long": "--region", "help": "AWS region", "required": True},
                {"long": "--name-filter", "help": "AMI name wildcard"},
                {"long": "--owners", "help": "Comma-separated AMI owners"},
                {"long": "--max-results", "help": "Max AMIs to return"},
                {"long": "--os", "help": "Recommended OS, or all"},
            ],
            "example": "spa aws list amis --region eu-central-1 --json",
        },
        {
            "name": "aws list instance-types",
            "summary": "List instance types offered in a region",
            "flags": [
                {"long": "--region", "help": "AWS region", "required": True},
                {"long": "--family", "help": "Instance type family prefix (e.g. t3)"},
            ],
            "example": "spa aws list instance-types --region eu-central-1 --family t3",
        },
        {
            "name": "aws list key-pairs",
            "summary": "List EC2 key pairs",
            "flags": [{"long": "--region", "help": "AWS region", "required": True}],
            "example": "spa aws list key-pairs --region eu-central-1",
        },
        {
            "name": "aws list security-groups",
            "summary": "List security groups",
            "flags": [{"long": "--region", "help": "AWS region", "required": True}],
            "example": "spa aws list security-groups --region eu-central-1",
        },
        {
            "name": "licenses",
            "summary": "Inspect license type, expiration and ITSI/ES entitlements",
        },
        {
            "name": "run",
            "summary": "Run a playbook by stem. Discover: spa --json run list then spa run NAME --help. Honor data[].requires_confirmation with --yes.",
            "flags": [
                {"long": "--hosts", "help": "only these hosts (names or roles from this env)"},
                {"long": "--yes", "short": "-y", "help": "Confirm a mutating playbook (required in agent mode)"},
                {
                    "long": "--apps-playbook",
                    "help": "For splunk_apps_playbook_run: curated stem or env-relative path (sets apps_playbook and app_name)",
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
            "summary": "Splunkbase search, an apps[] snippet, or an archive download.",
            "example": "spa --json apps search unix",
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
        "Playbooks are not listed here. Discover them with `spa --json run list`",
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
