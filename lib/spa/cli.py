"""spa command-line entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from spa.agent import agent_mode, emit
from spa.api import CommandResult, open_session
from spa.executil import ToolNotFound, apply_paths_env
from spa.paths import resolve_spa_paths


# Commands whose flags belong to the wrapped tool, not to spa (spa shell idx1,
# spa aws --check-auth). argparse.REMAINDER drops a leading option, so these are
# split off before the spa parser runs.
NATIVE_FLAG_COMMANDS = ("shell", "sh", "aws", "licenses", "lic")
GLOBAL_OPTS_WITH_VALUE = ("--start-dir",)
HOSTS_FLAG_HELP = "only these hosts (names or roles from this env)"
AGENT_EXAMPLES = """examples:
  spa agent schema       command schema (name, summary, flags, requires_confirmation)
  spa agent              same as spa agent schema
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
    skip_run_value = {"--dir", "--hosts"}
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
    print("usage: spa run [-h] [--list] [--dir DIR] [--hosts NAME] [-y] [NAME]")
    print()
    print("Run a playbook by stem, or list/describe playbooks without executing Ansible.")
    print()
    print("  spa run --list              catalog (name — summary)")
    print("  spa run NAME --help         description, risk, inputs, examples")
    print("  spa run NAME [-y] [--hosts NAME] [-- ansible-playbook args]")
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


def _add_command(sub, name, aliases=(), **kwargs):
    parser = sub.add_parser(name, aliases=list(aliases), **kwargs)
    parser.set_defaults(canonical=name)
    return parser


def shell_copy_examples() -> str:
    from spa.shell import COPY_EXAMPLES

    return COPY_EXAMPLES


def _add_hosts_option(parser) -> None:
    parser.add_argument(
        "--hosts",
        action="append",
        default=[],
        metavar="NAME",
        help=HOSTS_FLAG_HELP,
    )


def _paths(start_dir: Optional[str] = None):
    start = Path(start_dir).resolve() if start_dir else None
    paths = resolve_spa_paths(start_dir=start)
    apply_paths_env(paths)
    return paths


def _emit_result(result: CommandResult, as_agent: bool) -> int:
    emit(result.ok, data=result.data, error=result.error, as_agent=as_agent)
    return result.code


