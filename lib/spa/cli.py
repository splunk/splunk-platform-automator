"""spa command-line entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from spa.agent import agent_mode, emit, format_schema_markdown
from spa.api import CommandResult, open_session
from spa.apps import SEARCH_KINDS, SEARCH_TYPES
from spa.executil import (
    REQUIREMENT_DISTRIBUTIONS,
    ToolNotFound,
    apply_paths_env,
    venv_required_error,
    venv_setup_message,
)
from spa.paths import env_dir_required_error, resolve_spa_paths


# Commands whose flags belong to the wrapped tool, not to spa (spa shell idx1,
# spa aws --check-auth). argparse.REMAINDER drops a leading option, so these are
# split off before the spa parser runs.
NATIVE_FLAG_COMMANDS = ("shell", "sh", "aws", "licenses", "lic")
# These must keep working without a venv: they are how an operator inspects or
# builds one. Every other command reads YAML or runs Ansible, so it is gated.
VENV_OPTIONAL_COMMANDS = frozenset({"venv", "doctor", "agent", "init", "environment", "logs"})
GLOBAL_OPTS_WITH_VALUE = ("--start-dir", "--env")
HOSTS_FLAG_HELP = "only these hosts (names or roles from this env)"
AGENT_EXAMPLES = """examples:
  spa agent schema       command schema (name, summary, flags, requires_confirmation)
  spa agent              same as spa agent schema
  spa --no-agent agent schema --markdown  regenerate docs/commands.md
  spa --json run --list  playbook catalog, incl. per-playbook requires_confirmation

Commands whose schema entry sets requires_confirmation need -y/--yes in agent
mode; agents never answer an interactive prompt.
"""


def _split_passthrough(argv: Sequence[str]) -> Tuple[List[str], List[str]]:
    if "--" in argv:
        idx = list(argv).index("--")
        return list(argv[:idx]), list(argv[idx + 1 :])
    return list(argv), []


def _split_native(argv: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Split at a native-flag command: (spa args incl. command, tool args)."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in GLOBAL_OPTS_WITH_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        if token in NATIVE_FLAG_COMMANDS:
            return list(argv[: index + 1]), list(argv[index + 1 :])
        break
    return list(argv), []


def _tilde(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _start_dir_from_head(head: Sequence[str]) -> Optional[str]:
    tokens = list(head)
    if "--start-dir" in tokens:
        index = tokens.index("--start-dir")
        if index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def _print_catalog(rows: List[dict], paths) -> None:
    """Group the catalog by root; the source column only matters in --json."""
    groups = (
        ("ansible", "Framework playbooks", paths.spa_home / "ansible"),
        ("verification", "Verification playbooks", paths.spa_home / "ansible" / "verification"),
        ("env", "Env playbooks", paths.spa_env_dir),
    )
    # One column start for every group so summaries line up across sections.
    width = max((len(row["name"]) for row in rows if row.get("summary")), default=0) + 2
    printed = False
    for source, title, folder in groups:
        group_rows = [row for row in rows if row.get("source") == source]
        if not group_rows:
            continue
        if printed:
            print()
        printed = True
        print("%s — %s" % (title, _tilde(folder)))
        for row in group_rows:
            summary = row.get("summary")
            if summary:
                print("  %s%s" % (row["name"].ljust(width), summary))
            else:
                print("  %s" % row["name"])
    if printed:
        print()
        print("Run one with: spa run <name> [--hosts NAME] [-- ansible-playbook args]")
        print("Describe one: spa run <name> --help")


def _run_help_target(head: Sequence[str]) -> Optional[str]:
    """Playbook stem, empty string for spa run --help, or None to use argparse."""
    help_flags = {"-h", "--help"}
    skip_value = {"--start-dir"}
    index = 0
    while index < len(head):
        token = head[index]
        if token in skip_value:
            index += 2
            continue
        if token.startswith("-") and token not in help_flags:
            index += 1
            continue
        if token == "run":
            rest = list(head[index + 1 :])
            break
        return None
    else:
        return None
    if not any(item in help_flags for item in rest):
        return None
    names: List[str] = []
    skip_run_value = {"--dir", "--hosts", "--apps-playbook"}
    cursor = 0
    while cursor < len(rest):
        token = rest[cursor]
        if token in help_flags or token == "--list":
            cursor += 1
            continue
        if token in skip_run_value:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        names.append(token)
        cursor += 1
    if names:
        return names[0]
    return ""


def _print_run_usage() -> None:
    print("usage: spa run [-h] [--list] [--dir DIR] [--hosts NAME] [--apps-playbook STEM] [--ansible-output] [-v] [-y] [NAME]")
    print()
    print("Run a playbook by stem, or list/describe playbooks without executing Ansible.")
    print()
    print("  spa run --list              catalog (name — summary)")
    print("  spa run NAME --help         description, risk, inputs, examples")
    print("  spa run NAME [-y] [--hosts NAME] [--ansible-output] [-v] [-- ansible-playbook args]")
    print("  spa run splunk_apps_playbook_run --apps-playbook STEM|PATH --hosts ROLE --yes")
    print()
    print("Mutating playbooks need --yes in agent mode (see requires_confirmation).")
    print("Discover first with spa --json run --list, then spa run NAME --help.")


def _print_playbook_help(data: dict) -> None:
    meta = data.get("metadata") or {}
    print(data.get("name") or "")
    if data.get("renamed_from"):
        print("Renamed in 3.0; use spa run %s" % (data.get("use") or data.get("name")))
        print()
    if meta.get("summary"):
        print(meta["summary"])
        print()
    if meta.get("description"):
        print(meta["description"])
        print()
    extras = []
    if meta.get("category"):
        extras.append("category: %s" % meta["category"])
    if meta.get("risk"):
        extras.append("risk: %s" % meta["risk"])
    if data.get("requires_confirmation"):
        extras.append("confirmation: required")
    elif meta.get("risk") == "read-only":
        extras.append("confirmation: none")
    if meta.get("requires_provisioned") or data.get("requires_provisioned"):
        extras.append("provisioned hosts: required")
    if extras:
        print("  %s" % "  |  ".join(extras))
    if data.get("path"):
        print("  path: %s" % data["path"])
    if data.get("missing"):
        print()
        print("No # spa-run: metadata on this playbook.")
    requires = meta.get("requires") or []
    if requires:
        print()
        print("Requires:")
        for item in requires:
            print("  - %s" % item)
    inputs = meta.get("inputs") or []
    if inputs:
        print()
        print("Inputs:")
        for item in inputs:
            if isinstance(item, dict):
                name = item.get("name") or ""
                desc = item.get("description") or ""
                req = "required" if item.get("required") else "optional"
                print("  %s (%s)%s" % (name, req, (": " + desc) if desc else ""))
            else:
                print("  %s" % item)
    examples = meta.get("examples") or []
    if examples:
        print()
        print("Examples:")
        for item in examples:
            print("  %s" % item)
    related = data.get("related_playbooks") or []
    if related:
        from spa.app_playbooks import format_related_help

        print()
        for line in format_related_help(related):
            print(line)


def _add_mode_flags(parser) -> None:
    """Accept --json/--agent/--no-agent after the subcommand (parent flags stay first)."""
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="JSON output / agent envelope",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force agent mode (JSON envelope, never prompt); auto-detected otherwise",
    )
    parser.add_argument(
        "--no-agent",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force human mode (text output, may prompt) even inside an agent",
    )


def _add_command(sub, name, aliases=(), accept_mode_flags=True, **kwargs):
    parser = sub.add_parser(name, aliases=list(aliases), **kwargs)
    parser.set_defaults(canonical=name)
    if accept_mode_flags:
        _add_mode_flags(parser)
    return parser


def shell_copy_examples() -> str:
    from spa.shell import COPY_EXAMPLES

    return COPY_EXAMPLES


def _add_verbose(parser, help_text: str) -> None:
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help=help_text,
    )


def _add_ansible_output(parser) -> None:
    parser.add_argument(
        "--ansible-output",
        action="store_true",
        help="Show redacted Ansible-style output (live and from stored logs; not in agent output)",
    )
    _add_verbose(
        parser,
        "Stream Ansible's own output unredacted; may print secrets (Ansible verbosity: -- -vv)",
    )


def _want_ansible_output(args) -> bool:
    return bool(getattr(args, "verbose", False) or getattr(args, "ansible_output", False))


def _want_native_output(args) -> bool:
    """-v gives Ansible's own stdout; --ansible-output alone stays redacted."""
    return bool(getattr(args, "verbose", False))


