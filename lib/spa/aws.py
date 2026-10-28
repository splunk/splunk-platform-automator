#!/usr/bin/env python3
"""
AWS discovery and validation for splunk_config.yml terraform.aws settings.

Requires boto3 and AWS credentials (env, profile, or instance role).

Examples:
  spa aws --check-auth --json
  spa aws regions list --json
  spa aws --region eu-central-1 --latest-ami --os amazon_linux --json
  spa aws --region eu-central-1 --latest-ami --os all --json
  spa aws amis list --region eu-central-1 --name-filter "custom*" --json
  spa aws --region eu-central-1 --validate \\
    --ami-id ami-xxx --key-name aws_key --security-groups Splunk_Basic \\
    --instance-type t3.medium --json
  spa aws --survey --region eu-central-1 --json
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
except ImportError:
    boto3 = None  # type: ignore


ENV_INSTANCE_TYPES = ("t3.small", "t3.medium", "t3.large", "t3.xlarge")
DEFAULT_AMI_OWNERS = ("amazon", "aws-marketplace", "self")
RHEL_OFFICIAL_OWNER = "309956199498"  # AWS alias: amazon (official RHEL AMIs)

RHEL_OFFICIAL_OWNER = "309956199498"  # AWS alias: amazon (official RHEL AMIs)
DEBIAN_OFFICIAL_OWNER = "136693071363"  # Debian Cloud Team

# Preference order for SPA envs (RHEL best tested; Debian least tested with SPA).
RECOMMENDED_OS_ORDER = ("rhel", "ubuntu", "amazon_linux", "debian")

# Version-agnostic OS keys — latest AMI resolved at runtime (SSM or EC2 describe).
RECOMMENDED_OS: Dict[str, Dict[str, Any]] = {
    "rhel": {
        "label": "RHEL",
        "resolver": "rhel",
        "default_ssh_username": "ec2-user",
    },
    "ubuntu": {
        "label": "Ubuntu LTS",
        "resolver": "ubuntu",
        "default_ssh_username": "ubuntu",
    },
    "amazon_linux": {
        "label": "Amazon Linux",
        "resolver": "amazon_linux",
        "default_ssh_username": "ec2-user",
    },
    "debian": {
        "label": "Debian",
        "resolver": "debian",
        "default_ssh_username": "admin",
        "framework_note": "Less tested with Splunk Platform Automator; prefer RHEL or Ubuntu.",
    },
}

# Backward-compatible aliases for older scripts and docs.
OS_ALIASES: Dict[str, str] = {
    "al2023": "amazon_linux",
    "ubuntu2404": "ubuntu",
    "rhel10": "rhel",
}

AMAZON_LINUX_SSM_PREFIX = "/aws/service/ami-amazon-linux-latest/"
UBUNTU_SSM_PREFIX = "/aws/service/canonical/ubuntu/server/"
_SSM_PARAMETER_CACHE: Dict[tuple[str, str], List[str]] = {}


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _aws_item_line(item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    if item.get("name") and "endpoint" in item:
        return "%s  selected" % item["name"] if item.get("selected") else str(item["name"])
    if item.get("ami_id"):
        parts = [
            item.get("ami_id"),
            item.get("name"),
            item.get("architecture"),
            item.get("suggested_ssh_username"),
        ]
        return "  ".join(str(part) for part in parts if part)
    if item.get("group_name"):
        return "  ".join(
            str(part) for part in (item.get("group_id"), item.get("group_name")) if part
        )
    if item.get("name"):
        return str(item["name"])
    return "  ".join(
        "%s=%s" % (key, value) for key, value in item.items() if value is not None and key != "ok"
    )


def format_aws_text(data: Any) -> str:
    """Human stdout. JSON mode prints the payload and does not call this."""
    if not isinstance(data, dict):
        return str(data) + "\n"
    lines: List[str] = []
    if data.get("account"):
        lines.append("Account: %s" % data["account"])
    if data.get("arn"):
        lines.append("ARN: %s" % data["arn"])
    if data.get("ami_id") and "items" not in data:
        lines.append(_aws_item_line(data))
    items = data.get("items")
    if isinstance(items, list):
        if not items and data.get("ok") is not False:
            lines.append("No results.")
        for item in items:
            lines.append(_aws_item_line(item))
    item = data.get("item")
    if isinstance(item, dict):
        lines.append(_aws_item_line(item))
    for label, key in (
        ("Key pairs", "key_pairs"),
        ("Security groups", "security_groups"),
        ("Instance types", "instance_types_t3"),
    ):
        nested = data.get(key)
        if not isinstance(nested, dict):
            continue
        lines.append("%s:" % label)
        nested_items = nested.get("items") or []
        if not nested_items:
            lines.append("  No results.")
        for entry in nested_items:
            lines.append("  %s" % _aws_item_line(entry))
    recommended = data.get("recommended_amis")
    if isinstance(recommended, dict):
        lines.append("AMIs:")
        for os_key, entry in recommended.items():
            chosen = (entry or {}).get("item") or {}
            ami = chosen.get("ami_id") or (entry or {}).get("error") or "not found"
            lines.append("  %s  %s" % (os_key, ami))
    checks = data.get("checks")
    if isinstance(checks, dict):
        for name, entry in checks.items():
            if isinstance(entry, dict):
                state = "ok" if entry.get("ok") else "failed"
                detail = entry.get("error") or entry.get("ami_id") or entry.get("key_name") or entry.get("instance_type") or ""
                lines.append("%s: %s%s" % (name, state, ("  %s" % detail) if detail else ""))
            else:
                lines.append("%s: %s" % (name, entry))
    for warning in data.get("warnings") or []:
        lines.append("Warning: %s" % warning)
    if not lines:
        lines.append("ok" if data.get("ok", True) else "failed")
    return "\n".join(lines) + "\n"


def _output(data: Any, as_json: bool) -> None:
    from spa.runlog import redact

    if as_json:
        print(json.dumps(redact(data), indent=2, default=str))
        return
    if isinstance(data, dict):
        notice = region_notice(
            _ResolvedRegion(data.get("region"), data.get("region_source"), data.get("profile"))
        )
        if notice:
            _err(notice)
        if data.get("ok") is False and data.get("error"):
            _err(str(redact(data["error"])))
    sys.stdout.write(format_aws_text(data))


def _require_boto3() -> None:
    if boto3 is None:
        message = "boto3 is required. Install with: pip install boto3"
        if AwsArgumentParser.json_errors:
            from spa.runlog import redact

            print(json.dumps({"ok": False, "error": redact(message)}, separators=(",", ":")))
        else:
            _err(message)
        sys.exit(2)


class _ResolvedRegion:
    def __init__(self, region: Optional[str], source: Optional[str], profile: Optional[str] = None):
        self.region = region
        self.source = source
        self.profile = profile


def _aws_config_path() -> str:
    configured = os.environ.get("AWS_CONFIG_FILE", "").strip()
    return configured or os.path.expanduser("~/.aws/config")


def _aws_profile_name() -> str:
    return (
        os.environ.get("AWS_PROFILE", "").strip()
        or os.environ.get("AWS_DEFAULT_PROFILE", "").strip()
        or "default"
    )


def _profile_sections(profile: str) -> tuple:
    if profile == "default":
        return ("default", "profile default")
    return ("profile %s" % profile,)


def _region_from_aws_config() -> _ResolvedRegion:
    """Read region from the AWS config file. This does not import boto3."""
    profile = _aws_profile_name()
    path = _aws_config_path()
    if not os.path.isfile(path):
        return _ResolvedRegion(None, None)
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeError):
        return _ResolvedRegion(None, None)
    for section in _profile_sections(profile):
        if not parser.has_section(section) or not parser.has_option(section, "region"):
            continue
        region = parser.get(section, "region", fallback="").strip()
        if region:
            return _ResolvedRegion(region, "aws-config", profile)
    return _ResolvedRegion(None, None)


def environment_config_region(config_file: Any) -> Optional[str]:
    """terraform.aws.region from an environment's splunk_config.yml, or None. Never raises."""
    try:
        from spa.preflight import load_config_mapping
        from pathlib import Path

        path = os.fspath(config_file)
        if not os.path.isfile(path):
            return None
        data = load_config_mapping(Path(path))
    except Exception:
        return None
    block = (data.get("terraform") or {}).get("aws") if isinstance(data, dict) else None
    value = block.get("region") if isinstance(block, dict) else None
    text = str(value).strip() if value else ""
    return text or None


