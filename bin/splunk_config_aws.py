#!/usr/bin/env python3
"""
AWS discovery and validation for splunk_config.yml terraform.aws settings.

Requires boto3 and AWS credentials (env, profile, or instance role).

Examples:
  python3 bin/splunk_config_aws.py --list-regions --json
  python3 bin/splunk_config_aws.py --region eu-central-1 --latest-ami --os amazon_linux --json
  python3 bin/splunk_config_aws.py --region eu-central-1 --latest-ami --os all --json
  python3 bin/splunk_config_aws.py --region eu-central-1 --list-amis --name-filter "custom*" --json
  python3 bin/splunk_config_aws.py --region eu-central-1 --validate \\
    --ami-id ami-xxx --key-name aws_key --security-groups Splunk_Basic \\
    --instance-type t3.medium --json
  python3 bin/splunk_config_aws.py --survey --region eu-central-1 --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
except ImportError:
    boto3 = None  # type: ignore


LAB_INSTANCE_TYPES = ("t3.small", "t3.medium", "t3.large", "t3.xlarge")
DEFAULT_AMI_OWNERS = ("amazon", "aws-marketplace", "self")
RHEL_OFFICIAL_OWNER = "309956199498"  # AWS alias: amazon (official RHEL AMIs)

RHEL_OFFICIAL_OWNER = "309956199498"  # AWS alias: amazon (official RHEL AMIs)
DEBIAN_OFFICIAL_OWNER = "136693071363"  # Debian Cloud Team

# Preference order for labs (RHEL best tested; Debian least tested with SPA).
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


def _output(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))


def _require_boto3() -> None:
    if boto3 is None:
        _err("boto3 is required. Install with: pip install boto3")
        sys.exit(2)


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


def list_regions(session: Any) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name="us-east-1")
    try:
        resp = ec2.describe_regions(AllRegions=False)
        items = [
            {"name": r["RegionName"], "endpoint": r.get("Endpoint")}
            for r in sorted(resp.get("Regions", []), key=lambda x: x["RegionName"])
        ]
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


def describe_ami(session: Any, region: str, ami_id: str) -> Dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    try:
        resp = ec2.describe_images(ImageIds=[ami_id])
        images = resp.get("Images", [])
        if not images:
            return {"ok": False, "error": f"AMI not found: {ami_id}"}
        img = images[0]
        name = img.get("Name", "")
        desc = img.get("Description", "") or ""
        return {
            "ok": True,
            "ami_id": ami_id,
            "name": name,
            "state": img.get("State"),
            "architecture": img.get("Architecture"),
            "creation_date": img.get("CreationDate"),
            "suggested_ssh_username": suggest_ssh_username(name, desc),
        }
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
            items = [t for t in LAB_INSTANCE_TYPES if t in offered]
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

    if security_groups:
        sg_resp = list_security_groups(session, region)
        by_name = {i["group_name"]: i for i in sg_resp.get("items", [])}
        sg_checks = []
        for name in security_groups:
            found = name in by_name
            sg_checks.append({"group_name": name, "ok": found, "group_id": by_name.get(name, {}).get("group_id")})
            if not found:
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

    return {"ok": all_ok, "region": region, "checks": checks}


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AWS discovery and validation for splunk_config.yml")
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument("--region", help="AWS region")

    p.add_argument("--list-regions", action="store_true", help="List enabled regions")
    p.add_argument("--list-amis", action="store_true", help="List AMIs in region (use --name-filter or --os)")
    p.add_argument("--latest-ami", action="store_true", help="Resolve latest AMI for recommended OS (--os)")
    p.add_argument(
        "--os",
        help="Recommended OS: rhel, ubuntu, amazon_linux, debian (or all). Aliases: al2023, rhel10, ubuntu2404",
    )
    p.add_argument("--name-filter", help="AMI name wildcard for custom --list-amis (not used for recommended OS)")
    p.add_argument(
        "--owners",
        help="Comma-separated AMI owners (default: amazon,aws-marketplace,self)",
    )
    p.add_argument("--list-instance-types", action="store_true", help="List instance types offered in region")
    p.add_argument("--family", help="Instance type family prefix (e.g. t3)")
    p.add_argument("--list-key-pairs", action="store_true", help="List EC2 key pairs")
    p.add_argument("--list-security-groups", action="store_true", help="List security groups")
    p.add_argument("--describe-ami", action="store_true", help="Describe one AMI")
    p.add_argument("--ami-id", help="AMI ID for describe or validate")
    p.add_argument("--validate", action="store_true", help="Validate selections")
    p.add_argument("--key-name", help="Key pair name for validate")
    p.add_argument("--security-groups", help="Comma-separated security group names for validate")
    p.add_argument("--instance-type", help="Instance type for validate")
    p.add_argument("--survey", action="store_true", help="Combined discovery report for a region")
    p.add_argument("--max-results", type=int, default=15, help="Max AMIs to return")
    return p


def main() -> int:
    args = build_parser().parse_args()
    as_json = args.json

    if args.list_regions:
        session = _session()
        result = list_regions(session)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if not args.region and not args.list_regions:
        _err("--region is required for this operation (except --list-regions)")
        return 1

    session = _session(args.region)

    if args.survey:
        result = survey(session, args.region)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.list_amis:
        if args.os:
            if args.os == "all":
                os_keys = valid_os_keys()
            else:
                normalized = normalize_os_key(args.os)
                if normalized not in RECOMMENDED_OS:
                    _err(
                        f"Unknown --os {args.os}. Valid: {', '.join(valid_os_keys())}, all "
                        f"(aliases: {', '.join(OS_ALIASES)})"
                    )
                    return 1
                os_keys = [normalized]
            combined: Dict[str, Any] = {"ok": True, "region": args.region, "items": []}
            for key in os_keys:
                entry = resolve_recommended_os_ami(
                    session, args.region, key, max_results=args.max_results
                )
                if not entry.get("ok"):
                    combined["ok"] = False
                if entry.get("item"):
                    combined["items"].append({**entry["item"], "os": key, "label": entry.get("label")})
                else:
                    for item in entry.get("items", []):
                        combined["items"].append({**item, "os": key, "label": entry.get("label")})
            _output(combined, as_json)
            return 0 if combined.get("ok") else 1
        owners = args.owners.split(",") if args.owners else None
        result = list_amis(session, args.region, args.name_filter, owners, args.max_results)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.latest_ami:
        if not args.os:
            _err("--os is required for --latest-ami (rhel, ubuntu, amazon_linux, debian, or all)")
            return 1
        if args.os == "all":
            result = recommended_os_amis(session, args.region)
        else:
            normalized = normalize_os_key(args.os)
            if normalized not in RECOMMENDED_OS:
                _err(
                    f"Unknown --os {args.os}. Valid: {', '.join(valid_os_keys())}, all "
                    f"(aliases: {', '.join(OS_ALIASES)})"
                )
                return 1
            result = resolve_recommended_os_ami(session, args.region, normalized, max_results=1)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.list_instance_types:
        result = list_instance_types(session, args.region, family=args.family, curated=not args.family)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.list_key_pairs:
        result = list_key_pairs(session, args.region)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.list_security_groups:
        result = list_security_groups(session, args.region)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.describe_ami:
        if not args.ami_id:
            _err("--ami-id is required for --describe-ami")
            return 1
        result = describe_ami(session, args.region, args.ami_id)
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    if args.validate:
        sg = parse_security_groups(args.security_groups)
        result = validate_selections(
            session,
            args.region,
            ami_id=args.ami_id,
            key_name=args.key_name,
            security_groups=sg,
            instance_type=args.instance_type,
        )
        _output(result, as_json)
        return 0 if result.get("ok") else 1

    _err("No operation specified. Use --list-regions, --latest-ami, --list-amis, --validate, or --survey.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