def _add_env_selector(parser) -> None:
    parser.add_argument(
        "--env",
        dest="env_selector",
        metavar="NAME",
        help="Registered environment name or dest path",
    )


def _add_init_arguments(parser) -> None:
    parser.add_argument(
        "env_dir",
        nargs="?",
        help="Environment dest path, or a bare name under the default env parent",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        help="Registry name (default: folder basename). With --env-dir, also the child folder",
    )
    parser.add_argument(
        "--env-dir",
        dest="init_env_dir",
        metavar="DIR",
        help="Parent directory for this init only (requires --name). Does not change the default parent",
    )
    parser.add_argument("--example", metavar="NAME", help="Topology example id (see spa init --list)")
    parser.add_argument(
        "--provider",
        metavar="NAME",
        help="Provider example: aws or virtualbox (default: aws, or providers.yml)",
    )
    parser.add_argument("--list", action="store_true", help="List topology and provider examples")
    parser.add_argument("--from", dest="from_dir", metavar="DIR", help="Migrate an existing SPA environment")
    parser.add_argument("--migrate", action="store_true", help="Migrate the source environment into ENV_DIR")
    parser.add_argument("--keep-source", action="store_true", help="Keep state files in the migration source")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite .spa.yml (and strip old clone leftovers). "
        "Does not replace splunk_config.yml unless --example is also given.",
    )
    parser.add_argument("--venv", action="store_true", help="Create the environment Python virtualenv")
    parser.add_argument("--python", metavar="PATH", help="Python interpreter used to create the virtualenv")
    parser.add_argument("--ansible", help="Pin ansible==VER in the env venv")
    parser.add_argument("--pip", action="append", default=[], help="Extra pip spec (repeatable)")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip prerequisite checks after init")
    parser.add_argument(
        "--software-dir",
        metavar="DIR",
        help="Shared Splunk installers directory (saved in ~/.config/spa/paths.yml)",
    )
    parser.add_argument(
        "--baseconfig-dir",
        metavar="DIR",
        help="PS baseconfig apps directory (default: same as --software-dir)",
    )
    parser.add_argument(
        "--apps-dir",
        metavar="DIR",
        help="Local source: local apps directory (saved in ~/.config/spa/paths.yml)",
    )


def _add_hosts_option(parser) -> None:
    parser.add_argument(
        "--hosts",
        action="append",
        default=[],
        metavar="NAME",
        help=HOSTS_FLAG_HELP,
    )


def _paths(start_dir: Optional[str] = None, env_selector: Optional[str] = None):
    start = Path(start_dir).resolve() if start_dir else None
    paths = resolve_spa_paths(start_dir=start, env_selector=env_selector)
    apply_paths_env(paths)
    return paths


def _emit_result(result: CommandResult, as_agent: bool) -> int:
    emit(result.ok, data=result.data, error=result.error, as_agent=as_agent)
    return result.code


def _print_command_error(result: CommandResult) -> int:
    if result.error:
        print(result.error, file=sys.stderr)
    return result.code


def _print_init_messages(result: CommandResult) -> None:
    messages = (result.data or {}).get("messages") if isinstance(result.data, dict) else None
    if messages:
        print("\n".join(messages))


def _doctor_env_dir(selector: Optional[str], start_dir: Optional[str]) -> Optional[str]:
    if not selector:
        return None
    from spa.registry import lookup_env_path

    start = Path(start_dir).resolve() if start_dir else Path.cwd()
    return str(lookup_env_path(selector, relative_to=start))