def resolve_region(explicit: Optional[str] = None, environment_region: Optional[str] = None) -> _ResolvedRegion:
    """Prefer --region, then the environment's terraform.aws.region, then AWS_REGION, AWS_DEFAULT_REGION, the AWS config."""
    if explicit:
        return _ResolvedRegion(explicit, "--region")
    if environment_region:
        return _ResolvedRegion(environment_region, "terraform.aws.region")
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        value = os.environ.get(name, "").strip()
        if value:
            return _ResolvedRegion(value, name)
    return _region_from_aws_config()


def region_notice(resolved: _ResolvedRegion) -> str:
    if not resolved.region:
        return ""
    if resolved.source == "--region":
        return "Using region %s from --region." % resolved.region
    if resolved.source == "terraform.aws.region":
        return "Using region %s from terraform.aws.region in the environment config." % resolved.region
    if resolved.source in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        return "Using region %s from %s." % (resolved.region, resolved.source)
    profile = resolved.profile or "default"
    return "Using region %s from ~/.aws/config (profile %s)." % (resolved.region, profile)


def _stamp_region(data: Any, resolved: _ResolvedRegion) -> None:
    if not isinstance(data, dict) or not resolved.region:
        return
    data.setdefault("region", resolved.region)
    data["region_source"] = resolved.source
    if resolved.source == "aws-config":
        data["profile"] = resolved.profile or "default"


def _finish(result: Any, resolved: _ResolvedRegion) -> Any:
    _stamp_region(getattr(result, "data", None), resolved)
    return result


def _session(region: Optional[str] = None) -> Any:
    _require_boto3()
    return boto3.Session(region_name=region)


def suggest_ssh_username(ami_name: str, description: str = "") -> str:
    text = f"{ami_name} {description}".lower()
    if "ubuntu" in text:
        return "ubuntu"
    if "debian" in text:
        return "admin"
    return "ec2-user"


def normalize_os_key(os_key: str) -> str:
    return OS_ALIASES.get(os_key, os_key)


def valid_os_keys() -> List[str]:
    return list(RECOMMENDED_OS_ORDER)


def os_preference_rank(os_key: str) -> Optional[int]:
    normalized = normalize_os_key(os_key)
    try:
        return RECOMMENDED_OS_ORDER.index(normalized) + 1
    except ValueError:
        return None


def _list_ssm_parameter_names(session: Any, region: str, path: str) -> List[str]:
    cache_key = (region, path)
    if cache_key in _SSM_PARAMETER_CACHE:
        return _SSM_PARAMETER_CACHE[cache_key]

    ssm = session.client("ssm", region_name=region)
    paginator = ssm.get_paginator("get_parameters_by_path")
    names: List[str] = []
    try:
        for page in paginator.paginate(Path=path, Recursive=True, WithDecryption=False):
            for param in page.get("Parameters", []):
                names.append(param["Name"])
    except (ClientError, BotoCoreError):
        return []

    _SSM_PARAMETER_CACHE[cache_key] = names
    return names


def discover_amazon_linux_ssm_path(parameter_names: List[str]) -> Optional[str]:
    """Pick highest al{YYYY} generation with kernel-default x86_64 SSM pointer."""
    best: Optional[tuple[int, str]] = None
    pattern = re.compile(rf"^{re.escape(AMAZON_LINUX_SSM_PREFIX)}al(\d{{4}})-ami-kernel-default-x86_64$")
    for name in parameter_names:
        match = pattern.match(name)
        if not match:
            continue
        year = int(match.group(1))
        if best is None or year > best[0]:
            best = (year, name)
    return best[1] if best else None