def _print_init_messages(result: CommandResult) -> None:
    messages = (result.data or {}).get("messages") if isinstance(result.data, dict) else None
    if messages:
        print("\n".join(messages))


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

    import argparse

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
        description="Splunk Platform Automator — env dirs against one SPA_HOME prefix.",
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
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose command output")
    parser.add_argument("--start-dir", help="Directory to resolve .spa.yml from")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_init = _add_command(sub, "init", help="Scaffold or migrate an env dir")
    p_init.add_argument("env_dir", nargs="?", help="Environment directory to create or migrate")
    p_init.add_argument("--example", metavar="NAME", help="Copy a bundled example configuration")
    p_init.add_argument("--list", action="store_true", help="List example YAML names")
    p_init.add_argument("--from", dest="from_dir", metavar="DIR", help="Migrate an existing SPA environment")
    p_init.add_argument("--migrate", action="store_true", help="Migrate the source environment into ENV_DIR")
    p_init.add_argument("--keep-source", action="store_true", help="Keep state files in the migration source")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite .spa.yml / .envrc (and strip old clone leftovers). "
        "Does not replace splunk_config.yml unless --example is also given.",
    )
    p_init.add_argument("--venv", action="store_true", help="Create the environment Python virtualenv")
    p_init.add_argument("--python", metavar="PATH", help="Python interpreter used to create the virtualenv")
    p_init.add_argument("--ansible", help="Pin ansible==VER in the env venv")
    p_init.add_argument("--pip", action="append", default=[], help="Extra pip spec (repeatable)")
    p_init.add_argument("--no-envrc", action="store_true", help="Do not create a direnv .envrc file")
    p_init.add_argument("--skip-doctor", action="store_true", help="Skip prerequisite checks after init")

    p_val = _add_command(sub, "validate", aliases=["val"], help="Validate splunk_config.yml")
    p_val.add_argument("config", nargs="?", help="Configuration file (defaults to this environment)")
    p_val.add_argument("--check-licenses", action="store_true", help="Validate configured license files")
    p_val.add_argument(
        "--splunk-config-aws",
        action="store_true",
        help="Include legacy splunk_config_aws compatibility checks",
    )

    p_doc = _add_command(sub, "doctor", aliases=["doc"], help="Host prerequisite checks")
    p_doc.add_argument("--spa-home", metavar="DIR", help="Framework directory to inspect")
    p_doc.add_argument("--env", metavar="DIR", help="Environment directory to inspect")
    p_doc.add_argument("--aws", action="store_true", help="Check AWS prerequisites")
    p_doc.add_argument("--virtualbox", action="store_true", help="Check VirtualBox prerequisites")
    p_doc.add_argument("--strict", action="store_true", help="Treat optional-tool warnings as failures")
    p_doc.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p_doc.add_argument("--fix-direnv", action="store_true", help="Install the direnv shell hook when possible")

    p_env = _add_command(sub, "env", help="Print export statements")
    p_env.add_argument("--export", action="store_true", default=True, help="Print shell export statements")
    p_env.add_argument("--start-dir", metavar="DIR", help="Directory used to resolve .spa.yml")

    p_prov = _add_command(
        sub, "provision", aliases=["prov"], help="Provision infrastructure for the configured provider"
    )
    p_prov.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Auto-approve Terraform apply (same as spa -y provision)",
    )
    p_deploy = _add_command(sub, "deploy", aliases=["dep"], help="Deploy Splunk")
    p_deploy.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirm deploy (required in agent mode)",
    )
    _add_hosts_option(p_deploy)
    p_destroy = _add_command(sub, "destroy", help="Destroy infrastructure for the configured provider")
    p_destroy.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Auto-approve Terraform destroy (same as spa -y destroy)",
    )
    p_suspend = _add_command(
        sub, "suspend", aliases=["sus"], help="Stop managed cloud instances without destroying them"
    )
    p_suspend.add_argument(
        "-y", "--yes", action="store_true", default=argparse.SUPPRESS,
        help="Confirm power change (required in agent mode)",
    )
    p_suspend.add_argument("--no-wait", action="store_true", help="Return after requesting the stop")
    _add_hosts_option(p_suspend)
    p_resume = _add_command(
        sub, "resume", aliases=["res"], help="Start managed cloud instances and refresh inventory"
    )
    p_resume.add_argument(
        "-y", "--yes", action="store_true", default=argparse.SUPPRESS,
        help="Confirm power change (required in agent mode)",
    )
    _add_hosts_option(p_resume)

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

    p_hosts = _add_command(sub, "hosts", aliases=["h"], help="List, SSH, or copy using inventory hosts")
    p_hosts.add_argument(
        "--status",
        action="store_true",
        help="Include runtime power state and connectivity",
    )
    _add_hosts_option(p_hosts)
    hosts_sub = p_hosts.add_subparsers(dest="hosts_cmd", metavar="ACTION")
    p_hosts_list = hosts_sub.add_parser("list", aliases=["ls"], help="List hosts in this env")
    p_hosts_list.add_argument(
        "--status",
        action="store_true",
        help="Include runtime power state and connectivity",
    )
    _add_hosts_option(p_hosts_list)
    p_hosts_ssh = hosts_sub.add_parser("ssh", help="SSH to one host")
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
    _add_command(sub, "shell", aliases=["sh"], help="SSH via inventory (alias of spa hosts ssh)", add_help=False)
    _add_command(sub, "aws", help="AWS discovery (spa aws --help)", add_help=False)
    _add_command(sub, "licenses", aliases=["lic"], help="License discovery (spa licenses --help)", add_help=False)

    p_agent = _add_command(
        sub,
        "agent",
        help="Print the machine-readable command schema (spa agent schema)",
        usage="spa agent [schema]",
        description="Machine-readable contract for agents and skills: every command with\n"
        "its summary, flags, and whether it requires -y/--yes.\n"
        "\n"
        "Always prints the JSON envelope, with or without --json, because only agents\n"
        "read it. Playbooks are not in this schema; list them with spa --json run --list.",
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
        paths = _paths(args.start_dir)
    except Exception as exc:
        emit(False, error=str(exc), as_agent=as_agent)
        return 1

    session = open_session(paths=paths)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "agent":
        result = session.schema()
        emit(True, data=result.data, as_agent=True)
        return 0

    if args.command == "env":
        from spa.paths import format_export

        # direnv does eval "$(spa env --export)" — never wrap that in JSON.
        if args.json:
            emit(True, data=paths.export_env(), as_agent=True)
        else:
            sys.stdout.write(format_export(paths))
        return 0

    if args.command == "init":
        if args.list:
            result = session.list_examples()
            if as_agent:
                return _emit_result(result, True)
            print("\n".join(result.data or []))
            return 0
        if not args.env_dir:
            print("spa init: env dir is required", file=sys.stderr)
            return 1
        result = session.init(
            args.env_dir,
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
            write_envrc_file=not args.no_envrc,
            skip_doctor=args.skip_doctor,
            rebuild_venv=bool(args.ansible or args.pip) and args.force,
        )
        if as_agent:
            emit(
                result.ok,
                data={"env_dir": str(Path(args.env_dir).resolve())},
                error=result.error,
                as_agent=True,
            )
            return result.code
        _print_init_messages(result)
        if result.error:
            print(result.error, file=sys.stderr)
        return result.code

    if args.command == "validate":
        from spa.validate import format_validate_text

        result = session.validate(
            config=args.config,
            check_licenses=args.check_licenses,
            splunk_config_aws=args.splunk_config_aws,
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
            env_dir=args.env,
            aws=args.aws,
            virtualbox=args.virtualbox,
            strict=args.strict,
            fix_direnv=args.fix_direnv,
        )
        want_json = as_agent or bool(getattr(args, "json", False))
        if want_json:
            return _emit_result(result, True)
        sys.stdout.write(format_doctor_text(result))
        return result.code

    if args.command in {"provision", "destroy"}:
        extra = list(extra)
        result = getattr(session, args.command)(extra, confirm=args.yes, agent=as_agent)
        if as_agent:
            return _emit_result(result, True)
        if result.error:
            print(result.error, file=sys.stderr)
        return result.code

    if args.command == "deploy":
        extra = list(extra)
        result = session.deploy(
            extra,
            verbose=args.verbose,
            hosts=getattr(args, "hosts", None),
            confirm=args.yes,
            agent=as_agent,
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
            verbose=args.verbose,
            hosts=getattr(args, "hosts", None),
            confirm=args.yes,
            agent=as_agent,
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
            print("spa run --list for the catalog", file=sys.stderr)
        return result.code

    if args.command == "hosts":
        hosts_cmd = args.hosts_cmd or "list"
        if hosts_cmd in {"list", "ls"}:
            result = session.hosts_list(
                status=bool(getattr(args, "status", False) or args.verbose),
                hosts=getattr(args, "hosts", None),
            )
            if as_agent:
                return _emit_result(result, True)
            if result.error:
                print(result.error, file=sys.stderr)
                return result.code
            data = result.data or {}
            if data.get("provider") and getattr(args, "status", False):
                print("Checking %s status..." % str(data["provider"]).upper(), file=sys.stderr)
            if data.get("provider_error"):
                print("Warning: %s" % data["provider_error"], file=sys.stderr)
            for row in data.get("hosts") or []:
                roles_str = ""
                if row.get("roles"):
                    roles_str = " (%s)" % ", ".join(row["roles"])
                extra_info = ""
                if row.get("ansible") or row.get("provider_status"):
                    provider_status = ""
                    if row.get("provider_status"):
                        provider_status = ", %s: %s" % (
                            str(row.get("provider") or "provider").upper(),
                            row["provider_status"],
                        )
                    extra_info = " - Ansible: %s%s" % (
                        row.get("ansible", "N/A"),
                        provider_status,
                    )
                print("%s%s%s" % (row["name"], roles_str, extra_info))
            return 0
        from spa import shell as shell_mod

        if hosts_cmd == "ssh":
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
