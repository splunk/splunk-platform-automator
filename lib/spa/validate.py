"""Validate splunk_config.yml (`spa validate`)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from spa.api import CommandResult
from spa.executil import ToolNotFound, apply_paths_env, tool_path
from spa.paths import SpaPaths, resolve_spa_paths


ProgressCallback = Callable[[Dict[str, Any]], None]


VALIDATE_STEPS = (
    ("schema", "Schema validation (Pydantic)"),
    ("controller_data", "Controller directories (Software / baseconfig / apps / playbooks)"),
    ("inventory", "Inventory plugin (ansible-inventory)"),
    ("license_role", "License and license_manager role check"),
    ("syntax", "Playbook syntax-check"),
)

SCHEMA_STAMP_ERROR = (
    "splunk_config.yml has no schema_version. "
    "An omitted key still reads as version 1. "
    "Stamp it with spa config migrate --yes."
)


def require_authored_schema_version(config_path: Path) -> Optional[CommandResult]:
    """Fail when splunk_config.yml has no authored schema_version. Does not write."""
    from spa.preflight import load_config_mapping

    if not config_path.is_file():
        return None
    mapping = load_config_mapping(config_path)
    if mapping.get("schema_version") is None:
        return CommandResult(ok=False, error=SCHEMA_STAMP_ERROR, code=1)
    return None


def _note(
    on_progress: Optional[ProgressCallback],
    message: str,
    stream: str = "stdout",
    *,
    agent: bool = False,
    phase: Optional[str] = None,
    index: Optional[int] = None,
) -> None:
    if on_progress:
        on_progress({"type": "line", "stream": stream, "line": message})
    if agent and phase:
        sys.stderr.write(
            json.dumps(
                {
                    "type": "progress",
                    "phase": phase,
                    "phase_title": message,
                    "phase_index": index,
                    "phase_count": 5,
                    "status": "running",
                }
            )
            + "\n"
        )
        sys.stderr.flush()


def controller_data_message(state: Any, playbook_dirs: Optional[List[Dict[str, Any]]] = None) -> str:
    """One `OK` line per controller directory, like the other validate steps."""
    lines = [
        "Software OK: %s" % state.software_dir,
        "Baseconfig OK: %s" % state.baseconfig_dir,
    ]
    if state.apps_checked:
        lines.append("Local apps OK: %s" % state.apps_dir)
    else:
        lines.append("Local apps OK: none configured")
    if not playbook_dirs:
        lines.append("Custom playbooks OK: none configured")
    else:
        for row in playbook_dirs:
            count = row.get("playbooks", 0)
            detail = "empty" if not count else "%d playbook%s" % (count, "" if count == 1 else "s")
            lines.append("Custom playbooks OK: %s (%s)" % (row["path"], detail))
    return "\n".join(lines)


def license_summary(scan: Dict[str, Any]) -> Dict[str, Any]:
    """What the license_role step asserts. Full per-file scan: `spa licenses list`."""
    return {
        "configured_splunk_license_file": scan.get("configured_splunk_license_file"),
        "license_manager_in_config": scan.get("license_manager_in_config"),
        "itsi_in_config": scan.get("itsi_in_config"),
        "es_in_config": scan.get("es_in_config"),
        "files_found": len(scan.get("discovered_files") or []),
        "proposed_splunk_license_file": list(scan.get("proposed_splunk_license_file") or []),
        "unsatisfied_requirements": list(scan.get("unsatisfied_requirements") or []),
    }


def evaluate_license_role(scan: Dict[str, Any]) -> Dict[str, Any]:
    """License-role step: files without LM still fail; missing files and unlicensed ITSI warn."""
    from spa.next_steps import ITSI_LICENSE_FILE_WARNING, LICENSE_MANAGER_FILE_WARNING

    configured = scan.get("configured_splunk_license_file")
    has_lm = scan.get("license_manager_in_config")
    warnings: List[Dict[str, str]] = []
    if configured and not has_lm:
        return {
            "ok": False,
            "message": "splunk_license_file is set but no license_manager role on any host",
            "warnings": warnings,
        }
    if scan.get("itsi_in_config") and not has_lm:
        return {
            "ok": False,
            "message": "ITSI in config but no license_manager role on any host",
            "warnings": warnings,
        }
    entitlement = premium_entitlement_error(scan)
    if entitlement:
        return {"ok": False, "message": entitlement, "warnings": warnings}
    if has_lm and not configured:
        warnings.append(dict(LICENSE_MANAGER_FILE_WARNING))
    if scan.get("itsi_in_config") and (
        not configured or "itsi" in [str(item) for item in (scan.get("unsatisfied_requirements") or [])]
    ):
        warnings.append(dict(ITSI_LICENSE_FILE_WARNING))
    return {"ok": True, "message": "License role pairing OK", "warnings": warnings}


def premium_entitlement_error(scan: Dict[str, Any]) -> Optional[str]:
    """ES in config without a matching capability is a default validate failure.

    Unlicensed ITSI is IT Essentials Work and is a warning, not a failure.
    """
    if not scan.get("es_in_config"):
        return None
    errors = [
        str(item)
        for item in ((scan.get("license_validation") or {}).get("errors") or [])
        if "itsi" not in str(item).lower()
    ]
    if errors:
        return "; ".join(errors)
    unsatisfied = [
        str(item)
        for item in (scan.get("unsatisfied_requirements") or [])
        if str(item) == "es"
    ]
    if unsatisfied:
        return "Configured license files do not provide required capability: %s" % ", ".join(
            unsatisfied
        )
    return None


def custom_playbook_dirs_error(playbook_dirs: List[Dict[str, Any]], env_dir: Any) -> str:
    """Name every unusable `playbook_dirs` entry and where to fix it."""
    lines = [
        "Custom playbooks failed: %s %s (%s)" % (row["dir"], row["reason"], row["path"])
        for row in playbook_dirs
        if not row["ok"]
    ]
    lines.append("Fix playbook_dirs in %s/.spa.yml or create the directory." % env_dir)
    return "\n".join(lines)


def aws_validate_argv(aws: Dict[str, Any]) -> List[str]:
    """Named `spa provider aws validate` argv from terraform.aws. Not parent flags."""
    argv = ["validate", "--region", aws["region"]]
    if aws.get("ami_id"):
        argv.extend(["--ami-id", aws["ami_id"]])
    if aws.get("key_name"):
        argv.extend(["--key-name", aws["key_name"]])
    if aws.get("instance_type"):
        argv.extend(["--instance-type", aws["instance_type"]])
    sgs = aws.get("security_group_names") or []
    if sgs:
        argv.extend(["--security-groups", ",".join(sgs)])
    return argv


def validate_terraform_aws(aws: Dict[str, Any]) -> CommandResult:
    """Named-SG existence for spa validate --splunk-config aws. No port-rule warnings."""
    from spa import aws as aws_mod

    return aws_mod.execute_argv(aws_validate_argv(aws), check_exposure=False)


def resolve_config_path(config: str, paths: Optional[SpaPaths] = None) -> Path:
    """Resolve a --config argument like validate_env will consume it."""
    cfg = Path(config).expanduser()
    if not cfg.is_absolute():
        cwd = Path.cwd() / cfg
        cfg = cwd if cwd.is_file() else ((paths or resolve_spa_paths()).spa_home / cfg)
    return cfg.resolve()


def validate_env(
    paths: Optional[SpaPaths] = None,
    *,
    config: Optional[str] = None,
    check_licenses: bool = False,
    splunk_config: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
    agent: bool = False,
) -> CommandResult:
    """Run validation steps and return structured results (no printing)."""
    if splunk_config is not None and splunk_config != "aws":
        return CommandResult(ok=False, error="spa validate --splunk-config aws", code=2)
    if config:
        config_path = resolve_config_path(config, paths)
        overlay = os.environ.copy()
        overlay["SPLUNK_CONFIG_FILE"] = str(config_path)
        if paths is not None:
            overlay["SPA_ENV_DIR"] = str(paths.spa_env_dir)
        paths = resolve_spa_paths(environ=overlay)
    else:
        paths = paths or resolve_spa_paths()
        config_path = Path(paths.config_file)

    apply_paths_env(paths)
    env = os.environ.copy()
    env.update(paths.export_env())
    env["SPLUNK_CONFIG_FILE"] = str(config_path)
    steps: List[Dict[str, Any]] = []
    data: Dict[str, Any] = {"config_file": str(config_path), "steps": steps}

    if not config_path.is_file():
        return CommandResult(
            ok=False,
            error="Config file not found: %s" % config_path,
            data=data,
            code=1,
        )

    from spa.preflight import env_lookup_readiness, load_config_mapping, unresolved_env_message

    try:
        loaded = load_config_mapping(config_path)
    except Exception:
        loaded = None
    if loaded is not None:
        env_error = unresolved_env_message(loaded)
        if env_error:
            data["env_lookups"] = env_lookup_readiness(loaded)
            steps.append({"id": "env_lookups", "ok": False, "message": env_error})
            return CommandResult(ok=False, error=env_error, data=data, code=1)

    if loaded is not None and isinstance(loaded.get("ccm"), dict):
        from spa.providers.ccm import validate_ccm

        ccm_result = validate_ccm(paths, loaded.get("ccm") or {})
        if not ccm_result.ok:
            steps.append({"id": "ccm", "ok": False, "message": ccm_result.error})
            return CommandResult(
                ok=False,
                error=ccm_result.error,
                data=data,
                code=ccm_result.code or 1,
            )
        steps.append({"id": "ccm", "ok": True, "message": "CCM validation OK"})

    plugin = str(paths.spa_home / "ansible" / "plugins" / "inventory")
    lib = str(paths.spa_home / "lib")
    env["PYTHONPATH"] = os.pathsep.join([lib, plugin, env.get("PYTHONPATH", "")])

    schema_py = r"""