def _run_init(args, session, as_agent: bool) -> int:
    if args.list:
        result = session.list_examples()
        if as_agent:
            return _emit_result(result, True)
        from spa.init import format_example_list

        print(format_example_list(result.data or {}))
        return 0
    from spa.registry import RegistryError, resolve_init_dest

    try:
        dest, registry_name, _ = resolve_init_dest(
            getattr(args, "env_dir", None),
            env_dir_flag=getattr(args, "init_env_dir", None),
            name=getattr(args, "name", None),
            force=bool(getattr(args, "force", False)),
        )
    except RegistryError as exc:
        emit(False, error=str(exc), as_agent=as_agent)
        return exc.code
    result = session.init(
        str(dest),
        example=args.example,
        example_set=args.example is not None,
        from_dir=args.from_dir,
        migrate_set=args.migrate or args.from_dir is not None,
        keep_source=args.keep_source,
        force=args.force,
        env_venv=args.venv or bool(args.python) or bool(args.ansible) or bool(args.pip),
        python=args.python,
        ansible=args.ansible,
        pip_pkgs=args.pip,
        skip_doctor=args.skip_doctor,
        rebuild_venv=bool(args.ansible or args.pip) and args.force,
        software_dir=args.software_dir,
        baseconfig_dir=args.baseconfig_dir,
        apps_dir=args.apps_dir,
        provider=args.provider,
        registry_name=registry_name,
    )
    if as_agent:
        payload = dict(result.data or {})
        payload["env_dir"] = str(dest.resolve())
        payload["name"] = registry_name
        emit(result.ok, data=payload, error=result.error, as_agent=True)
        return result.code
    _print_init_messages(result)
    if result.error:
        print(result.error, file=sys.stderr)
    return result.code


def _run_environment(args, session, paths, as_agent: bool, env_parser) -> int:
    from spa.paths import format_export

    action = getattr(args, "environment_cmd", None)
    if getattr(args, "export", False) and not action:
        if args.json:
            emit(True, data=paths.export_env(), as_agent=True)
        else:
            sys.stdout.write(format_export(paths))
        return 0
    if not action:
        env_parser.print_help()
        return 0
    if action == "list":
        result = session.environment_list()
        if as_agent:
            return _emit_result(result, True)
        if not result.ok:
            print(result.error or "environment list failed", file=sys.stderr)
            return result.code
        rows = (result.data or {}).get("environments") or []
        if not rows:
            print("No registered environments. Create one with spa environment init NAME")
            return 0
        for row in rows:
            mark = "*" if row.get("default") else " "
            missing = "" if row.get("exists") else "  (missing)"
            print("%s %s  %s%s" % (mark, row.get("name"), row.get("path"), missing))
        return 0
    if action == "init":
        return _run_init(args, session, as_agent)
    if action == "set":
        result = session.environment_set(
            env_dir=getattr(args, "set_env_dir", None),
            provider=getattr(args, "set_provider", None),
            software_dir=getattr(args, "set_software_dir", None),
            baseconfig_dir=getattr(args, "set_baseconfig_dir", None),
            apps_dir=getattr(args, "set_apps_dir", None),
            default=getattr(args, "set_default", None),
        )
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
            return result.code
        data = result.data or {}
        if data.get("paths_yml"):
            print("Updated %s" % data["paths_yml"])
        if data.get("environments_yml"):
            print("Default environment is %s" % data["default"])
        if "providers_yml" in data:
            if data.get("providers_yml"):
                print("Updated %s" % data["providers_yml"])
            else:
                print("Default provider is aws (providers.yml removed)")
        return result.code
    if action == "remove":
        result = session.environment_remove(
            args.name,
            confirm=bool(getattr(args, "yes", False)),
            force=bool(getattr(args, "force", False)),
        )
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
            return result.code
        print("Removed %s (%s)" % (result.data.get("name"), result.data.get("path")))
        return 0
    env_parser.print_help()
    return 0


