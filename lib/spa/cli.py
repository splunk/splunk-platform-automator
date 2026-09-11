"""spa command-line entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from spa.agent import COMMAND_SCHEMA, agent_mode, emit
from spa.executil import apply_paths_env
from spa.paths import resolve_spa_paths


def _split_passthrough(argv: Sequence[str]) -> Tuple[List[str], List[str]]:
    if "--" in argv:
        idx = list(argv).index("--")
        return list(argv[:idx]), list(argv[idx + 1 :])
    return list(argv), []


def _paths(start_dir: Optional[str] = None):
    start = Path(start_dir).resolve() if start_dir else None
    paths = resolve_spa_paths(start_dir=start)
    apply_paths_env(paths)
    return paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    head, extra = _split_passthrough(argv)

    import argparse

    parser = argparse.ArgumentParser(
        prog="spa",
        description="Splunk Platform Automator — env dirs against one SPA_HOME prefix.",
    )
    parser.add_argument("--json", action="store_true", help="JSON output / agent envelope")
    parser.add_argument("--agent", action="store_true")
    parser.add_argument("--no-agent", action="store_true")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive / auto-approve")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--start-dir", help="Directory to resolve .spa.yml from")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Scaffold or migrate an env dir")
    p_init.add_argument("env_dir", nargs="?")
    p_init.add_argument("--example")
    p_init.add_argument("--list", action="store_true", help="List example YAML names")
    p_init.add_argument("--from", dest="from_dir")
    p_init.add_argument("--migrate", action="store_true")
    p_init.add_argument("--keep-source", action="store_true")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite .spa.yml / .envrc (and strip old clone leftovers). "
        "Does not replace splunk_config.yml unless --example is also given.",
    )
    p_init.add_argument("--venv", action="store_true")
    p_init.add_argument("--python")
    p_init.add_argument("--ansible", help="Pin ansible==VER in the env venv")
    p_init.add_argument("--pip", action="append", default=[], help="Extra pip spec (repeatable)")
    p_init.add_argument("--no-envrc", action="store_true")
    p_init.add_argument("--skip-doctor", action="store_true")

    p_val = sub.add_parser("validate", help="Validate splunk_config.yml")
    p_val.add_argument("config", nargs="?")
    p_val.add_argument("--check-licenses", action="store_true")
    p_val.add_argument("--splunk-config-aws", action="store_true")

    p_doc = sub.add_parser("doctor", help="Host prerequisite checks")
    p_doc.add_argument("--spa-home")
    p_doc.add_argument("--env")
    p_doc.add_argument("--aws", action="store_true")
    p_doc.add_argument("--virtualbox", action="store_true")
    p_doc.add_argument("--strict", action="store_true")
    p_doc.add_argument("--json", action="store_true")
    p_doc.add_argument("--fix-direnv", action="store_true")

    p_env = sub.add_parser("env", help="Print export statements")
    p_env.add_argument("--export", action="store_true", default=True)
    p_env.add_argument("--start-dir")

    sub.add_parser("provision", help="Provision AWS with Terraform")
    sub.add_parser("deploy", help="Deploy Splunk")
    sub.add_parser("destroy", help="Destroy AWS hosts")

    p_run = sub.add_parser("run", help="Run a playbook by stem")
    p_run.add_argument("name", nargs="?")
    p_run.add_argument("--list", action="store_true")
    p_run.add_argument("--dir", dest="playbook_dir", help="Extra env-dir folder to list/run")

    p_shell = sub.add_parser("shell", help="SSH/SCP via inventory")
    p_shell.add_argument("shell_args", nargs=argparse.REMAINDER)

    p_aws = sub.add_parser("aws", help="AWS discovery")
    p_aws.add_argument("aws_args", nargs=argparse.REMAINDER)

    p_lic = sub.add_parser("licenses", help="License discovery")
    p_lic.add_argument("license_args", nargs=argparse.REMAINDER)

    p_agent = sub.add_parser("agent", help="Agent helpers")
    p_agent.add_argument("agent_cmd", nargs="?", default="schema")

    args = parser.parse_args(head)
    as_agent = agent_mode(force_agent=args.agent or args.json, force_human=args.no_agent)
    # spa aws --json is native JSON; still allow global --json as envelope
    if args.command in {"aws", "licenses"} and not args.agent and not args.no_agent:
        as_agent = agent_mode(force_agent=False, force_human=args.no_agent)

    try:
        paths = _paths(args.start_dir)
    except Exception as exc:
        emit(False, error=str(exc), as_agent=as_agent)
        return 1

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "agent":
        emit(True, data=COMMAND_SCHEMA, as_agent=True)
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
        from spa import init as init_mod

        if args.list:
            names = init_mod.list_examples(paths.spa_home)
            if as_agent:
                emit(True, data=names, as_agent=True)
            else:
                print("\n".join(names))
            return 0
        if not args.env_dir:
            print("spa init: env dir is required", file=sys.stderr)
            return 1
        try:
            rc = init_mod.init_env(
                Path(args.env_dir),
                paths.spa_home,
                example=args.example,
                example_set=args.example is not None,
                from_dir=Path(args.from_dir) if args.from_dir else None,
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
                emit(rc == 0, data={"env_dir": str(Path(args.env_dir).resolve())}, as_agent=True)
            return rc
        except init_mod.InitError as exc:
            emit(False, error=str(exc), as_agent=as_agent)
            return exc.code

    if args.command == "validate":
        from spa import validate as validate_mod

        val_argv = []
        if args.check_licenses:
            val_argv.append("--check-licenses")
        if args.splunk_config_aws:
            val_argv.append("--splunk-config-aws")
        if args.config:
            val_argv.append(args.config)
        rc = validate_mod.run(val_argv)
        if as_agent:
            emit(rc == 0, error=None if rc == 0 else "validate failed", as_agent=True)
        return rc

    if args.command == "doctor":
        from spa import doctor as doctor_mod

        doc_argv = []
        if args.spa_home:
            doc_argv.extend(["--spa-home", args.spa_home])
        if args.env:
            doc_argv.extend(["--env", args.env])
        for flag in ("aws", "virtualbox", "strict", "json", "fix_direnv"):
            if getattr(args, flag, False):
                doc_argv.append("--" + flag.replace("_", "-"))
        rc = doctor_mod.run(doc_argv)
        if as_agent and not args.json:
            emit(rc == 0, error=None if rc == 0 else "doctor failed", as_agent=True)
        return rc

    if args.command in {"provision", "deploy", "destroy"}:
        from spa.playbooks import PlaybookError, resolve, run_playbook

        names = {
            "provision": "provision_terraform_aws",
            "deploy": "deploy_site",
            "destroy": "destroy_terraform_aws",
        }
        extra = list(extra)
        if args.command == "provision" and args.yes:
            extra = ["-e", "auto_approve=true", *extra]
        if args.command == "destroy" and not args.yes and as_agent:
            emit(False, error="destroy requires -y in agent mode", as_agent=True)
            return 1
        try:
            playbook = resolve(names[args.command], paths)
        except PlaybookError as exc:
            emit(False, error=str(exc), as_agent=as_agent)
            return 1
        if args.verbose:
            extra = ["-v", *extra]
        rc = run_playbook(playbook, paths, extra)
        if as_agent:
            emit(rc == 0, error=None if rc == 0 else "playbook failed", as_agent=True)
        return rc

    if args.command == "run":
        from spa.playbooks import PlaybookError, catalog, resolve, run_playbook

        if args.list or not args.name:
            rows = catalog(paths, extra_dir=args.playbook_dir)
            if as_agent or args.json:
                emit(True, data=rows, as_agent=True)
            else:
                for row in rows:
                    print("%s\t%s" % (row["name"], row["source"]))
            return 0 if args.list or not args.name else 1
        try:
            playbook = resolve(args.name, paths, extra_dir=args.playbook_dir)
        except PlaybookError as exc:
            emit(False, error=str(exc), as_agent=as_agent)
            if not as_agent:
                print(str(exc), file=sys.stderr)
                print("spa run --list for the catalog", file=sys.stderr)
            return 1
        extra_args = list(extra)
        if args.verbose:
            extra_args = ["-v", *extra_args]
        rc = run_playbook(playbook, paths, extra_args)
        if as_agent:
            emit(rc == 0, error=None if rc == 0 else "playbook failed", as_agent=True)
        return rc

    if args.command == "shell":
        from spa import shell as shell_mod

        shell_argv = list(args.shell_args)
        if extra:
            shell_argv = [a for a in shell_argv if a != "--"] + extra
        try:
            shell_mod.main(shell_argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if as_agent:
                emit(code == 0, as_agent=True)
            return code or 0
        return 0

    if args.command == "aws":
        from spa import aws as aws_mod

        saved = sys.argv
        sys.argv = ["spa-aws", *args.aws_args, *extra]
        try:
            rc = aws_mod.main()
        finally:
            sys.argv = saved
        return rc

    if args.command == "licenses":
        from spa import licenses as licenses_mod

        saved = sys.argv
        sys.argv = ["spa-licenses", *args.license_args, *extra]
        try:
            rc = licenses_mod.main()
        finally:
            sys.argv = saved
        return rc

    parser.print_help()
    return 1