import sys
from schema import validate_config_file, ConfigValidationError
path = sys.argv[1]
try:
    validate_config_file(path)
    print("Schema OK: %s" % path)
except ConfigValidationError as e:
    print(e, file=sys.stderr)
    sys.exit(1)
"""
    _note(
        on_progress,
        "[1/5] Schema validation (Pydantic)...",
        agent=agent,
        phase="schema",
        index=1,
    )
    rc = subprocess.run(
        [tool_path(paths, "python3"), "-c", schema_py, str(config_path)],
        cwd=str(paths.spa_home),
        env=env,
        capture_output=True,
        text=True,
    )
    schema_msg = (rc.stdout or rc.stderr or "").strip() or (
        "Schema OK: %s" % config_path if rc.returncode == 0 else "Schema validation failed"
    )
    steps.append({"id": "schema", "ok": rc.returncode == 0, "message": schema_msg})
    if rc.returncode != 0:
        err = (rc.stderr or rc.stdout or "Schema validation failed").strip()
        return CommandResult(ok=False, error=err, data=data, code=rc.returncode)
    stamp = require_authored_schema_version(config_path)
    if stamp is not None:
        if agent:
            return stamp
        return CommandResult(ok=False, error=SCHEMA_STAMP_ERROR, data=data, code=1)

    _note(
        on_progress,
        "[2/5] Controller directories (Software / baseconfig / apps / playbooks)...",
        agent=agent,
        phase="controller_data",
        index=2,
    )
    from spa.playbooks import custom_playbook_dir_state
    from spa.preflight import check_controller_data, controller_data_error

    controller = check_controller_data(paths)
    playbook_dirs = custom_playbook_dir_state(Path(paths.spa_env_dir))
    # Only on failure: the step message already names every directory on success.
    detail = {
        "software_dir": controller.software_dir,
        "baseconfig_dir": controller.baseconfig_dir,
        "apps_dir": controller.apps_dir,
        "apps_checked": controller.apps_checked,
        "missing": list(controller.missing),
        "playbook_dirs": playbook_dirs,
    }
    if not controller.ok:
        msg = controller_data_error(controller)
        data["controller_data"] = detail
        steps.append({"id": "controller_data", "ok": False, "message": msg})
        return CommandResult(ok=False, error=msg, data=data, code=1)
    if any(not row["ok"] for row in playbook_dirs):
        msg = custom_playbook_dirs_error(playbook_dirs, paths.spa_env_dir)
        data["controller_data"] = detail
        steps.append({"id": "controller_data", "ok": False, "message": msg})
        return CommandResult(ok=False, error=msg, data=data, code=1)
    steps.append(
        {
            "id": "controller_data",
            "ok": True,
            "message": controller_data_message(controller, playbook_dirs),
        }
    )

    _note(
        on_progress,
        "[3/5] Inventory plugin (ansible-inventory)...",
        agent=agent,
        phase="inventory",
        index=3,
    )
    try:
        inventory_bin = tool_path(paths, "ansible-inventory")
    except ToolNotFound as exc:
        steps.append({"id": "inventory", "ok": False, "message": str(exc)})
        return CommandResult(ok=False, error=str(exc), data=data, code=1)
    rc = subprocess.run(
        [inventory_bin, "--list"],
        cwd=str(paths.spa_home),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    inv_ok = rc.returncode == 0
    steps.append(
        {
            "id": "inventory",
            "ok": inv_ok,
            "message": "Inventory OK" if inv_ok else (rc.stderr or "Inventory failed").strip(),
        }
    )
    if not inv_ok:
        return CommandResult(
            ok=False,
            error=(rc.stderr or "Inventory failed").strip(),
            data=data,
            code=rc.returncode,
        )

    _note(
        on_progress,
        "[4/5] License and license_manager role check...",
        agent=agent,
        phase="license_role",
        index=4,
    )
    from spa import licenses as licenses_mod

    license_scan = licenses_mod.scan_licenses(paths.spa_env_dir, config_path=config_path)
    data["licenses"] = license_summary(license_scan)
    if check_licenses:
        data["license_scan"] = license_scan
    role = evaluate_license_role(license_scan)
    if role["warnings"]:
        data.setdefault("warnings", []).extend(role["warnings"])
        from spa.next_steps import attach_license_file_next

        attach_license_file_next(data)
    if not role["ok"]:
        steps.append({"id": "license_role", "ok": False, "message": role["message"]})
        return CommandResult(ok=False, error=role["message"], data=data, code=1)
    steps.append({"id": "license_role", "ok": True, "message": role["message"]})

    _note(
        on_progress,
        "[5/5] Playbook syntax-check...",
        agent=agent,
        phase="syntax",
        index=5,
    )
    for pb in ("ansible/aws_provision.yml", "ansible/deploy_site.yml"):
        rc = subprocess.run(
            [tool_path(paths, "ansible-playbook"), pb, "--syntax-check"],
            cwd=str(paths.spa_home),
            env=env,
            capture_output=True,
            text=True,
        )
        if rc.returncode != 0:
            err = (rc.stderr or rc.stdout or "Playbook syntax-check failed").strip()
            steps.append({"id": "syntax", "ok": False, "message": err, "playbook": pb})
            return CommandResult(ok=False, error=err, data=data, code=rc.returncode)
    steps.append({"id": "syntax", "ok": True, "message": "Playbook syntax OK"})

    if check_licenses:
        validation = license_scan.get("license_validation") or {}
        data["license_validation"] = validation
        errors = validation.get("errors") or []
        if errors:
            msg = "; ".join(str(item) for item in errors)
            steps.append({"id": "license_files", "ok": False, "message": msg})
            return CommandResult(ok=False, error=msg, data=data, code=1)
        steps.append({"id": "license_files", "ok": True, "message": "License check OK"})

    if splunk_config == "aws":
        try:
            import yaml
        except ImportError:
            msg = "PyYAML required for AWS validate"
            steps.append({"id": "aws", "ok": False, "message": msg})
            return CommandResult(ok=False, error=msg, data=data, code=1)
        with config_path.open() as handle:
            cfg = yaml.safe_load(handle) or {}
        aws = (cfg.get("terraform") or {}).get("aws") or {}
        region = aws.get("region")
        if not region:
            steps.append(
                {
                    "id": "aws",
                    "ok": True,
                    "message": "Skipping AWS validate: no terraform.aws.region in config",
                    "skipped": True,
                }
            )
        else:
            aws_result = validate_terraform_aws(aws)
            data["aws"] = aws_result.data
            if not aws_result.ok:
                steps.append(
                    {"id": "aws", "ok": False, "message": aws_result.error or "AWS validation failed"}
                )
                return CommandResult(
                    ok=False,
                    error=aws_result.error or "AWS validation failed",
                    data=data,
                    code=aws_result.code,
                )
            steps.append({"id": "aws", "ok": True, "message": "AWS validation OK"})

    return CommandResult(ok=True, data=data)


def format_validate_text(result: CommandResult) -> str:
    data = result.data or {}
    lines = ["=== Validating %s ===" % data.get("config_file", "")]
    labels = {
        "schema": "[1/5] Schema validation (Pydantic)...",
        "controller_data": "[2/5] Controller directories (Software / baseconfig / apps / playbooks)...",
        "inventory": "[3/5] Inventory plugin (ansible-inventory)...",
        "license_role": "[4/5] License and license_manager role check...",
        "syntax": "[5/5] Playbook syntax-check...",
        "license_files": "[optional] Software license content and entitlement check...",
        "aws": "[optional] AWS terraform.aws validation...",
        "ccm": "[optional] CCM provider checks...",
    }
    for step in data.get("steps") or []:
        ident = step.get("id")
        if ident in labels:
            lines.append(labels[ident])
        if ident == "license_files" and data.get("license_scan"):
            lines.append(json.dumps(data["license_scan"], indent=2, default=str))
        message = step.get("message") or ""
        if message:
            lines.append(message)
    for warning in data.get("warnings") or []:
        if isinstance(warning, dict):
            lines.append("Warning: %s" % (warning.get("message") or warning.get("id")))
        else:
            lines.append("Warning: %s" % warning)
    if result.ok:
        lines.append("=== Validation complete ===")
    return "\n".join(lines) + "\n"


def run(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate splunk_config.yml")
    parser.add_argument("--check-licenses", action="store_true")
    parser.add_argument(
        "--splunk-config",
        metavar="PROVIDER",
        choices=["aws"],
        help="Check this provider's selections from the environment config. aws today.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="Validate this file instead of the environment config",
    )
    args = parser.parse_args(argv)
    result = validate_env(
        config=args.config,
        check_licenses=args.check_licenses,
        splunk_config=args.splunk_config,
    )
    text = format_validate_text(result)
    sys.stdout.write(text)
    if result.error and result.error not in text:
        print(result.error, file=sys.stderr)
    return result.code
