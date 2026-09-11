"""Validate splunk_config.yml (`spa validate`)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from spa.executil import apply_paths_env, tool_path
from spa.paths import resolve_spa_paths


def run(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate splunk_config.yml")
    parser.add_argument("--check-licenses", action="store_true")
    parser.add_argument("--splunk-config-aws", action="store_true")
    parser.add_argument("config", nargs="?", help="Path to splunk_config.yml")
    args = parser.parse_args(argv)

    if args.config:
        cfg = Path(args.config).expanduser()
        if not cfg.is_absolute():
            cwd = Path.cwd() / cfg
            cfg = cwd if cwd.is_file() else (resolve_spa_paths().spa_home / cfg)
        os.environ["SPLUNK_CONFIG_FILE"] = str(cfg.resolve())

    paths = resolve_spa_paths()
    apply_paths_env(paths)
    config_path = Path(paths.config_file)
    if not config_path.is_file():
        print("Config file not found: %s" % config_path, file=sys.stderr)
        return 1

    print("=== Validating %s ===" % config_path)
    plugin = str(paths.spa_home / "ansible" / "plugins" / "inventory")
    lib = str(paths.spa_home / "lib")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([lib, plugin, env.get("PYTHONPATH", "")])

    print("[1/4] Schema validation (Pydantic)...")
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
    rc = subprocess.run(
        [tool_path(paths, "python3"), "-c", schema_py, str(config_path)],
        cwd=str(paths.spa_home),
        env=env,
    )
    if rc.returncode != 0:
        return rc.returncode

    print("[2/4] Inventory plugin (ansible-inventory)...")
    rc = subprocess.run(
        [tool_path(paths, "ansible-inventory"), "--list"],
        cwd=str(paths.spa_home),
        env=env,
        stdout=subprocess.DEVNULL,
    )
    if rc.returncode != 0:
        return rc.returncode
    print("Inventory OK")

    print("[3/4] License and license_manager role check...")
    from spa import licenses as licenses_mod

    data = licenses_mod.scan_licenses(paths.spa_env_dir, config_path=config_path)
    configured = data.get("configured_splunk_license_file")
    has_lm = data.get("license_manager_in_config")
    if configured and not has_lm:
        print(
            "splunk_license_file is set but no license_manager role on any host",
            file=sys.stderr,
        )
        return 1
    if has_lm and not configured:
        print("license_manager role is set but splunk_license_file is missing", file=sys.stderr)
        return 1
    if data.get("itsi_in_config") and not has_lm:
        print("ITSI in config but no license_manager role on any host", file=sys.stderr)
        return 1
    print("License role pairing OK")

    print("[4/4] Playbook syntax-check...")
    for pb in ("ansible/provision_terraform_aws.yml", "ansible/deploy_site.yml"):
        rc = subprocess.run(
            [tool_path(paths, "ansible-playbook"), pb, "--syntax-check"],
            cwd=str(paths.spa_home),
            env=env,
        )
        if rc.returncode != 0:
            return rc.returncode
    print("Playbook syntax OK")

    if args.check_licenses:
        print("[optional] Software license content and entitlement check...")
        print(json.dumps(data, indent=2, default=str))
        validation = data.get("license_validation") or {}
        for warning in validation.get("warnings") or []:
            print("License warning: %s" % warning, file=sys.stderr)
        errors = validation.get("errors") or []
        if errors:
            for error in errors:
                print("License error: %s" % error, file=sys.stderr)
            return 1
        print("License check OK")

    if args.splunk_config_aws:
        print("[optional] AWS terraform.aws validation...")
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is None:
            print("PyYAML required for AWS validate", file=sys.stderr)
            return 1
        with config_path.open() as handle:
            cfg = yaml.safe_load(handle) or {}
        aws = (cfg.get("terraform") or {}).get("aws") or {}
        region = aws.get("region")
        if not region:
            print("Skipping AWS validate: no terraform.aws.region in config", file=sys.stderr)
        else:
            from spa import aws as aws_mod

            argv_aws = ["--region", region, "--validate", "--json"]
            if aws.get("ami_id"):
                argv_aws.extend(["--ami-id", aws["ami_id"]])
            if aws.get("key_name"):
                argv_aws.extend(["--key-name", aws["key_name"]])
            if aws.get("instance_type"):
                argv_aws.extend(["--instance-type", aws["instance_type"]])
            sgs = aws.get("security_group_names") or []
            if sgs:
                argv_aws.extend(["--security-groups", ",".join(sgs)])
            rc = aws_mod.main(argv_aws)
            if rc != 0:
                return rc
        print("AWS validation OK")

    print("=== Validation complete ===")
    return 0
