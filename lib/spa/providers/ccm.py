"""Corporate Cloud Manager (CCM) EC2 lifecycle.

Auth is the process environment variable CCM_TOKEN only. Never print the PAT.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from spa.paths import SpaPaths
from spa.providers import (
    ProviderError,
    ProvisionState,
    expected_hostnames,
    load_deployment_config,
)
from spa.providers.external import inventory_line, upsert_inventory

TOKEN_ENV = "CCM_TOKEN"
API_ROOT = "https://api.ccm.splunkits.io"
DEFAULT_TIMEOUT = 30
DEPLOYMENTS_PATH = "/api/v1/deployments"
MAX_INSTANCES = 50
NAME_MIN = 5
NAME_MAX = 100
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][\w-]*[a-zA-Z0-9]$")
DEFAULT_TTL_DAYS = 7
DEFAULT_DISK_STORAGE = 50
DEFAULT_TIMEZONE = "UTC"
DEFAULT_OPERATION_HOURS = "manual"
DEFAULT_BUSINESS_PURPOSE = "DeveloperInstance"
DEFAULT_SSH_USERNAME = "ec2-user"
DEFAULT_SSH_KEY_FILE = "~/.ssh/CCM-Key.pem"
POLL_INTERVAL = 5
POLL_ATTEMPTS = 180
TTL_MAX_DAYS = 30


class CcmError(RuntimeError):
    """HTTP or auth failure. Message must not contain the PAT."""


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse HTTP downgrades and drop Bearer on a host change."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlparse(req.full_url)
        new = urllib.parse.urlparse(newurl)
        if new.scheme != "https":
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_origin = (old.scheme.lower(), (old.hostname or "").lower(), old.port)
        new_origin = (new.scheme.lower(), (new.hostname or "").lower(), new.port)
        if old_origin != new_origin:
            redirected.remove_header("Authorization")
        return redirected


def token_present(environ: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    return bool((env.get(TOKEN_ENV) or "").strip())


def token_state(environ: Optional[Mapping[str, str]] = None) -> str:
    return "set" if token_present(environ) else "not set"


class UrllibCcmClient:
    """HTTPS client for api.ccm.splunkits.io. Token is Bearer CCM_TOKEN."""

    def __init__(
        self,
        token: str,
        *,
        opener: Optional[Any] = None,
        timeout: int = DEFAULT_TIMEOUT,
        base_url: str = API_ROOT,
    ) -> None:
        if not (token or "").strip():
            raise CcmError("%s: not set" % TOKEN_ENV)
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https":
            raise CcmError("CCM API URL must be HTTPS")
        self._token = token.strip()
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        if opener is not None:
            self._opener = opener
        else:
            ctx = ssl.create_default_context()
            self._opener = urllib.request.build_opener(
                _HttpsOnlyRedirectHandler(),
                urllib.request.HTTPSHandler(context=ctx),
            )

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "UrllibCcmClient":
        env = os.environ if environ is None else environ
        return cls((env.get(TOKEN_ENV) or "").strip())

    def _url(self, path: str) -> str:
        if path.startswith("http://"):
            raise CcmError("CCM API URL must be HTTPS")
        if path.startswith("https://"):
            url = path
        else:
            url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        if urllib.parse.urlparse(url).scheme != "https":
            raise CcmError("CCM API URL must be HTTPS")
        return url

    def _redact(self, text: str) -> str:
        if self._token and self._token in text:
            return text.replace(self._token, TOKEN_ENV)
        return text

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, str]] = None,
        body: Optional[Any] = None,
    ) -> Tuple[int, Any]:
        url = self._url(path)
        if query:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
        headers = {
            "User-Agent": "spa",
            "Authorization": "Bearer %s" % self._token,
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                raw = resp.read() or b""
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read() or b""
        except urllib.error.URLError as exc:
            raise CcmError(self._redact("CCM API request failed")) from exc
        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            return status, None
        try:
            return status, json.loads(text)
        except json.JSONDecodeError as exc:
            raise CcmError("CCM API returned invalid JSON") from exc


def ping(client: Optional[UrllibCcmClient] = None) -> None:
    """GET /api/v1/deployments. Raises CcmError; never includes the PAT or body."""
    http = client or UrllibCcmClient.from_env()
    status, _payload = http.request("GET", DEPLOYMENTS_PATH)
    if status >= 400:
        raise CcmError("CCM API returned HTTP %s" % status)


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _ttl_stamp(when: datetime, days: int) -> str:
    expiry = when.astimezone(timezone.utc) + timedelta(days=int(days))
    return expiry.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _deployment_ids(payload: Any) -> List[str]:
    data = _unwrap(payload)
    rows: List[Any]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        nested = data.get("deployments") or data.get("items") or []
        rows = nested if isinstance(nested, list) else []
    else:
        rows = []
    ids = []
    for row in rows:
        if isinstance(row, dict) and row.get("deployment_id"):
            ids.append(str(row["deployment_id"]))
    return ids


class Provider:
    name = "ccm"

    def __init__(
        self,
        paths: SpaPaths,
        config: Dict[str, Any],
        client: Optional[UrllibCcmClient] = None,
        sleep: Optional[Callable[[float], None]] = None,
        now: Optional[Callable[[], datetime]] = None,
        poll_interval: int = POLL_INTERVAL,
        poll_attempts: int = POLL_ATTEMPTS,
    ) -> None:
        self.paths = paths
        # Slice 3 reads these from the ccm: block (not hardcoded here):
        # operating_system, instance_type, disk_storage, key_name (API ssh_key_name),
        # ssh_private_key_file, ssh_username.
        self.config = config
        self.state_dir = paths.spa_env_dir / "ccm"
        self._client = client
        self._sleep = sleep or time.sleep
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._poll_interval = poll_interval
        self._poll_attempts = poll_attempts

    def _read_state(self) -> Optional[Dict[str, Any]]:
        path = self.state_dir / "state.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _expired_state(self, deployment_id: str) -> ProvisionState:
        return ProvisionState(
            provider=self.name,
            provisioned=False,
            reason=(
                "CCM terminated this deployment (TTL expiry or CCM terminate): %s"
                % deployment_id
            ),
            hint="spa destroy --yes then spa provision --yes",
        )

    def provision_state(self) -> ProvisionState:
        recorded = self._read_state()
        deployment_id = str((recorded or {}).get("deployment_id") or "")
        if not deployment_id:
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="No CCM state for this env: %s" % self.state_dir,
                hint="spa provision --yes",
            )
        if self._client is None and not token_present():
            return ProvisionState(provider=self.name, provisioned=True)
        try:
            http = self._http()
            path = "%s/%s" % (
                DEPLOYMENTS_PATH,
                urllib.parse.quote(deployment_id, safe=""),
            )
            status, payload = http.request("GET", path)
            if status == 404:
                return self._expired_state(deployment_id)
            if status < 400 and _unwrap(payload):
                return ProvisionState(provider=self.name, provisioned=True)
            status, payload = http.request("GET", DEPLOYMENTS_PATH)
            if status < 400 and deployment_id not in _deployment_ids(payload):
                return self._expired_state(deployment_id)
        except (CcmError, ProviderError):
            return ProvisionState(provider=self.name, provisioned=True)
        return ProvisionState(provider=self.name, provisioned=True)

    def _not_implemented(self, action: str) -> None:
        raise ProviderError("CCM %s is not implemented yet." % action)

    def _http(self) -> UrllibCcmClient:
        try:
            return self._client or UrllibCcmClient.from_env()
        except CcmError as exc:
            raise ProviderError(str(exc)) from exc

    def _hostnames(self) -> List[str]:
        return expected_hostnames(load_deployment_config(self.paths))

    def _deployment_name(self) -> str:
        explicit = str(self.config.get("name") or "").strip()
        name = explicit or self.paths.spa_env_dir.name
        if (
            len(name) < NAME_MIN
            or len(name) > NAME_MAX
            or not NAME_PATTERN.match(name)
        ):
            raise ProviderError(
                "CCM deployment name %r is invalid (5–100 characters, "
                "letters/numbers/hyphens/underscores, no spaces). "
                "Set ccm.name to a valid name." % name,
                code=2,
            )
        return name

    def _create_body(self, name: str, hosts: List[str]) -> Tuple[Dict[str, Any], str]:
        ttl_days = int(self.config.get("ttl_days") or DEFAULT_TTL_DAYS)
        if ttl_days < 1 or ttl_days > TTL_MAX_DAYS:
            raise ProviderError(
                "ccm.ttl_days must be 1–%s, got %s." % (TTL_MAX_DAYS, ttl_days),
                code=2,
            )
        ttl = _ttl_stamp(self._now(), ttl_days)
        operating_system = self.config.get("operating_system")
        instance_type = self.config.get("instance_type")
        if not operating_system or not instance_type:
            raise ProviderError(
                "ccm.operating_system and ccm.instance_type are required to provision.",
                code=2,
            )
        body: Dict[str, Any] = {
            "name": name,
            "disk_storage": int(self.config.get("disk_storage") or DEFAULT_DISK_STORAGE),
            "operating_system": operating_system,
            "instance_type": instance_type,
            "timezone": self.config.get("timezone") or DEFAULT_TIMEZONE,
            "num_instances": len(hosts),
            "ttl": ttl,
            "operation_hours": self.config.get("operation_hours") or DEFAULT_OPERATION_HOURS,
            "business_purpose": self.config.get("business_purpose")
            or DEFAULT_BUSINESS_PURPOSE,
        }
        key_name = str(self.config.get("key_name") or "").strip()
        if key_name:
            body["ssh_key_name"] = key_name
        description = self.config.get("business_description")
        if description:
            body["business_description"] = description
        ebs = self.config.get("ebs_storage")
        if isinstance(ebs, dict) and (
            ebs.get("ebs_count") is not None or ebs.get("ebs_size") is not None
        ):
            item: Dict[str, Any] = {}
            if ebs.get("ebs_count") is not None:
                item["ebs_count"] = ebs["ebs_count"]
            if ebs.get("ebs_size") is not None:
                item["ebs_size"] = ebs["ebs_size"]
            body["ebs_storage"] = item
        return body, ttl

    def _request(self, method: str, path: str, **kwargs: Any) -> Tuple[int, Any]:
        try:
            return self._http().request(method, path, **kwargs)
        except CcmError as exc:
            raise ProviderError(str(exc)) from exc

    def _poll_until_ready(self, deployment_id: str) -> Dict[str, Any]:
        path = "%s/%s" % (DEPLOYMENTS_PATH, urllib.parse.quote(deployment_id, safe=""))
        for _ in range(self._poll_attempts):
            status, payload = self._request("GET", path)
            if status == 404:
                raise ProviderError(
                    "CCM terminated this deployment (TTL expiry or CCM terminate): %s. "
                    "Run: spa destroy --yes then spa provision --yes" % deployment_id
                )
            if status >= 400:
                raise ProviderError("CCM API returned HTTP %s" % status)
            data = _unwrap(payload) or {}
            if not isinstance(data, dict):
                data = {}
            if str(data.get("req_state") or "").lower() == "ready":
                return data
            self._sleep(self._poll_interval)
        raise ProviderError("CCM deployment %s did not become ready" % deployment_id)

    def _write_state(self, deployment_id: str, ttl: str, hosts: Mapping[str, Mapping[str, Any]]) -> None:
        payload = {
            "deployment_id": deployment_id,
            "ttl": ttl,
            "hosts": {
                name: {"instance_id": row.get("instance_id")}
                for name, row in hosts.items()
            },
        }
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / "state.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def _write_inventory(self, hosts: Mapping[str, Mapping[str, Any]]) -> Any:
        user = self.config.get("ssh_username") or DEFAULT_SSH_USERNAME
        key = self.config.get("ssh_private_key_file") or DEFAULT_SSH_KEY_FILE
        destination = self.paths.inventory_dir / "hosts"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file():
            destination.write_text("", encoding="utf-8")
        for name, row in hosts.items():
            address = str(row.get("ip_address") or "")
            if not address:
                raise ProviderError("CCM instance for %s has no ip_address" % name)
            upsert_inventory(
                destination,
                name,
                inventory_line(name, address, str(user), str(key), 22),
            )
        return destination

    def provision(self, extra: List[str], **kwargs: Any) -> Dict[str, Any]:
        del extra
        hosts = self._hostnames()
        if len(hosts) > MAX_INSTANCES:
            raise ProviderError(
                "This env has %s hosts; CCM accepts at most %s instances in one create."
                % (len(hosts), MAX_INSTANCES),
                code=2,
            )
        name = self._deployment_name()
        body, ttl = self._create_body(name, hosts)
        status, payload = self._request(
            "POST",
            DEPLOYMENTS_PATH,
            query={"type": "ec2"},
            body=body,
        )
        if status >= 400:
            raise ProviderError("CCM API returned HTTP %s" % status)
        created = _unwrap(payload) or {}
        deployment_id = created.get("deployment_id") if isinstance(created, dict) else None
        if not deployment_id:
            raise ProviderError("CCM create did not return a deployment_id")
        ready = self._poll_until_ready(str(deployment_id))
        instances = ready.get("instances_data") or []
        if len(instances) != len(hosts):
            raise ProviderError(
                "CCM returned %s instances for %s hosts." % (len(instances), len(hosts))
            )
        mapped = {}
        for hostname, instance in zip(hosts, instances):
            if not isinstance(instance, dict):
                raise ProviderError("CCM instances_data entry for %s is invalid" % hostname)
            mapped[hostname] = {
                "instance_id": instance.get("instance_id"),
                "ip_address": instance.get("ip_address"),
            }
        known_ttl = str(ready.get("ttl") or ttl)
        self._write_state(str(deployment_id), known_ttl, mapped)
        inventory = self._write_inventory(mapped)
        warning = "CCM will terminate the whole deployment when %s passes." % known_ttl
        if not kwargs.get("agent"):
            print(warning, file=sys.stderr)
        return {
            "deployment_id": str(deployment_id),
            "ttl": known_ttl,
            "inventory": str(inventory),
            "warnings": [warning],
        }

    def _clear_local(self) -> None:
        state_file = self.state_dir / "state.json"
        if state_file.is_file():
            state_file.unlink()
        hosts_file = self.paths.inventory_dir / "hosts"
        if hosts_file.is_file():
            hosts_file.unlink()

    def destroy(self, extra: List[str], **kwargs: Any) -> Dict[str, Any]:
        del extra, kwargs
        recorded = self._read_state() or {}
        deployment_id = str(recorded.get("deployment_id") or "")
        if deployment_id:
            path = "%s/%s" % (
                DEPLOYMENTS_PATH,
                urllib.parse.quote(deployment_id, safe=""),
            )
            status, _payload = self._request("DELETE", path)
            if status not in {200, 202, 204, 404} and status >= 400:
                raise ProviderError("CCM API returned HTTP %s" % status)
        self._clear_local()
        return {"deployment_id": deployment_id or None, "cleared": True}

    def suspend(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self._not_implemented("suspend")

    def resume(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self._not_implemented("resume")
