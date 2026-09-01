#!/usr/bin/env python3
"""
AWS discovery and validation for splunk_config.yml terraform.aws settings.

Requires boto3 and AWS credentials (env, profile, or instance role).

Examples:
  python3 bin/splunk_config_aws.py --list-regions --json
  python3 bin/splunk_config_aws.py --region eu-central-1 --list-amis --name-filter "RHEL*10*" --json
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
    return "ec2-user"


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
            name = img.get("Name", "")
            desc = img.get("Description", "") or ""
            items.append(
                {
                    "ami_id": img.get("ImageId"),
                    "name": name,
                    "creation_date": img.get("CreationDate"),
                    "architecture": img.get("Architecture"),
                    "suggested_ssh_username": suggest_ssh_username(name, desc),
                }
            )
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
    result["amis_rhel10"] = list_amis(session, region, name_filter="RHEL*10*", max_results=10)
    result["amis_ubuntu"] = list_amis(session, region, name_filter="ubuntu/images/hvm-ssd/ubuntu-*22.04*", max_results=10)
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
    p.add_argument("--list-amis", action="store_true", help="List AMIs in region")
    p.add_argument("--name-filter", help="AMI name wildcard filter for --list-amis")
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
        owners = args.owners.split(",") if args.owners else None
        result = list_amis(session, args.region, args.name_filter, owners, args.max_results)
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

    _err("No operation specified. Use --list-regions, --list-amis, --validate, or --survey.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
