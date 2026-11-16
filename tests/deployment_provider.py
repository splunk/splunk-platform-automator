"""Pluggable provider identity hooks for live deployment compose."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

OS_PACKAGES = {
    "ubuntu": ["acl", "policykit-1"],
    "debian": ["acl", "policykit-1"],
    "rhel": ["acl", "polkit"],
    "amazon_linux": ["acl", "polkit"],
}

SSH_USERNAME_FALLBACK = {
    "ubuntu": "ubuntu",
    "debian": "admin",
    "rhel": "ec2-user",
    "amazon_linux": "ec2-user",
}

SPA_BIN = Path(__file__).resolve().parents[1] / "bin" / "spa"
_AMI_CACHE: Dict[tuple[str, str], Dict[str, Any]] = {}

AmiResolver = Callable[[str, str], Mapping[str, Any]]


class ProviderHookError(Exception):
    """Raised when a provider hook cannot fill AMI / SSH identity."""


def fetch_latest_ami_payload(*, os_key: str, region: str) -> Dict[str, Any]:
    """Call `spa --agent provider aws latest-ami`. Cached per (region, os_key)."""
    cache_key = (region, os_key)
    cached = _AMI_CACHE.get(cache_key)
    if cached is not None:
        return cached
    env = os.environ.copy()
    env.pop("SPA_ENV_DIR", None)
    env.pop("SPLUNK_CONFIG_FILE", None)
    result = subprocess.run(
        [
            str(SPA_BIN),
            "--agent",
            "provider",
            "aws",
            "latest-ami",
            "--region",
            region,
            "--os",
            os_key,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(SPA_BIN.parent),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "exit %s" % result.returncode
        raise ProviderHookError("spa provider aws latest-ami failed: %s" % detail)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProviderHookError("spa provider aws latest-ami returned non-JSON") from exc
    if not payload.get("ok"):
        raise ProviderHookError(payload.get("error") or "spa provider aws latest-ami failed")
    _AMI_CACHE[cache_key] = payload
    return payload


def _payload_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, Mapping) else payload


def _ami_item(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    item = entry.get("item")
    if isinstance(item, Mapping) and item.get("ami_id"):
        return item
    items = entry.get("items")
    if isinstance(items, list) and items and isinstance(items[0], Mapping):
        return items[0]
    if entry.get("ami_id"):
        return entry
    return {}


def ami_identity_from_payload(payload: Mapping[str, Any], os_key: str) -> Dict[str, str]:
    data = _payload_data(payload)
    recommended = data.get("recommended_amis")
    if isinstance(recommended, Mapping):
        entry = recommended.get(os_key) or {}
        item = _ami_item(entry if isinstance(entry, Mapping) else {})
    else:
        item = _ami_item(data)
    ami_id = item.get("ami_id")
    if not ami_id:
        raise ProviderHookError("latest-ami payload missing ami_id for os %s" % os_key)
    username = item.get("suggested_ssh_username") or SSH_USERNAME_FALLBACK[os_key]
    return {"ami_id": str(ami_id), "suggested_ssh_username": str(username)}


def _merge_packages(os_block: Dict[str, Any], os_key: str) -> None:
    packages = list(os_block.get("packages") or [])
    for pkg in OS_PACKAGES[os_key]:
        if pkg not in packages:
            packages.append(pkg)
    os_block["packages"] = packages


class AwsProviderHook:
    id = "aws"

    def compose_identity(
        self,
        config: Dict[str, Any],
        *,
        os_key: str,
        extra_ufs: Optional[Mapping[str, str]] = None,
        region: str,
        ami_resolver: Optional[AmiResolver] = None,
    ) -> Dict[str, Any]:
        extra_ufs = dict(extra_ufs or {})
        needed = {os_key, *extra_ufs.values()}
        unknown = sorted(key for key in needed if key not in OS_PACKAGES)
        if unknown:
            raise ProviderHookError("unknown os key(s): %s" % ", ".join(unknown))
        identities: Dict[str, Mapping[str, Any]] = {}
        if ami_resolver is not None:
            for key in needed:
                identities[key] = ami_resolver(key, region)
        else:
            fetch_key = "all" if len(needed) > 1 else os_key
            payload = fetch_latest_ami_payload(os_key=fetch_key, region=region)
            for key in needed:
                identities[key] = ami_identity_from_payload(payload, key)

        aws = config.setdefault("terraform", {}).setdefault("aws", {})
        primary = identities[os_key]
        aws["ami_id"] = primary["ami_id"]
        aws["ssh_username"] = primary["suggested_ssh_username"]
        _merge_packages(config.setdefault("os", {}), os_key)

        hosts = config.setdefault("splunk_hosts", [])
        for name, guest_os in extra_ufs.items():
            identity = identities[guest_os]
            hosts.append(
                {
                    "name": name,
                    "roles": ["universal_forwarder"],
                    "terraform": {
                        "aws": {
                            "ami_id": identity["ami_id"],
                            "ssh_username": identity["suggested_ssh_username"],
                        }
                    },
                    "os": {"packages": list(OS_PACKAGES[guest_os])},
                }
            )
        return config


PROVIDERS = {
    "aws": AwsProviderHook(),
}