def _error_agent_mode(argv: List[str]) -> bool:
    """Agent mode for a failure raised outside normal command dispatch."""
    head, _ = _split_passthrough(argv)
    head, _ = _split_native(head)
    if head and head[-1] in NATIVE_FLAG_COMMANDS:
        return False
    return agent_mode(
        force_agent="--agent" in head or "--json" in head,
        force_human="--no-agent" in head,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        return _run(raw)
    except ToolNotFound as exc:
        emit(False, error=str(exc), as_agent=_error_agent_mode(raw))
        return 1
    except ModuleNotFoundError as exc:
        # A requirement spa imports lazily (boto3, lxml, jmespath, ...). Report
        # the venv to build instead of a traceback from deep in a subcommand.
        if (exc.name or "") not in REQUIREMENT_DISTRIBUTIONS:
            raise
        paths = resolve_spa_paths(start_dir=None)
        emit(
            False,
            error=venv_setup_message(paths, [exc.name]),
            as_agent=_error_agent_mode(raw),
        )
        return 2


def _run(argv: Sequence[str]) -> int:
    argv = list(argv)
    head, extra = _split_passthrough(argv)
    help_name = _run_help_target(head)
    if help_name is not None and not extra:
        as_agent = agent_mode(
            force_agent="--agent" in head or "--json" in head,
            force_human="--no-agent" in head,
        )
        paths = _paths(_start_dir_from_head(head))
        session = open_session(start_dir=str(paths.spa_env_dir))
        if help_name == "":
            if as_agent:
                return _emit_result(
                    CommandResult(
                        ok=True,
                        data={
                            "usage": "spa run [--list] [NAME]",
                            "discover": ["spa --json run --list", "spa run NAME --help"],
                        },
                    ),
                    True,
                )
            _print_run_usage()
            return 0
        result = session.describe_playbook(help_name)
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
            return result.code
        _print_playbook_help(result.data or {})
        return 0
    head, native = _split_native(head)

    parse_as_agent = agent_mode(
        force_agent="--agent" in head or "--json" in head,
        force_human="--no-agent" in head,
    )

    class AgentAwareArgumentParser(argparse.ArgumentParser):
        """Keep parse failures machine-readable when an agent invokes spa."""

        def error(self, message):
            if parse_as_agent:
                emit(False, error="spa: %s" % message, as_agent=True)
                raise SystemExit(2)
            super().error(message)

    parser = AgentAwareArgumentParser(
        prog="spa",
        description=(
            "Splunk Enterprise deployment CLI — clustering, apps, licenses, hosts, "
            "and verification on AWS or VirtualBox. Agent-ready."
        ),
    )
    parser.add_argument("--json", action="store_true", help="JSON output / agent envelope")
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Force agent mode (JSON envelope, never prompt); auto-detected otherwise",
    )
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="Force human mode (text output, may prompt) even inside an agent",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Confirm a mutating command without prompting (required in agent mode)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose command output; on provision/deploy/destroy/run streams Ansible's own "
        "unredacted output (Ansible's own verbosity: -- -vv)",
    )
    parser.add_argument("--start-dir", help="Directory to resolve .spa.yml from")
    parser.add_argument(
        "--env",
        dest="env_selector",
        metavar="NAME",
        help="Registered environment name or dest path",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_init = _add_command(sub, "init", help="Scaffold or migrate an env dir (alias of spa environment init)")
    _add_init_arguments(p_init)

    p_feat = _add_command(
        sub,
        "features",
        aliases=["feat"],
        help="Look up config features (spa features list|show ID|search QUERY|keys)",
    )
    p_feat.add_argument(
        "features_cmd",
        nargs="?",
        default="list",
        choices=["list", "show", "search", "keys"],
        help="list (default), show, search, or keys",
    )
    p_feat.add_argument("features_arg", nargs="?", help="Feature id (show) or query (search)")
    p_feat.add_argument(
        "--keys",
        action="store_true",
        help="With show ID, include per-key types, constraints, and guidance",
    )

    p_apps = _add_command(
        sub,
        "apps",
        help="Search Splunkbase, print an apps[] snippet, or download an archive",
    )
    _add_env_selector(p_apps)
    apps_sub = p_apps.add_subparsers(dest="apps_cmd", metavar="ACTION", required=True)
    p_apps_search = apps_sub.add_parser("search", help="Search Splunkbase (compact rows)")
    _add_mode_flags(p_apps_search)
    p_apps_search.add_argument("query", nargs="+", help="Technology or app name keywords")
    p_apps_search.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="Max hits (default 10)",
    )
    p_apps_search.add_argument(
        "--type",
        dest="app_type",
        choices=list(SEARCH_TYPES),
        help="Filter Splunkbase type (%s)" % ", ".join(SEARCH_TYPES),
    )
    p_apps_search.add_argument(
        "--kind",
        choices=list(SEARCH_KINDS),
        help="Filter SPA kind (%s)" % ", ".join(SEARCH_KINDS),
    )
    p_apps_snippet = apps_sub.add_parser(
        "snippet",
        help="Print a kind-specific apps[] YAML snippet (Splunkbase id or local folder name)",
    )
    _add_mode_flags(p_apps_snippet)
    p_apps_snippet.add_argument(
        "app_id",
        metavar="APP_ID_OR_NAME",
        help="Splunkbase numeric app id, or local custom app folder with --source local",
    )
    p_apps_snippet.add_argument(
        "--version", default="latest", help="Release version (default latest)"
    )
    p_apps_snippet.add_argument(
        "--roles",
        help="Comma-separated target_roles (TA only; ignored for premium/content packs)",
    )
    p_apps_snippet.add_argument(
        "--source",
        choices=["splunkbase", "local"],
        default="splunkbase",
        help="Snippet source; local checks this environment's apps_dir (default splunkbase)",
    )
    p_apps_snippet.add_argument(
        "--local",
        dest="source",
        action="store_const",
        const="local",
        default=argparse.SUPPRESS,
        help="Shorthand for --source local",
    )
    p_apps_snippet.add_argument(
        "--customize",
        action="store_true",
        help="Include matching curated apps_playbooks customizations in the YAML",
    )
    p_apps_download = apps_sub.add_parser(
        "download",
        help="Download an archive into apps_dir",
        description=(
            "Download an archive into apps_dir (does not edit splunk_config.yml; use spa apps "
            "snippet for YAML). Credentials come from splunk_app_deployment.splunkbase_username / "
            "splunkbase_password in splunk_config.yml first, then SPLUNKBASE_USERNAME / "
            "SPLUNKBASE_PASSWORD."
        ),
    )
    _add_mode_flags(p_apps_download)
    p_apps_download.add_argument("app_id", help="Splunkbase numeric app id")
    p_apps_download.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm download (required in agent mode)",
    )
    p_apps_download.add_argument(
        "--version", default="latest", help="Release version (default latest)"
    )
    p_apps_download.add_argument(
        "--extract",
        action="store_true",
        help="Safely extract a folder-backed app into apps_dir and delete the archive (TA/ES only)",
    )
    p_apps_download.add_argument(
        "--overwrite",
        action="store_true",
        help="With --extract, replace an existing app folder in apps_dir",
    )

    p_val = _add_command(sub, "validate", aliases=["val"], help="Validate splunk_config.yml")
    p_val.add_argument("config", nargs="?", help="Configuration file (defaults to this environment)")
    p_val.add_argument("--check-licenses", action="store_true", help="Validate configured license files")
    p_val.add_argument(
        "--splunk-config-aws",
        action="store_true",
        help="Include legacy splunk_config_aws compatibility checks",
    )
    _add_env_selector(p_val)

    p_doc = _add_command(sub, "doctor", aliases=["doc"], help="Host prerequisite checks")
    p_doc.add_argument("--spa-home", metavar="DIR", help="Framework directory to inspect")
    p_doc.add_argument("--aws", action="store_true", help="Check AWS prerequisites")
    p_doc.add_argument("--virtualbox", action="store_true", help="Check VirtualBox prerequisites")
    p_doc.add_argument("--strict", action="store_true", help="Treat optional-tool warnings as failures")
    _add_env_selector(p_doc)

    p_venv = _add_command(
        sub,
        "venv",
        help="Inspect, create, reinstall, upgrade, or rebuild the SPA Python virtualenv",
    )
    venv_action = p_venv.add_mutually_exclusive_group()
    venv_action.add_argument("--path", action="store_const", const="path", dest="venv_action", help="Print the target venv path (default)")
    venv_action.add_argument("--create", action="store_const", const="create", dest="venv_action", help="Create the venv when missing")
    venv_action.add_argument("--reinstall", action="store_const", const="reinstall", dest="venv_action", help="Install requirements into the existing venv")
    venv_action.add_argument("--upgrade", action="store_const", const="upgrade", dest="venv_action", help="Upgrade packages and Ansible collections in the existing venv")
    venv_action.add_argument("--rebuild", action="store_const", const="rebuild", dest="venv_action", help="Delete, recreate, and install the venv")
    venv_scope = p_venv.add_mutually_exclusive_group()
    venv_scope.add_argument("--shared", action="store_true", help="Use SPA_HOME/.venv (default)")
    venv_scope.add_argument("--environment", action="store_true", help="Use this environment's .venv")
    p_venv.add_argument("--python", metavar="PATH", help="Python interpreter used to create the venv")
    p_venv.add_argument("--no-install", action="store_true", help="Create/rebuild without pip or Ansible collection installs")
    p_venv.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm creating or changing the venv (required in agent mode)",
    )
    _add_env_selector(p_venv)

    p_environment = _add_command(
        sub,
        "environment",
        aliases=["env"],
        help="List, init, set, or remove registered environments (alias: env)",
    )
    p_environment.add_argument(
        "--export",
        action="store_true",
        default=False,
        help="Print shell exports for external tools (spa commands resolve the env themselves)",
    )
    env_sub = p_environment.add_subparsers(dest="environment_cmd", metavar="ACTION")
    p_env_list = env_sub.add_parser("list", aliases=["ls"], help="List registered environments")
    _add_mode_flags(p_env_list)
    p_env_init = env_sub.add_parser("init", help="Scaffold or migrate an env dir")
    _add_mode_flags(p_env_init)
    _add_init_arguments(p_env_init)
    p_env_set = env_sub.add_parser(
        "set",
        help="Set user-level defaults in paths.yml / providers.yml (not per-env .spa.yml)",
    )
    _add_mode_flags(p_env_set)
    p_env_set.add_argument(
        "--env-dir",
        dest="set_env_dir",
        metavar="DIR",
        help="Default parent for name-only init (saved in paths.yml; omit when ~/Splunk-Platform-Automator)",
    )
    p_env_set.add_argument(
        "--software-dir",
        dest="set_software_dir",
        metavar="DIR",
        help="Shared Splunk installers directory (saved in paths.yml; also sets baseconfig_dir if unset)",
    )
    p_env_set.add_argument(
        "--baseconfig-dir",
        dest="set_baseconfig_dir",
        metavar="DIR",
        help="PS baseconfig apps directory (saved in paths.yml; default: same as --software-dir)",
    )
    p_env_set.add_argument(
        "--apps-dir",
        dest="set_apps_dir",
        metavar="DIR",
        help="Local source: local apps directory (saved in paths.yml)",
    )
    p_env_set.add_argument(
        "--default",
        dest="set_default",
        metavar="NAME",
        help="Registered environment used when cwd and SPA_ENV_DIR do not select one",
    )
    p_env_set.add_argument(
        "--provider",
        dest="set_provider",
        metavar="NAME",
        help="Default provider for init (aws is implicit; virtualbox writes providers.yml)",
    )
    p_env_remove = env_sub.add_parser(
        "remove",
        aliases=["rm"],
        help="Unregister and delete an env directory (not spa destroy)",
    )
    _add_mode_flags(p_env_remove)
    p_env_remove.add_argument("name", help="Registered environment name")
    p_env_remove.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm deleting the env directory",
    )
    p_env_remove.add_argument(
        "--force",
        action="store_true",
        help="Allow deleting a dir that looks deployed (local tree only; does not destroy cloud/VMs)",
    )

    p_prov = _add_command(
        sub, "provision", aliases=["prov"], help="Provision infrastructure for the configured provider"
    )
    _add_env_selector(p_prov)
    p_prov.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm provision (same as spa -y provision)",
    )
    _add_ansible_output(p_prov)
    p_deploy = _add_command(sub, "deploy", aliases=["dep"], help="Deploy Splunk")
    p_deploy.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm deploy (required in agent mode)",
    )
    p_deploy.add_argument(
        "--allow-unprovisioned",
        action="store_true",
        help="Skip the check that every config host is in inventory "
        "(e.g. spa deploy --yes --hosts idx1 --allow-unprovisioned)",
    )
    _add_hosts_option(p_deploy)
    _add_env_selector(p_deploy)
    _add_ansible_output(p_deploy)
    p_destroy = _add_command(
        sub, "destroy", aliases=["des"], help="Destroy infrastructure for the configured provider"
    )
    p_destroy.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm destroy (same as spa -y destroy)",
    )
    _add_env_selector(p_destroy)
    _add_ansible_output(p_destroy)
    p_suspend = _add_command(
        sub, "suspend", aliases=["sus"], help="Stop managed instances without destroying them"
    )
    p_suspend.add_argument(
        "-y", "--yes", action="store_true", default=argparse.SUPPRESS,
        help="Confirm power change (required in agent mode)",
    )
    p_suspend.add_argument("--no-wait", action="store_true", help="Return after requesting the stop")
    _add_hosts_option(p_suspend)
    _add_env_selector(p_suspend)
    _add_ansible_output(p_suspend)
    p_resume = _add_command(
        sub, "resume", aliases=["res"], help="Start managed instances and refresh inventory"
    )
    p_resume.add_argument(
        "-y", "--yes", action="store_true", default=argparse.SUPPRESS,
        help="Confirm power change (required in agent mode)",
    )
    _add_hosts_option(p_resume)
    _add_env_selector(p_resume)
    _add_ansible_output(p_resume)

    p_run = _add_command(
        sub,
        "run",
        help="Run a playbook by stem (spa run --list; spa run NAME --help)",
    )
    p_run.add_argument("name", nargs="?", help="Playbook stem from spa run --list")
    p_run.add_argument("--list", action="store_true", help="List available playbooks and summaries")
    p_run.add_argument("--dir", dest="playbook_dir", help="Extra env-dir folder to list/run")
    p_run.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm a mutating playbook (required in agent mode)",
    )
    _add_hosts_option(p_run)
    _add_env_selector(p_run)
    _add_ansible_output(p_run)
    p_run.add_argument(
        "--apps-playbook",
        help="For splunk_apps_playbook_run: curated stem, or env-relative path (e.g. ancustom/my_custom_playbook)",
    )

    p_logs = _add_command(
        sub,
        "logs",
        help="List or show per-environment run transcripts ($SPA_ENV_DIR/logs)",
    )
    p_logs.add_argument("run_id", nargs="?", help="Run id (filename stem)")
    p_logs.add_argument("--last", action="store_true", help="Show the most recent run")
    p_logs.add_argument("--follow", action="store_true", help="Follow the latest jsonl file")
    _add_ansible_output(p_logs)
    _add_env_selector(p_logs)

    p_hosts = _add_command(sub, "hosts", aliases=["h"], help="List, SSH, or copy using inventory hosts")
    _add_env_selector(p_hosts)
    p_hosts.add_argument(
        "-s",
        "--status",
        action="store_true",
        help="Include runtime power state and connectivity (skipped until hosts are provisioned)",
    )
    _add_hosts_option(p_hosts)
    hosts_sub = p_hosts.add_subparsers(dest="hosts_cmd", metavar="ACTION")
    p_hosts_list = hosts_sub.add_parser("list", aliases=["ls"], help="List hosts in this env")
    _add_mode_flags(p_hosts_list)
    p_hosts_list.add_argument(
        "-s",
        "--status",
        action="store_true",
        help="Include runtime power state and connectivity (skipped until hosts are provisioned)",
    )
    _add_hosts_option(p_hosts_list)
    p_hosts_ssh = hosts_sub.add_parser("ssh", help="SSH to one host")
    _add_mode_flags(p_hosts_ssh)
    p_hosts_ssh.add_argument("name", help="Inventory hostname")
    p_hosts_ssh.add_argument("ssh_args", nargs=argparse.REMAINDER, help="Additional arguments passed to ssh")
    p_hosts_copy = hosts_sub.add_parser(
        "copy",
        aliases=["cp"],
        help="Copy files with scp (SRC DST, remote side is HOST:PATH)",
        usage="spa hosts copy [-r] SRC [SRC ...] DST",
        description="Copy files between this machine and an env host.",
        epilog=shell_copy_examples(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_mode_flags(p_hosts_copy)
    p_hosts_copy.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Copy directories",
    )
    p_hosts_copy.add_argument(
        "paths",
        nargs=argparse.REMAINDER,
        metavar="SRC DST",
        help="Source and destination paths; HOST:PATH for the remote side",
    )

    # Flags for these are parsed by the wrapped tool (see _split_native).
    _add_command(
        sub, "shell", aliases=["sh"], help="SSH via inventory (alias of spa hosts ssh)",
        add_help=False, accept_mode_flags=False,
    )
    _add_command(sub, "aws", help="AWS discovery (spa aws --help)", add_help=False, accept_mode_flags=False)
    _add_command(
        sub, "licenses", aliases=["lic"], help="License discovery (spa licenses --help)",
        add_help=False, accept_mode_flags=False,
    )

    p_agent = _add_command(
        sub,
        "agent",
        help="Print the machine-readable command schema (spa agent schema)",
        usage="spa agent [schema]",
        description="Machine-readable contract for agents and skills: every command with\n"
        "its summary, flags, and whether it requires -y/--yes.\n"
        "\n"
        "JSON envelope by default (with or without --json). Human --markdown prints the\n"
        "catalog used for docs/commands.md; --json / agent mode still JSON.\n"
        "Playbooks are not in this schema; list them with spa --json run --list.",
        epilog=AGENT_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_agent.add_argument(
        "agent_cmd",
        nargs="?",
        default="schema",
        choices=["schema"],
        metavar="ACTION",
        help="schema (the default and only action today)",
    )
    p_agent.add_argument(
        "--markdown",
        action="store_true",
        help="Print GitHub-flavored markdown instead of JSON (human stdout; regenerate docs/commands.md)",
    )

    args = parser.parse_args(head)
    invoked = args.command
    if getattr(args, "canonical", None):
        args.command = args.canonical
    as_agent = agent_mode(force_agent=args.agent or args.json, force_human=args.no_agent)
    # These print their own output (aws/licenses have a native --json); an
    # envelope would only apply to a path-resolution failure below.
    if invoked in NATIVE_FLAG_COMMANDS and not args.agent:
        as_agent = agent_mode(force_agent=False, force_human=args.no_agent)

    try:
        paths = _paths(args.start_dir, getattr(args, "env_selector", None))
    except Exception as exc:
        emit(False, error=str(exc), as_agent=as_agent)
        return 1

    session = open_session(paths=paths)

    if args.command is None:
        parser.print_help()
        return 0

    native_help_only = invoked in NATIVE_FLAG_COMMANDS and set(native) <= {"-h", "--help"}
    apps_cmd = getattr(args, "apps_cmd", None)
    apps_without_env = args.command == "apps" and apps_cmd in {"search", "snippet"}
    if (
        args.command not in {"init", "agent", "environment", "doctor", "features", "venv"}
        and not native_help_only
        and not apps_without_env
    ):
        missing = env_dir_required_error(paths)
        if missing:
            emit(False, error=missing, as_agent=as_agent)
            return 2

    if args.command not in VENV_OPTIONAL_COMMANDS and not native_help_only:
        not_ready = venv_required_error(paths)
        if not_ready:
            emit(False, error=not_ready, as_agent=as_agent)
            return 2

    if args.command == "agent":
        result = session.schema()
        if getattr(args, "markdown", False) and not as_agent:
            sys.stdout.write(format_schema_markdown(result.data))
            return 0
        emit(True, data=result.data, as_agent=True)
        return 0

    if args.command == "environment":
        return _run_environment(args, session, paths, as_agent, p_environment)

    if args.command == "init":
        return _run_init(args, session, as_agent)

    if args.command == "features":
        action = args.features_cmd or "list"
        ident = args.features_arg if action == "show" else None
        query = args.features_arg if action == "search" else None
        result = session.features(
            action=action,
            ident=ident,
            query=query,
            include_keys=bool(args.keys),
        )
        if as_agent:
            return _emit_result(result, True)
        if not result.ok:
            print(result.error or "features failed", file=sys.stderr)
            return result.code
        data = result.data or {}
        if action in {"list", "search"}:
            from spa.catalog import format_feature_rows

            rows = data.get("features") or []
            if not rows and action == "search":
                print("No features matched %r" % query)
                return 0
            print(format_feature_rows(rows))
            return 0
        if action == "show":
            print(data.get("text") or "")
            return 0
        if action == "keys":
            missing = data.get("missing_from_catalog") or []
            missing_detail = data.get("missing_key_detail") or []
            print(
                "%s catalog features, %s schema keys missing from catalog, "
                "%s catalog keys missing details"
                % (data.get("features"), len(missing), len(missing_detail))
            )
            for key in missing:
                print("missing: %s" % key)
            for key in missing_detail:
                print("missing detail: %s" % key)
            return 0 if not missing and not missing_detail else 1
        return 0

    if args.command == "apps":
        def _roles():
            raw = getattr(args, "roles", None) or ""
            return [part.strip() for part in raw.split(",") if part.strip()] or None

        action = args.apps_cmd
        result = session.apps(
            action=action,
            query=" ".join(getattr(args, "query", None) or []),
            app_id=getattr(args, "app_id", None),
            limit=int(getattr(args, "limit", 10) or 10),
            app_type=getattr(args, "app_type", None),
            kind=getattr(args, "kind", None),
            version=getattr(args, "version", None) or "latest",
            roles=_roles(),
            source=getattr(args, "source", "splunkbase"),
            extract=bool(getattr(args, "extract", False)),
            overwrite=bool(getattr(args, "overwrite", False)),
            customize=bool(getattr(args, "customize", False)),
            confirm=args.yes,
            agent=as_agent,
        )
        if as_agent:
            return _emit_result(result, True)
        if not result.ok:
            print(result.error or "apps failed", file=sys.stderr)
            return result.code
        data = result.data or {}
        if action == "search":
            from spa.apps import format_search_text

            sys.stdout.write(format_search_text(data.get("query") or "", data.get("apps") or []))
            return 0
        if action == "download":
            if data.get("extracted_path"):
                print("Extracted: %s" % data["extracted_path"])
                print("Removed archive after extract")
            else:
                print("Downloaded: %s" % (data.get("path") or ""))
            return 0
        sys.stdout.write(data.get("snippet") or "")
        return 0

    if args.command == "validate":
        from spa.validate import format_validate_text

        result = session.validate(
            config=args.config,
            check_licenses=args.check_licenses,
            splunk_config_aws=args.splunk_config_aws,
            agent=as_agent,
        )
        if as_agent:
            return _emit_result(result, True)
        sys.stdout.write(format_validate_text(result))
        if result.error:
            print(result.error, file=sys.stderr)
        validation = ((result.data or {}).get("license_validation") or {})
        for warning in validation.get("warnings") or []:
            print("License warning: %s" % warning, file=sys.stderr)
        return result.code

    if args.command == "doctor":
        from spa.doctor import format_doctor_text

        result = session.doctor(
            spa_home=args.spa_home,
            env_dir=_doctor_env_dir(getattr(args, "env_selector", None), args.start_dir),
            aws=args.aws,
            virtualbox=args.virtualbox,
            strict=args.strict,
        )
        want_json = as_agent or bool(getattr(args, "json", False))
        if want_json:
            return _emit_result(result, True)
        sys.stdout.write(format_doctor_text(result))
        return result.code

    if args.command == "venv":
        if not as_agent:
            def _venv_step(event):
                step = (event or {}).get("step")
                if step:
                    print(step, flush=True)

            session.on_progress = _venv_step
        result = session.venv(
            action=getattr(args, "venv_action", None) or "path",
            environment=bool(args.environment),
            python=args.python,
            no_install=bool(args.no_install),
            confirm=args.yes,
            agent=as_agent,
        )
        if as_agent:
            payload = dict(result.data or {})
            if result.ok:
                payload.pop("log", None)
            emit(result.ok, data=payload, error=result.error, as_agent=True)
            return result.code
        data = result.data or {}
        action = getattr(args, "venv_action", None) or "path"
        if not result.ok:
            log = data.get("log") or ""
            if log:
                sys.stderr.write(log if log.endswith("\n") else log + "\n")
            if result.error and result.error not in log:
                print(result.error, file=sys.stderr)
            return result.code
        if args.verbose and data.get("log"):
            sys.stderr.write(data["log"])
        if action == "path":
            print((data.get("stdout") or data.get("path") or "").strip())
        return result.code

    if args.command == "logs":
        result = session.logs(
            run_id=getattr(args, "run_id", None),
            last=bool(getattr(args, "last", False)),
            follow=bool(getattr(args, "follow", False)) and not as_agent,
            ansible_output=_want_ansible_output(args),
        )
        if as_agent:
            payload = dict(result.data or {})
            payload.pop("transcript", None)
            payload.pop("replay", None)
            emit(result.ok, data=payload or None, error=result.error, as_agent=True)
            return result.code
        if not result.ok:
            print(result.error or "logs failed", file=sys.stderr)
            return result.code
        data = result.data or {}
        if args.follow:
            return 0
        if "runs" in data and not args.last and not args.run_id:
            rows = data.get("runs") or []
            if not rows:
                print("No runs in %s/logs" % paths.spa_env_dir)
                return 0
            for row in rows:
                print(
                    "%s  rc=%s  %s"
                    % (row.get("run_id"), row.get("rc"), row.get("command"))
                )
            return 0
        if _want_ansible_output(args):
            sys.stdout.write(data.get("replay") or "")
        else:
            sys.stdout.write(data.get("transcript") or "")
        return 0

    if args.command in {"provision", "destroy"}:
        extra = list(extra)
        result = getattr(session, args.command)(
            extra,
            confirm=args.yes,
            agent=as_agent,
            ansible_output=_want_ansible_output(args),
            native_output=_want_native_output(args),
        )
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
        return result.code

    if args.command == "deploy":
        extra = list(extra)
        result = session.deploy(
            extra,
            verbose=_want_ansible_output(args),
            hosts=getattr(args, "hosts", None),
            confirm=args.yes,
            agent=as_agent,
            skip_provision_check=bool(getattr(args, "allow_unprovisioned", False)),
            ansible_output=_want_ansible_output(args),
            native_output=_want_native_output(args),
        )
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
        return result.code

    if args.command in {"suspend", "resume"}:
        if extra:
            emit(
                False,
                error="%s does not accept arguments after --" % args.command,
                as_agent=as_agent,
            )
            return 1
        result = getattr(session, args.command)(
            confirm=args.yes,
            wait=not getattr(args, "no_wait", False),
            agent=as_agent,
            hosts=getattr(args, "hosts", None),
            ansible_output=_want_ansible_output(args),
        )
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
            return result.code
        from spa.hosts import format_names

        data = result.data or {}
        instances = data.get("instances") or []
        print(
            "%s %s complete (%d host%s)."
            % (
                str(data.get("provider") or "").upper(),
                args.command,
                len(instances),
                "" if len(instances) == 1 else "s",
            )
        )
        by_state: dict = {}
        for instance in instances:
            by_state.setdefault(instance["state"], []).append(instance["name"])
        for state, names in sorted(by_state.items()):
            print("  %s (%d): %s" % (state, len(names), format_names(sorted(names))))
        if data.get("inventory"):
            print("  inventory: %s" % data["inventory"])
        if data.get("note"):
            print("  note: %s" % data["note"])
        return 0

    if args.command == "run":
        if args.list or not args.name:
            result = session.catalog(extra_dir=args.playbook_dir)
            if as_agent or args.json:
                return _emit_result(result, True)
            _print_catalog(result.data or [], paths)
            return 0
        extra_args = list(extra)
        result = session.run(
            args.name,
            extra=extra_args,
            extra_dir=args.playbook_dir,
            verbose=_want_ansible_output(args),
            hosts=getattr(args, "hosts", None),
            confirm=args.yes,
            agent=as_agent,
            apps_playbook=getattr(args, "apps_playbook", None),
            ansible_output=_want_ansible_output(args),
            native_output=_want_native_output(args),
        )
        if as_agent:
            return _emit_result(result, True)
        if result.data and result.data.get("renamed_from"):
            print(
                "use spa run %s" % (result.data.get("use") or result.data.get("playbook")),
                file=sys.stderr,
            )
        if result.error:
            print(result.error, file=sys.stderr)
            if (result.data or {}).get("provisioned") is not False:
                print("spa run --list for the catalog", file=sys.stderr)
        return result.code

    if args.command == "hosts":
        hosts_cmd = args.hosts_cmd or "list"
        if hosts_cmd in {"list", "ls"}:
            result = session.hosts_list(
                status=bool(getattr(args, "status", False)),
                hosts=getattr(args, "hosts", None),
            )
            if as_agent:
                return _emit_result(result, True)
            if result.error:
                print(result.error, file=sys.stderr)
                return result.code
            data = result.data or {}
            show_status = bool(getattr(args, "status", False))
            if (
                data.get("provider")
                and show_status
                and data.get("provisioned") is not False
            ):
                print("Checking %s status..." % str(data["provider"]).upper(), file=sys.stderr)
            if data.get("provider_error"):
                print("Warning: %s" % data["provider_error"], file=sys.stderr)
            from spa.shell import format_host_status

            for row in data.get("hosts") or []:
                roles_str = ""
                if row.get("roles"):
                    roles_str = " (%s)" % ", ".join(row["roles"])
                extra_info = format_host_status(row) if show_status else ""
                print("%s%s%s" % (row["name"], roles_str, extra_info))
            return 0
        from spa import shell as shell_mod

        if hosts_cmd == "ssh":
            blocked = session._require_provisioned()
            if blocked:
                return _print_command_error(blocked)
            try:
                shell_mod.main([args.name, *list(getattr(args, "ssh_args", []) or []), *extra])
            except SystemExit as exc:
                return exc.code if isinstance(exc.code, int) else 1
            return 0
        if hosts_cmd in {"copy", "cp"}:
            paths_args = [*extra, *list(getattr(args, "paths", []) or [])]
            if getattr(args, "recursive", False):
                paths_args.insert(0, "-r")
            if len([item for item in paths_args if not item.startswith("-")]) < 2:
                print(
                    "spa hosts copy needs a source and a destination, "
                    "for example: spa hosts copy app.tgz idx1:/tmp/",
                    file=sys.stderr,
                )
                return 1
            blocked = session._require_provisioned()
            if blocked:
                return _print_command_error(blocked)
            try:
                shell_mod.apply_spa_env()
                shell_mod.run_scp(paths_args)
            except shell_mod.ShellError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            except SystemExit as exc:
                return exc.code if isinstance(exc.code, int) else 1
            return 0
        parser.print_help()
        return 1

    if args.command == "shell":
        from spa import shell as shell_mod

        # SSH/SCP is interactive: no JSON envelope even in agent mode.
        blocked = session._require_provisioned()
        if blocked:
            return _print_command_error(blocked)
        try:
            shell_mod.main([*native, *extra])
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1
        return 0

    if args.command == "aws":
        from spa import aws as aws_mod

        try:
            return aws_mod.main([*native, *extra])
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1

    if args.command == "licenses":
        from spa import licenses as licenses_mod

        try:
            return licenses_mod.main([*native, *extra])
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1

    parser.print_help()
    return 1