def discover_ubuntu_ssm_path(parameter_names: List[str]) -> Optional[str]:
    """Pick highest Ubuntu LTS (.04) release with stable/current amd64 gp3 (fallback gp2) AMI pointer."""
    candidates: List[tuple[tuple[int, ...], bool, str]] = []
    for storage in ("ebs-gp3", "ebs-gp2"):
        pattern = re.compile(
            rf"^{re.escape(UBUNTU_SSM_PREFIX)}(\d+\.04)/stable/current/amd64/hvm/{storage}/ami-id$"
        )
        for name in parameter_names:
            match = pattern.match(name)
            if not match:
                continue
            version = tuple(int(part) for part in match.group(1).split("."))
            candidates.append((version, storage == "ebs-gp3", name))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def discover_latest_rhel_major_version(session: Any, region: str) -> Optional[int]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_images(
            Owners=[RHEL_OFFICIAL_OWNER],
            Filters=[
                {"Name": "state", "Values": ["available"]},
                {"Name": "name", "Values": ["RHEL-*"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
        )
    except (ClientError, BotoCoreError):
        return None

    majors: set[int] = set()
    for image in resp.get("Images", []):
        match = re.match(r"RHEL-(\d+)", image.get("Name", ""))
        if match:
            majors.add(int(match.group(1)))
    return max(majors) if majors else None


def discover_latest_debian_major_version(session: Any, region: str) -> Optional[int]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_images(
            Owners=[DEBIAN_OFFICIAL_OWNER],
            Filters=[
                {"Name": "state", "Values": ["available"]},
                {"Name": "name", "Values": ["debian-*-amd64-*"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
        )
    except (ClientError, BotoCoreError):
        return None

    majors: set[int] = set()
    for image in resp.get("Images", []):
        match = re.match(r"debian-(\d+)-amd64-", image.get("Name", ""))
        if match:
            majors.add(int(match.group(1)))
    return max(majors) if majors else None


def get_latest_debian_ami(
    session: Any,
    region: str,
    major_version: int,
    max_results: int = 1,
) -> Dict[str, Any]:
    """Latest official Debian AMI by major version (Debian Cloud Team owner)."""
    ec2 = session.client("ec2", region_name=region)
    name_prefix = f"debian-{major_version}-amd64-"
    try:
        resp = ec2.describe_images(
            Owners=[DEBIAN_OFFICIAL_OWNER],
            Filters=[
                {"Name": "state", "Values": ["available"]},
                {"Name": "name", "Values": [f"{name_prefix}*"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
        )
        images = sorted(
            resp.get("Images", []),
            key=lambda i: i.get("CreationDate", ""),
            reverse=True,
        )[:max_results]
        items = [_ami_item_from_image(img) for img in images]
        if not items:
            return {
                "ok": False,
                "error": f"No available Debian {major_version} x86_64 AMI in {region}",
                "source": "ec2-describe-images",
                "debian_major_version": major_version,
                "owner_id": DEBIAN_OFFICIAL_OWNER,
                "items": [],
            }
        return {
            "ok": True,
            "source": "ec2-describe-images",
            "debian_major_version": major_version,
            "owner_id": DEBIAN_OFFICIAL_OWNER,
            "items": items,
        }
    except (ClientError, BotoCoreError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "source": "ec2-describe-images",
            "debian_major_version": major_version,
            "items": [],
        }


def resolve_debian_ami(session: Any, region: str, max_results: int = 1) -> Dict[str, Any]:
    major = discover_latest_debian_major_version(session, region)
    if major is None:
        return {
            "ok": False,
            "error": f"No available official Debian AMI found in {region}",
            "source": "ec2-describe-images",
            "items": [],
        }

    result = get_latest_debian_ami(session, region, major_version=major, max_results=max_results)
    result["resolved_version"] = str(major)
    result["debian_major_version"] = major
    return result


def resolve_amazon_linux_ami(session: Any, region: str, max_results: int = 1) -> Dict[str, Any]:
    names = _list_ssm_parameter_names(session, region, AMAZON_LINUX_SSM_PREFIX)
    ssm_path = discover_amazon_linux_ssm_path(names)
    if not ssm_path:
        return {
            "ok": False,
            "error": f"No Amazon Linux SSM pointer found under {AMAZON_LINUX_SSM_PREFIX}",
            "source": "ssm-discovery",
            "items": [],
        }

    result = get_ami_id_from_ssm(session, region, ssm_path)
    match = re.search(r"al(\d{4})-ami-kernel-default-x86_64$", ssm_path)
    result["resolved_version"] = match.group(1) if match else None
    result["ssm_path"] = ssm_path
    return result


def resolve_ubuntu_ami(session: Any, region: str, max_results: int = 1) -> Dict[str, Any]:
    names = _list_ssm_parameter_names(session, region, UBUNTU_SSM_PREFIX)
    ssm_path = discover_ubuntu_ssm_path(names)
    if not ssm_path:
        return {
            "ok": False,
            "error": f"No Ubuntu LTS SSM pointer found under {UBUNTU_SSM_PREFIX}",
            "source": "ssm-discovery",
            "items": [],
        }

    result = get_ami_id_from_ssm(session, region, ssm_path)
    match = re.search(r"/server/(\d+\.\d+)/stable/current/", ssm_path)
    result["resolved_version"] = match.group(1) if match else None
    result["ssm_path"] = ssm_path
    return result


def resolve_rhel_ami(session: Any, region: str, max_results: int = 1) -> Dict[str, Any]:
    major = discover_latest_rhel_major_version(session, region)
    if major is None:
        return {
            "ok": False,
            "error": f"No available official RHEL AMI found in {region}",
            "source": "ec2-describe-images",
            "items": [],
        }

    result = get_latest_rhel_ami(session, region, major_version=major, max_results=max_results)
    result["resolved_version"] = str(major)
    result["rhel_major_version"] = major
    return result


def check_auth(session: Any) -> Dict[str, Any]:
    sts = session.client("sts")
    try:
        ident = sts.get_caller_identity()
        return {
            "ok": True,
            "account": ident.get("Account"),
            "arn": ident.get("Arn"),
        }
    except (NoCredentialsError, ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc)}


def list_regions(session: Any, selected_region: Optional[str] = None) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name="us-east-1")
    try:
        resp = ec2.describe_regions(AllRegions=False)
        items = []
        for r in sorted(resp.get("Regions", []), key=lambda x: x["RegionName"]):
            item = {"name": r["RegionName"], "endpoint": r.get("Endpoint")}
            if selected_region and item["name"] == selected_region:
                item["selected"] = True
            items.append(item)
        return {"ok": True, "items": items}
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc), "items": []}


def _ami_item_from_image(img: Dict[str, Any]) -> Dict[str, Any]:
    name = img.get("Name", "")
    desc = img.get("Description", "") or ""
    return {
        "ami_id": img.get("ImageId"),
        "name": name,
        "creation_date": img.get("CreationDate"),
        "architecture": img.get("Architecture"),
        "description": desc,
        "suggested_ssh_username": suggest_ssh_username(name, desc),
        "public_ssm_parameter": img.get("PublicSsmParameterName"),
    }


def get_ami_id_from_ssm(session: Any, region: str, parameter_path: str) -> Dict[str, Any]:
    ssm = session.client("ssm", region_name=region)
    try:
        resp = ssm.get_parameter(Name=parameter_path)
        ami_id = (resp.get("Parameter") or {}).get("Value")
        if not ami_id:
            return {"ok": False, "error": "SSM parameter empty", "ssm_path": parameter_path}
        described = describe_ami(session, region, ami_id)
        if not described.get("ok"):
            return {
                "ok": False,
                "error": described.get("error", "describe_ami failed"),
                "ssm_path": parameter_path,
                "ami_id": ami_id,
            }
        return {
            "ok": True,
            "source": "ssm",
            "ssm_path": parameter_path,
            "item": {
                "ami_id": described["ami_id"],
                "name": described.get("name"),
                "creation_date": described.get("creation_date"),
                "architecture": described.get("architecture"),
                "suggested_ssh_username": described.get("suggested_ssh_username"),
                "public_ssm_parameter": parameter_path,
            },
        }
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc), "ssm_path": parameter_path}


def get_latest_rhel_ami(
    session: Any,
    region: str,
    major_version: int = 10,
    max_results: int = 1,
) -> Dict[str, Any]:
    """Latest official RHEL AMI by major version (no SSM public parameter for RHEL)."""
    ec2 = session.client("ec2", region_name=region)
    name_prefix = f"RHEL-{major_version}"
    try:
        resp = ec2.describe_images(
            Owners=[RHEL_OFFICIAL_OWNER],
            Filters=[
                {"Name": "state", "Values": ["available"]},
                {"Name": "name", "Values": [f"{name_prefix}*"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
        )
        images = sorted(
            resp.get("Images", []),
            key=lambda i: i.get("CreationDate", ""),
            reverse=True,
        )[:max_results]
        items = [_ami_item_from_image(img) for img in images]
        if not items:
            return {
                "ok": False,
                "error": f"No available RHEL {major_version} x86_64 AMI in {region}",
                "source": "ec2-describe-images",
                "rhel_major_version": major_version,
                "owner_id": RHEL_OFFICIAL_OWNER,
                "items": [],
            }
        return {
            "ok": True,
            "source": "ec2-describe-images",
            "rhel_major_version": major_version,
            "owner_id": RHEL_OFFICIAL_OWNER,
            "items": items,
        }
    except (ClientError, BotoCoreError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "source": "ec2-describe-images",
            "rhel_major_version": major_version,
            "items": [],
        }


def resolve_recommended_os_ami(
    session: Any,
    region: str,
    os_key: str,
    max_results: int = 1,
) -> Dict[str, Any]:
    normalized = normalize_os_key(os_key)
    spec = RECOMMENDED_OS.get(normalized)
    if not spec:
        return {
            "ok": False,
            "error": f"Unknown os key: {os_key}",
            "valid_os_keys": valid_os_keys(),
            "aliases": OS_ALIASES,
        }

    label = spec["label"]
    default_user = spec["default_ssh_username"]
    resolver = spec["resolver"]

    if resolver == "amazon_linux":
        result = resolve_amazon_linux_ami(session, region, max_results=max_results)
    elif resolver == "ubuntu":
        result = resolve_ubuntu_ami(session, region, max_results=max_results)
    elif resolver == "rhel":
        result = resolve_rhel_ami(session, region, max_results=max_results)
    elif resolver == "debian":
        result = resolve_debian_ami(session, region, max_results=max_results)
    else:
        return {"ok": False, "error": f"Unsupported resolver: {resolver}"}

    result["os"] = normalized
    if normalized != os_key:
        result["os_alias"] = os_key
    result["label"] = label
    rank = os_preference_rank(normalized)
    if rank is not None:
        result["preference_rank"] = rank
    framework_note = spec.get("framework_note")
    if framework_note:
        result["framework_note"] = framework_note

    if result.get("item"):
        if not result["item"].get("suggested_ssh_username"):
            result["item"]["suggested_ssh_username"] = default_user
    for item in result.get("items", []):
        if not item.get("suggested_ssh_username"):
            item["suggested_ssh_username"] = default_user
    return result


def recommended_os_amis(session: Any, region: str) -> Dict[str, Any]:
    entries = {}
    all_ok = True
    for os_key in RECOMMENDED_OS_ORDER:
        entry = resolve_recommended_os_ami(session, region, os_key, max_results=1)
        entries[os_key] = entry
        if not entry.get("ok"):
            all_ok = False
    return {
        "ok": all_ok,
        "region": region,
        "preference_order": list(RECOMMENDED_OS_ORDER),
        "recommended_amis": entries,
    }


def list_amis(
    session: Any,
    region: str,
    name_filter: Optional[str] = None,
    owners: Optional[List[str]] = None,
    max_results: int = 15,
) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    owners_list = list(owners or DEFAULT_AMI_OWNERS)
    filters: List[Dict[str, str]] = [{"Name": "state", "Values": ["available"]}]
    if name_filter:
        filters.append({"Name": "name", "Values": [name_filter]})

    try:
        resp = ec2.describe_images(Owners=owners_list, Filters=filters, MaxResults=min(max_results, 50))
        images = sorted(
            resp.get("Images", []),
            key=lambda i: i.get("CreationDate", ""),
            reverse=True,
        )[:max_results]
        items = []
        for img in images:
            items.append(_ami_item_from_image(img))
        return {"ok": True, "region": region, "items": items}
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc), "items": []}


def format_ami_comment(name: str, description: str, region: str) -> Optional[str]:
    """One-line image note for an ami_id end-of-line comment. No leading hash."""
    image = " ".join(str(name or "").split())
    detail = " ".join(str(description or "").split())
    where = " (%s)" % region if region else ""
    if image and detail:
        return "%s%s. %s" % (image, where, detail)
    if image or detail:
        return "%s%s" % (image or detail, where)
    return None


def ami_comment_for_config(region: str, ami_id: str) -> Optional[str]:
    """Image name and description for a config comment. None when AWS cannot describe it."""
    if boto3 is None or not region or not ami_id:
        return None
    try:
        described = describe_ami(_session(region), region, ami_id)
    except Exception:
        return None
    if not isinstance(described, dict) or not described.get("ok"):
        return None
    return format_ami_comment(
        str(described.get("name") or ""),
        str(described.get("description") or ""),
        region,
    )


def describe_ami(session: Any, region: str, ami_id: str) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_images(ImageIds=[ami_id])
        images = resp.get("Images", [])
        if not images:
            return {"ok": False, "error": f"AMI not found: {ami_id}"}
        img = images[0]
        item = _ami_item_from_image(img)
        item["ok"] = True
        item["state"] = img.get("State")
        return item
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc)}


def list_instance_types(
    session: Any,
    region: str,
    family: Optional[str] = None,
    curated: bool = True,
) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_instance_type_offerings(
            LocationType="region",
            Filters=[{"Name": "location", "Values": [region]}],
        )
        offered = {o["InstanceType"] for o in resp.get("InstanceTypeOfferings", [])}
        if family:
            prefix = family if family.endswith(".") else f"{family}."
            offered = {t for t in offered if t.startswith(prefix)}
        if curated:
            items = [t for t in ENV_INSTANCE_TYPES if t in offered]
            if not items:
                items = sorted(offered)[:10]
        else:
            items = sorted(offered)
        return {"ok": True, "region": region, "items": items}
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc), "items": []}


