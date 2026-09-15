"""Validate splunk_config.yml (`spa validate`)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from spa.api import CommandResult
from spa.executil import apply_paths_env, tool_path
from spa.paths import SpaPaths, resolve_spa_paths


ProgressCallback = Callable[[Dict[str, Any]], None]


def _note(on_progress: Optional[ProgressCallback], message: str, stream: str = "stdout") -> None:
    if on_progress:
        on_progress({"type": "line", "stream": stream, "line": message})


def validate_env(
    paths: Optional[SpaPaths] = None,
    *,
    config: Optional[str] = None,
    check_licenses: bool = False,
    splunk_config_aws: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    """Run validation steps and return structured results (no printing)."""
    if config:
        cfg = Path(config).expanduser()
        if not cfg.is_absolute():
            cwd = Path.cwd() / cfg
            cfg = cwd if cwd.is_file() else (resolve_spa_paths().spa_home / cfg)
        config_path = cfg.resolve()
        overlay = os.environ.copy()
        overlay["SPLUNK_CONFIG_FILE"] = str(config_path)
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
    _note(on_progress, "[1/5] Schema validation (Pydantic)...")
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

    _note(on_progress, "[2/5] Controller Software / baseconfig / local apps...")
    from spa.preflight import check_controller_data, controller_data_error

    controller = check_controller_data(paths)
    data["controller_data"] = {
        "software_dir": controller.software_dir,
        "baseconfig_dir": controller.baseconfig_dir,
        "apps_dir": controller.apps_dir,
        "missing": list(controller.missing),
    }
    if not controller.ok:
        msg = controller_data_error(controller)
        steps.append({"id": "controller_data", "ok": False, "message": msg})
        return CommandResult(ok=False, error=msg, data=data, code=1)
    steps.append(
        {
            "id": "controller_data",
            "ok": True,
            "message": "Software %s; baseconfig %s"
            % (controller.software_dir, controller.baseconfig_dir),
        }
    )

    _note(on_progress, "[3/5] Inventory plugin (ansible-inventory)...")
    rc = subprocess.run(
        [tool_path(paths, "ansible-inventory"), "--list"],
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

    _note(on_progress, "[4/5] License and license_manager role check...")
    from spa import licenses as licenses_mod

    license_scan = licenses_mod.scan_licenses(paths.spa_env_dir, config_path=config_path)
    data["license_scan"] = license_scan
    configured = license_scan.get("configured_splunk_license_file")
    has_lm = license_scan.get("license_manager_in_config")
    if configured and not has_lm:
        msg = "splunk_license_file is set but no license_manager role on any host"
        steps.append({"id": "license_role", "ok": False, "message": msg})
        return CommandResult(ok=False, error=msg, data=data, code=1)
    if has_lm and not configured:
        msg = "license_manager role is set but splunk_license_file is missing"
        steps.append({"id": "license_role", "ok": False, "message": msg})
        return CommandResult(ok=False, error=msg, data=data, code=1)
    if license_scan.get("itsi_in_config") and not has_lm:
        msg = "ITSI in config but no license_manager role on any host"
        steps.append({"id": "license_role", "ok": False, "message": msg})
        return CommandResult(ok=False, error=msg, data=data, code=1)
    steps.append({"id": "license_role", "ok": True, "message": "License role pairing OK"})

    _note(on_progress, "[5/5] Playbook syntax-check...")
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

    if splunk_config_aws:
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
            from spa import aws as aws_mod

            argv_aws = ["--region", region, "--validate"]
            if aws.get("ami_id"):
                argv_aws.extend(["--ami-id", aws["ami_id"]])
            if aws.get("key_name"):
                argv_aws.extend(["--key-name", aws["key_name"]])
            if aws.get("instance_type"):
                argv_aws.extend(["--instance-type", aws["instance_type"]])
            sgs = aws.get("security_group_names") or []
            if sgs:
                argv_aws.extend(["--security-groups", ",".join(sgs)])
            aws_result = aws_mod.execute_argv(argv_aws)
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
        "controller_data": "[2/5] Controller Software / baseconfig / local apps...",
        "inventory": "[3/5] Inventory plugin (ansible-inventory)...",
        "license_role": "[4/5] License and license_manager role check...",
        "syntax": "[5/5] Playbook syntax-check...",
        "license_files": "[optional] Software license content and entitlement check...",
        "aws": "[optional] AWS terraform.aws validation...",
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
    if result.ok:
        lines.append("=== Validation complete ===")
    return "\n".join(lines) + "\n"


def run(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate splunk_config.yml")
    parser.add_argument("--check-licenses", action="store_true")
    parser.add_argument("--splunk-config-aws", action="store_true")
    parser.add_argument("config", nargs="?", help="Path to splunk_config.yml")
    args = parser.parse_args(argv)
    result = validate_env(
        config=args.config,
        check_licenses=args.check_licenses,
        splunk_config_aws=args.splunk_config_aws,
    )
    sys.stdout.write(format_validate_text(result))
    if result.error:
        print(result.error, file=sys.stderr)
    return result.code