def list_key_pairs(session: Any, region: str) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_key_pairs()
        items = [{"name": k["KeyName"], "key_pair_id": k.get("KeyPairId")} for k in resp.get("KeyPairs", [])]
        return {"ok": True, "region": region, "items": sorted(items, key=lambda x: x["name"])}
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc), "items": []}


_SENSITIVE_PORTS = (22, 80, 8000, 8088, 8089)


def _permission_ports(permission: Dict[str, Any]) -> set:
    protocol = str(permission.get("IpProtocol") or "")
    if protocol == "-1":
        return set(_SENSITIVE_PORTS)
    start = permission.get("FromPort")
    if start is None:
        return set()
    end = permission.get("ToPort")
    if end is None:
        end = start
    return {port for port in _SENSITIVE_PORTS if start <= port <= end}


def _exposure_warnings(group_name: str, permissions: Any) -> List[str]:
    """Name a group that allows the world onto Splunk or SSH ports. No rule dump."""
    by_cidr: Dict[str, set] = {}
    for permission in permissions or []:
        if not isinstance(permission, dict):
            continue
        cidrs = []
        for row in permission.get("IpRanges") or []:
            cidr = row.get("CidrIp") if isinstance(row, dict) else None
            if cidr == "0.0.0.0/0":
                cidrs.append(cidr)
        for row in permission.get("Ipv6Ranges") or []:
            cidr = row.get("CidrIpv6") if isinstance(row, dict) else None
            if cidr == "::/0":
                cidrs.append(cidr)
        ports = _permission_ports(permission)
        for cidr in cidrs:
            by_cidr.setdefault(cidr, set()).update(ports)
    warnings = []
    for cidr, ports in by_cidr.items():
        if not ports:
            continue
        listed = ", ".join(str(port) for port in sorted(ports))
        label = "port" if len(ports) == 1 else "ports"
        warnings.append("security group %s allows %s to %s %s" % (group_name, cidr, label, listed))
    return warnings


def list_security_groups(session: Any, region: str) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_security_groups()
        items = []
        for sg in resp.get("SecurityGroups", []):
            items.append(
                {
                    "group_id": sg.get("GroupId"),
                    "group_name": sg.get("GroupName"),
                    "description": sg.get("Description"),
                }
            )
        items.sort(key=lambda x: x["group_name"] or "")
        return {"ok": True, "region": region, "items": items}
    except (ClientError, BotoCoreError) as exc:
        return {"ok": False, "error": str(exc), "items": []}


def validate_selections(
    session: Any,
    region: str,
    ami_id: Optional[str] = None,
    key_name: Optional[str] = None,
    security_groups: Optional[List[str]] = None,
    instance_type: Optional[str] = None,
) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    all_ok = True

    auth = check_auth(session)
    checks["auth"] = auth
    if not auth.get("ok"):
        all_ok = False

    if ami_id:
        ami_result = describe_ami(session, region, ami_id)
        checks["ami"] = ami_result
        if not ami_result.get("ok"):
            all_ok = False

    if key_name:
        kp = list_key_pairs(session, region)
        names = {i["name"] for i in kp.get("items", [])}
        kp_ok = key_name in names
        checks["key_pair"] = {"ok": kp_ok, "key_name": key_name, "found": kp_ok}
        if not kp_ok:
            all_ok = False

    warnings: List[str] = []
    if security_groups:
        described: List[Dict[str, Any]] = []
        try:
            ec2 = session.client("ec2", region_name=region)
            resp = ec2.describe_security_groups()
            described = list(resp.get("SecurityGroups") or [])
        except (ClientError, BotoCoreError):
            described = []
        by_name = {sg.get("GroupName"): sg for sg in described}
        sg_checks = []
        for name in security_groups:
            group = by_name.get(name)
            found = isinstance(group, dict)
            sg_checks.append(
                {
                    "group_name": name,
                    "ok": found,
                    "group_id": (group or {}).get("GroupId") if found else None,
                }
            )
            if found:
                warnings.extend(_exposure_warnings(name, group.get("IpPermissions") or []))
            else:
                all_ok = False
        checks["security_groups"] = {"ok": all(s["ok"] for s in sg_checks), "items": sg_checks}

    if instance_type:
        it = list_instance_types(session, region, family=instance_type.split(".")[0], curated=False)
        offered = set(it.get("items", []))
        it_ok = instance_type in offered
        checks["instance_type"] = {
            "ok": it_ok,
            "instance_type": instance_type,
            "offered_in_region": it_ok,
        }
        if not it_ok:
            all_ok = False

    result = {"ok": all_ok, "region": region, "checks": checks}
    if warnings:
        result["warnings"] = warnings
    return result


def survey(session: Any, region: str) -> Dict[str, Any]:
    auth = check_auth(session)
    result: Dict[str, Any] = {
        "ok": auth.get("ok", False),
        "region": region,
        "auth": auth,
    }
    if not auth.get("ok"):
        result["error"] = auth.get("error")
        return result

    result["key_pairs"] = list_key_pairs(session, region)
    result["security_groups"] = list_security_groups(session, region)
    result["instance_types_t3"] = list_instance_types(session, region, family="t3", curated=True)
    ami_info = recommended_os_amis(session, region)
    result["recommended_amis"] = ami_info.get("recommended_amis", {})
    if not ami_info.get("ok"):
        result["ok"] = False
    return result


def parse_security_groups(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [s.strip() for s in re.split(r"[,;]", value) if s.strip()]


_RETIRED_AWS_LISTS = {
    "--list-regions": "regions",
    "--list-amis": "amis",
    "--list-instance-types": "instance-types",
    "--list-key-pairs": "key-pairs",
    "--list-security-groups": "security-groups",
}

_AWS_LIST_KINDS = ("regions", "amis", "instance-types", "key-pairs", "security-groups")

def _listing_command(kind: str) -> str:
    return "spa aws %s list" % kind


def _listing_menu() -> str:
    return (
        "spa aws list has moved.\n"
        "Regions:         %s\n"
        "AMIs:            %s --region REGION\n"
        "Instance types:  %s --region REGION\n"
        "Key pairs:       %s --region REGION\n"
        "Security groups: %s --region REGION"
        % (
            _listing_command("regions"),
            _listing_command("amis"),
            _listing_command("instance-types"),
            _listing_command("key-pairs"),
            _listing_command("security-groups"),
        )
    )


AWS_LIST_EXAMPLES = """
examples:
  spa aws regions list
  spa aws amis list --region REGION [--os OS] [--name-filter PATTERN]
  spa aws instance-types list --region REGION [--family FAMILY]
  spa aws key-pairs list --region REGION
  spa aws security-groups list --region REGION
  spa aws --check-auth
  spa aws --region REGION --latest-ami --os OS
  spa aws --region REGION --survey
  spa aws --region REGION --validate
"""


class AwsArgumentParser(argparse.ArgumentParser):
    """Name the legal list command when a removed --list-* flag is used."""

    json_errors = False

    def error(self, message: str) -> None:
        for flag, kind in _RETIRED_AWS_LISTS.items():
            if flag in message:
                message = "Listing %s is: %s" % (kind, _listing_command(kind))
                break
        else:
            resource = self.prog.removeprefix("spa aws ").strip()
            if resource in _AWS_LIST_KINDS and (
                "required" in message or "invalid choice" in message
            ):
                message = "Listing %s is: %s" % (resource, _listing_command(resource))
            elif "KIND" in message and "required" in message:
                message = _listing_menu()
        if type(self).json_errors:
            from spa.runlog import redact

            sys.stdout.write(
                json.dumps({"ok": False, "error": redact(message)}, separators=(",", ":")) + "\n"
            )
            self.exit(2)
        self.print_usage(sys.stderr)
        self.exit(2, "%s: error: %s\n" % (self.prog, message))


def _add_json_after_kind(parser: argparse.ArgumentParser) -> None:
    """Accept --json after a list kind without clearing a leading --json."""
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print JSON. The default is text.",
    )


def build_parser() -> argparse.ArgumentParser:
    p = AwsArgumentParser(
        prog="spa aws",
        description="AWS discovery and validation for splunk_config.yml",
        epilog=AWS_LIST_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--json", action="store_true", help="Print JSON. The default is text.")
    p.add_argument(
        "--region",
        help="AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config.",
    )
    p.add_argument("--check-auth", action="store_true", help="Verify AWS credentials via STS (no --region required)")
    p.add_argument("--latest-ami", action="store_true", help="Resolve latest AMI for recommended OS (--os)")
    p.add_argument(
        "--os",
        help="Recommended OS for --latest-ami: rhel, ubuntu, amazon_linux, debian (or all). Aliases: al2023, rhel10, ubuntu2404",
    )
    p.add_argument("--describe-ami", action="store_true", help="Describe one AMI")
    p.add_argument("--ami-id", help="AMI ID for describe or validate")
    p.add_argument("--validate", action="store_true", help="Validate selections")
    p.add_argument(
        "--details",
        action="store_true",
        help="Include the full validation checks",
    )
    p.add_argument("--key-name", help="Key pair name for validate")
    p.add_argument("--security-groups", help="Comma-separated security group names for validate")
    p.add_argument("--instance-type", help="Instance type for validate")
    p.add_argument("--survey", action="store_true", help="Combined discovery report for a region")

    commands = p.add_subparsers(dest="aws_command", parser_class=AwsArgumentParser)
    region_help = (
        "AWS region. Defaults to AWS_REGION, AWS_DEFAULT_REGION, or the region in ~/.aws/config."
    )

    def _add_catalog(name: str, summary: str) -> argparse.ArgumentParser:
        resource = commands.add_parser(name, help=summary)
        _add_json_after_kind(resource)
        actions = resource.add_subparsers(
            dest="aws_action",
            required=True,
            metavar="ACTION",
            parser_class=AwsArgumentParser,
        )
        listing = actions.add_parser("list", help=summary)
        _add_json_after_kind(listing)
        listing.set_defaults(aws_list_kind=name)
        return listing

    _add_catalog("regions", "List enabled regions")

    amis = _add_catalog("amis", "List AMIs in a region")
    amis.add_argument("--region", default=argparse.SUPPRESS, help=region_help)
    amis.add_argument("--name-filter", help="AMI name wildcard (not used with --os)")
    amis.add_argument(
        "--owners",
        help="Comma-separated AMI owners (default: amazon,aws-marketplace,self)",
    )
    amis.add_argument("--max-results", type=int, default=15, help="Max AMIs to return")
    amis.add_argument(
        "--os",
        default=argparse.SUPPRESS,
        help="Recommended OS: rhel, ubuntu, amazon_linux, debian (or all). Aliases: al2023, rhel10, ubuntu2404",
    )

    instance_types = _add_catalog("instance-types", "List instance types offered in a region")
    instance_types.add_argument("--region", default=argparse.SUPPRESS, help=region_help)
    instance_types.add_argument("--family", default=argparse.SUPPRESS, help="Instance type family prefix (e.g. t3)")

    key_pairs = _add_catalog("key-pairs", "List EC2 key pairs")
    key_pairs.add_argument("--region", default=argparse.SUPPRESS, help=region_help)

    security_groups = _add_catalog("security-groups", "List security groups")
    security_groups.add_argument("--region", default=argparse.SUPPRESS, help=region_help)
    return p


def _aws_result(data: Dict[str, Any], error: Optional[str] = None):
    from spa.api import CommandResult

    ok = bool(data.get("ok", True)) if isinstance(data, dict) else True
    return CommandResult(
        ok=ok if error is None else False,
        data=data,
        error=error or (None if ok else data.get("error")),
        code=0 if (ok and not error) else 1,
    )


def _list_amis_result(session: Any, args: Any):
    from spa.api import CommandResult

    os_name = getattr(args, "os", None)
    max_results = getattr(args, "max_results", 15)
    if os_name:
        if os_name == "all":
            os_keys = valid_os_keys()
        else:
            normalized = normalize_os_key(os_name)
            if normalized not in RECOMMENDED_OS:
                return CommandResult(
                    ok=False,
                    error=(
                        "Unknown --os %s. Valid: %s, all (aliases: %s)"
                        % (os_name, ", ".join(valid_os_keys()), ", ".join(OS_ALIASES))
                    ),
                    code=1,
                )
            os_keys = [normalized]
        combined: Dict[str, Any] = {"ok": True, "region": args.region, "items": []}
        for key in os_keys:
            entry = resolve_recommended_os_ami(
                session, args.region, key, max_results=max_results
            )
            if not entry.get("ok"):
                combined["ok"] = False
            if entry.get("item"):
                combined["items"].append({**entry["item"], "os": key, "label": entry.get("label")})
            else:
                for item in entry.get("items", []):
                    combined["items"].append({**item, "os": key, "label": entry.get("label")})
        return _aws_result(combined)
    owners = args.owners.split(",") if getattr(args, "owners", None) else None
    return _aws_result(
        list_amis(session, args.region, getattr(args, "name_filter", None), owners, max_results)
    )


def execute(args: Any, environment_region: Optional[str] = None):
    from spa.api import CommandResult

    kind = getattr(args, "aws_list_kind", None)
    if kind and kind != "amis" and getattr(args, "os", None):
        return CommandResult(ok=False, error="--os requires: spa aws amis list", code=2)

    if not kind and not any(
        (
            args.check_auth,
            args.survey,
            args.latest_ami,
            args.describe_ami,
            args.validate,
        )
    ):
        return CommandResult(
            ok=False,
            error=(
                "spa aws needs an operation.\n"
                "List:       spa aws regions list\n"
                "            spa aws amis list --region REGION\n"
                "            spa aws instance-types list --region REGION\n"
                "            spa aws key-pairs list --region REGION\n"
                "            spa aws security-groups list --region REGION\n"
                "Auth:       spa aws --check-auth\n"
                "Latest AMI: spa aws --region REGION --latest-ami --os OS\n"
                "Survey:     spa aws --region REGION --survey\n"
                "Validate:   spa aws --region REGION --validate"
            ),
            code=2,
        )

    if args.check_auth:
        return _aws_result(check_auth(_session()))

    if kind == "regions":
        resolved = resolve_region(getattr(args, "region", None), environment_region)
        try:
            session = _session()
        except Exception as exc:  # e.g. botocore ProfileNotFound for a missing AWS_PROFILE; SystemExit from a missing boto3 still exits
            from spa.runlog import redact

            data = {"ok": False, "error": redact(str(exc)), "items": []}
        else:
            data = list_regions(session, selected_region=resolved.region)
        _stamp_region(data, resolved)
        if isinstance(data, dict):
            # The region in ~/.aws/config, even when an environment config overrides it.
            config_region = _region_from_aws_config()
            data["aws_config_region"] = config_region.region
            data["aws_config_profile"] = config_region.profile
        return _aws_result(data)

    if kind in {"amis", "instance-types", "key-pairs", "security-groups"}:
        resolved = resolve_region(getattr(args, "region", None), environment_region)
        if not resolved.region:
            return CommandResult(
                ok=False,
                error=(
                    "--region is required for %s. "
                    "Or set AWS_REGION, AWS_DEFAULT_REGION, or region in ~/.aws/config."
                )
                % _listing_command(kind),
                code=2,
            )
        args.region = resolved.region
        session = _session(resolved.region)
        if kind == "amis":
            return _finish(_list_amis_result(session, args), resolved)
        if kind == "instance-types":
            family = getattr(args, "family", None)
            return _finish(
                _aws_result(
                    list_instance_types(session, args.region, family=family, curated=not family)
                ),
                resolved,
            )
        if kind == "key-pairs":
            return _finish(_aws_result(list_key_pairs(session, args.region)), resolved)
        return _finish(_aws_result(list_security_groups(session, args.region)), resolved)

    resolved = resolve_region(getattr(args, "region", None), environment_region)
    if not resolved.region:
        return CommandResult(
            ok=False,
            error=(
                "--region is required for this operation (except spa aws regions list and --check-auth). "
                "Or set AWS_REGION, AWS_DEFAULT_REGION, or region in ~/.aws/config."
            ),
            code=1,
        )

    args.region = resolved.region
    session = _session(resolved.region)

    if args.survey:
        return _finish(_aws_result(survey(session, args.region)), resolved)

    if args.latest_ami:
        if not args.os:
            return CommandResult(
                ok=False,
                error="--os is required for --latest-ami (rhel, ubuntu, amazon_linux, debian, or all)",
                code=1,
            )
        if args.os == "all":
            return _finish(_aws_result(recommended_os_amis(session, args.region)), resolved)
        normalized = normalize_os_key(args.os)
        if normalized not in RECOMMENDED_OS:
            return CommandResult(
                ok=False,
                error=(
                    "Unknown --os %s. Valid: %s, all (aliases: %s)"
                    % (args.os, ", ".join(valid_os_keys()), ", ".join(OS_ALIASES))
                ),
                code=1,
            )
        return _finish(
            _aws_result(resolve_recommended_os_ami(session, args.region, normalized, max_results=1)),
            resolved,
        )

    if args.describe_ami:
        if not args.ami_id:
            return CommandResult(ok=False, error="--ami-id is required for --describe-ami", code=1)
        return _finish(_aws_result(describe_ami(session, args.region, args.ami_id)), resolved)

    if args.validate:
        sg = parse_security_groups(args.security_groups)
        return _finish(
            _aws_result(
                validate_selections(
                    session,
                    args.region,
                    ami_id=args.ami_id,
                    key_name=args.key_name,
                    security_groups=sg,
                    instance_type=args.instance_type,
                )
            ),
            resolved,
        )

    return CommandResult(
        ok=False,
        error=(
            "spa aws needs an operation.\n"
            "List:       spa aws regions list\n"
            "Auth:       spa aws --check-auth\n"
            "Latest AMI: spa aws --region REGION --latest-ami --os OS\n"
            "Survey:     spa aws --region REGION --survey\n"
            "Validate:   spa aws --region REGION --validate"
        ),
        code=2,
    )


def _retired_list_message(argv: Sequence[str]) -> Optional[str]:
    """The old spa aws list KIND form names the resource command and exits."""
    tokens = [token for token in argv if token and not str(token).startswith("-")]
    if not tokens or tokens[0] != "list":
        return None
    if len(tokens) > 1 and tokens[1] in _AWS_LIST_KINDS:
        return "Listing %s is: %s" % (tokens[1], _listing_command(tokens[1]))
    return _listing_menu()


def _compact_validate_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """One ok per check that validate_selections returned. No nested objects."""
    checks = data.get("checks")
    if not isinstance(checks, dict):
        return data
    projected = dict(data)
    compact = {}
    for name, entry in checks.items():
        ok = entry.get("ok") if isinstance(entry, dict) else bool(entry)
        compact[name] = {"ok": bool(ok)}
    projected["checks"] = compact
    return projected


def execute_argv(argv: Optional[List[str]] = None, environment_region: Optional[str] = None):
    raw = list(sys.argv[1:] if argv is None else argv)
    retired = _retired_list_message(raw)
    if retired:
        from spa.api import CommandResult

        return CommandResult(ok=False, error=retired, code=2)
    return execute(build_parser().parse_args(raw), environment_region=environment_region)


def main(argv: Optional[List[str]] = None, as_agent: bool = False, environment_region: Optional[str] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    AwsArgumentParser.json_errors = bool(as_agent or "--json" in raw)
    try:
        retired = _retired_list_message(raw)
        if retired:
            if as_agent or "--json" in raw:
                from spa.runlog import redact

                print(json.dumps({"ok": False, "error": redact(retired)}, separators=(",", ":")))
            else:
                _err(retired)
            return 2
        args = build_parser().parse_args(raw)
        result = execute(args, environment_region=environment_region)
        as_json = bool(args.json or as_agent)
        shown = result.data
        if (
            as_json
            and getattr(args, "validate", False)
            and not getattr(args, "details", False)
            and isinstance(shown, dict)
        ):
            shown = _compact_validate_payload(shown)
        if shown is not None:
            _output(shown, as_json)
        elif result.error:
            if as_json:
                from spa.runlog import redact

                print(json.dumps({"ok": False, "error": redact(result.error)}, separators=(",", ":")))
            else:
                _err(result.error)
        return result.code
    finally:
        AwsArgumentParser.json_errors = False


if __name__ == "__main__":
    sys.exit(main())
