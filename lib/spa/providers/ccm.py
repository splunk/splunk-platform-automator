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
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, NoReturn, Optional, Sequence, Tuple

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
META_PATH = "/api/v1/meta"
SSH_KEYS_PATH = "/ssh_keys/"
MAX_INSTANCES = 50
ACCOUNT_INSTANCE_CAP = 100
NAME_MIN = 5
NAME_MAX = 100
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][\w-]*[a-zA-Z0-9]$")
DEFAULT_TTL_DAYS = 7
DEFAULT_DISK_STORAGE = 50
DEFAULT_TIMEZONE = "UTC"
DEFAULT_OPERATION_HOURS = "manual"
DEFAULT_BUSINESS_PURPOSE = "DeveloperInstance"
DEFAULT_SSH_USERNAME = "splunker"
DEFAULT_SSH_KEY_FILE = "~/.ssh/CCM-Key.pem"
POLL_INTERVAL = 5
POLL_ATTEMPTS = 180
TTL_MAX_DAYS = 30
BUSINESS_PURPOSES = ("DeveloperInstance", "SalesOpportunity", "SupportCase")
OPERATION_HOURS = ("manual", "business_hours")
META_ATTRIBUTES = ("operating_systems", "instance_types", "disk_storage")
PROVIDER_NEEDS_ACTION = (
    "spa provider needs an action.\n"
    "CCM: spa provider ccm check-auth"
)
PROVIDER_CCM_NEEDS_ACTION = (
    "spa provider ccm needs an action.\n"
    "spa provider ccm check-auth.\n"
    "spa provider ccm survey\n"
    "spa provider ccm operating-systems list\n"
    "spa provider ccm instance-types list\n"
    "spa provider ccm disk-storage list\n"
    "spa provider ccm business-purposes list\n"
    "spa provider ccm operation-hours list\n"
    "spa provider ccm ssh-keys list\n"
    "spa provider ccm ttl extend --days N --yes\n"
    "spa provider ccm operation-hours set manual|business_hours --yes"
)


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


def _top_level_has_ccm(text: str) -> bool:
    for raw in text.splitlines():
        line = raw.split("#", 1)[0]
        if not line.strip() or line[:1].isspace():
            continue
        if line.split(":", 1)[0].strip() == "ccm":
            return True
    return False


def audience_visible(
    environ: Optional[Mapping[str, str]] = None,
    config: Optional[Mapping[str, Any]] = None,
    paths: Optional[SpaPaths] = None,
) -> bool:
    """True when human help/completion should name spa provider (CCM)."""
    if token_present(environ):
        return True
    if isinstance(config, dict) and isinstance(config.get("ccm"), dict):
        return True
    if paths is None:
        return False
    cfg = Path(paths.config_file)
    if not cfg.is_file():
        return False
    try:
        return _top_level_has_ccm(cfg.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False


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

    def _expired_error(self, deployment_id: str) -> NoReturn:
        state = self._expired_state(deployment_id)
        raise ProviderError("%s. Run: %s" % (state.reason, state.hint))

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
                self._expired_error(deployment_id)
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

    def _write_inventory(
        self, hosts: Mapping[str, Mapping[str, Any]], merge: bool = False
    ) -> Any:
        user = self.config.get("ssh_username") or DEFAULT_SSH_USERNAME
        key = self.config.get("ssh_private_key_file") or DEFAULT_SSH_KEY_FILE
        destination = self.paths.inventory_dir / "hosts"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and not merge:
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

    def _instance_path(self, deployment_id: str, instance_id: str) -> str:
        return "%s/%s/instances/%s" % (
            DEPLOYMENTS_PATH,
            urllib.parse.quote(deployment_id, safe=""),
            urllib.parse.quote(instance_id, safe=""),
        )

    def _require_state(self) -> Dict[str, Any]:
        recorded = self._read_state() or {}
        deployment_id = str(recorded.get("deployment_id") or "")
        if not deployment_id:
            raise ProviderError(
                "No CCM state for this env: %s" % self.state_dir,
                code=1,
            )
        return recorded

    def _selected_hosts(
        self, recorded: Mapping[str, Any], hosts: Optional[List[str]] = None
    ) -> Dict[str, Mapping[str, Any]]:
        mapping = recorded.get("hosts") or {}
        if not isinstance(mapping, dict):
            mapping = {}
        if not hosts:
            return {
                name: row
                for name, row in mapping.items()
                if isinstance(row, dict)
            }
        missing = [name for name in hosts if name not in mapping]
        if missing:
            raise ProviderError(
                "No CCM instance for: %s. Known: %s"
                % (", ".join(missing), ", ".join(sorted(mapping)))
            )
        return {name: mapping[name] for name in hosts if isinstance(mapping[name], dict)}

    def _patch_instances(
        self,
        deployment_id: str,
        selected: Mapping[str, Mapping[str, Any]],
        desired_state: str,
        deployment: Optional[Mapping[str, Any]] = None,
    ) -> None:
        current: Dict[str, str] = {}
        for row in (deployment or {}).get("instances_data") or []:
            if isinstance(row, dict) and row.get("instance_id"):
                current[str(row["instance_id"])] = str(row.get("state") or "").lower()
        wanted = desired_state.lower()
        for name, row in selected.items():
            instance_id = str((row or {}).get("instance_id") or "")
            if not instance_id:
                raise ProviderError("CCM state has no instance_id for %s" % name)
            if current.get(instance_id) == wanted:
                continue
            status, _payload = self._request(
                "PATCH",
                self._instance_path(deployment_id, instance_id),
                body={"desired_state": desired_state},
            )
            if status == 404:
                self._expired_error(deployment_id)
            if status >= 400:
                raise ProviderError("CCM API returned HTTP %s" % status)

    def host_status(self) -> Dict[str, Dict[str, Any]]:
        recorded = self._read_state() or {}
        deployment_id = str(recorded.get("deployment_id") or "")
        if not deployment_id:
            return {}
        mapping = recorded.get("hosts") or {}
        if not isinstance(mapping, dict):
            mapping = {}
        deployment = self._get_deployment(deployment_id)
        instances: Dict[str, Dict[str, Any]] = {}
        for row in deployment.get("instances_data") or []:
            if isinstance(row, dict) and row.get("instance_id"):
                instances[str(row["instance_id"])] = row
        status: Dict[str, Dict[str, Any]] = {}
        for name, row in mapping.items():
            if not isinstance(row, dict):
                continue
            instance_id = str(row.get("instance_id") or "")
            instance = instances.get(instance_id) or {}
            state = instance.get("state")
            record = {
                "state": state,
                "reachable": str(state or "").lower() == "running",
                "instance_id": instance.get("instance_id") or instance_id,
            }
            ttl = deployment.get("ttl")
            if ttl:
                record["ttl"] = ttl
            for identifier in (name, record["instance_id"], instance.get("ip_address")):
                if identifier:
                    status[str(identifier)] = record
        return status

    def suspend(self, **kwargs: Any) -> Dict[str, Any]:
        hosts = kwargs.get("hosts")
        recorded = self._require_state()
        deployment_id = str(recorded["deployment_id"])
        selected = self._selected_hosts(recorded, hosts)
        deployment = self._get_deployment(deployment_id)
        self._patch_instances(deployment_id, selected, "stopped", deployment)
        return {
            "provider": self.name,
            "action": "suspend",
            "deployment_id": deployment_id,
        }

    def _get_deployment(self, deployment_id: str) -> Dict[str, Any]:
        path = "%s/%s" % (
            DEPLOYMENTS_PATH,
            urllib.parse.quote(deployment_id, safe=""),
        )
        status, payload = self._request("GET", path)
        if status == 404:
            self._expired_error(deployment_id)
        if status >= 400:
            raise ProviderError("CCM API returned HTTP %s" % status)
        data = _unwrap(payload) or {}
        if not isinstance(data, dict) or not data:
            self._expired_error(deployment_id)
        return data

    def _map_instances(
        self,
        selected: Mapping[str, Mapping[str, Any]],
        deployment: Mapping[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        instances: Dict[str, Dict[str, Any]] = {}
        for row in deployment.get("instances_data") or []:
            if isinstance(row, dict) and row.get("instance_id"):
                instances[str(row["instance_id"])] = row
        mapped: Dict[str, Dict[str, Any]] = {}
        for name, row in selected.items():
            instance_id = str((row or {}).get("instance_id") or "")
            instance = instances.get(instance_id) or {}
            mapped[name] = {
                "instance_id": instance_id,
                "ip_address": instance.get("ip_address"),
            }
        return mapped

    def resume(self, **kwargs: Any) -> Dict[str, Any]:
        hosts = kwargs.get("hosts")
        recorded = self._require_state()
        deployment_id = str(recorded["deployment_id"])
        selected = self._selected_hosts(recorded, hosts)
        deployment = self._get_deployment(deployment_id)
        self._patch_instances(deployment_id, selected, "running", deployment)
        deployment = self._get_deployment(deployment_id)
        mapped = self._map_instances(selected, deployment)
        inventory = self._write_inventory(mapped, merge=bool(hosts))
        warnings: List[str] = []
        if str(self.config.get("operation_hours") or "") == "business_hours":
            warning = (
                "ccm.operation_hours is business_hours; CCM may stop instances "
                "again outside the window."
            )
            warnings.append(warning)
            if not kwargs.get("agent"):
                print(warning, file=sys.stderr)
        result = {
            "provider": self.name,
            "action": "resume",
            "deployment_id": deployment_id,
            "inventory": str(inventory),
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def _deployment_path(self, deployment_id: str) -> str:
        return "%s/%s" % (
            DEPLOYMENTS_PATH,
            urllib.parse.quote(deployment_id, safe=""),
        )

    def patch_deployment(self, body: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        recorded = self._require_state()
        deployment_id = str(recorded["deployment_id"])
        status, payload = self._request(
            "PATCH",
            self._deployment_path(deployment_id),
            body=dict(body),
        )
        if status == 404:
            self._expired_error(deployment_id)
        if status >= 400:
            raise ProviderError("CCM API returned HTTP %s" % status)
        data = _unwrap(payload) or {}
        if not isinstance(data, dict):
            data = {}
        return recorded, data

    def extend_ttl(self, days: int, when: Optional[datetime] = None) -> Dict[str, Any]:
        stamp = _ttl_stamp(when or self._now(), days)
        timezone = str(self.config.get("timezone") or DEFAULT_TIMEZONE)
        recorded, data = self.patch_deployment({"ttl": stamp, "timezone": timezone})
        known = str(data.get("ttl") or stamp)
        hosts = recorded.get("hosts") if isinstance(recorded.get("hosts"), dict) else {}
        self._write_state(str(recorded["deployment_id"]), known, hosts)
        return {
            "deployment_id": str(recorded["deployment_id"]),
            "ttl": known,
        }

    def set_operation_hours(self, hours: str) -> Dict[str, Any]:
        timezone = str(self.config.get("timezone") or DEFAULT_TIMEZONE)
        self.patch_deployment({"operation_hours": hours, "timezone": timezone})
        return {"operation_hours": hours, "timezone": timezone}


_META_ACTIONS = {
    "operating-systems": "operating_systems",
    "instance-types": "instance_types",
    "disk-storage": "disk_storage",
}
EBS_SIZES = (50, 100, 300)


def _named_catalog(names: Sequence[Any]) -> Dict[str, Any]:
    return {"items": [{"name": name} for name in names]}


def _meta_rows(payload: Any, attribute: str) -> List[Any]:
    data = _unwrap(payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = data.get(attribute)
        if isinstance(nested, list):
            return nested
    return []


def _meta_items(payload: Any, attribute: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in _meta_rows(payload, attribute):
        if isinstance(row, dict):
            name = row.get("name", row.get("value"))
            items.append({"name": name})
        else:
            items.append({"name": row})
    return items


def _ccm_item_line(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    if item.get("fingerprint") or item.get("local_private_key"):
        parts = [item.get("name"), item.get("fingerprint"), item.get("local_private_key")]
        return "  ".join(str(part) for part in parts if part is not None and part != "")
    if "name" in item:
        return str(item["name"])
    return "  ".join(
        "%s=%s" % (key, value)
        for key, value in item.items()
        if value is not None and key != "public_key"
    )


def format_ccm_text(data: Any) -> str:
    """Human stdout for spa provider ccm. JSON mode does not call this."""
    if not isinstance(data, dict):
        return str(data) + "\n"
    lines: List[str] = []
    if data.get("ccm_token"):
        lines.append("CCM_TOKEN: %s" % data["ccm_token"])
    items = data.get("items")
    if isinstance(items, list):
        if not items:
            lines.append("No results.")
        for item in items:
            lines.append(_ccm_item_line(item))
    for label, key in (
        ("Operating systems", "operating_systems"),
        ("Instance types", "instance_types"),
        ("Disk storage", "disk_storage"),
        ("Business purposes", "business_purposes"),
        ("Operation hours", "operation_hours"),
    ):
        nested = data.get(key)
        if not isinstance(nested, dict):
            continue
        lines.append("%s:" % label)
        nested_items = nested.get("items") or []
        if not nested_items:
            lines.append("  No results.")
        for entry in nested_items:
            lines.append("  %s" % _ccm_item_line(entry))
    if data.get("ttl"):
        lines.append("ttl: %s" % data["ttl"])
    hours = data.get("operation_hours")
    if hours and not isinstance(hours, dict):
        lines.append("operation_hours: %s" % hours)
    for warning in data.get("warnings") or []:
        lines.append("Warning: %s" % warning)
    if not lines:
        lines.append("ok" if data.get("ok", True) else "failed")
    return "\n".join(lines) + "\n"


def _private_key_path(config: Mapping[str, Any]) -> Path:
    raw = str(config.get("ssh_private_key_file") or DEFAULT_SSH_KEY_FILE)
    return Path(raw).expanduser()


def _instance_count(payload: Any) -> int:
    data = _unwrap(payload)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        nested = data.get("deployments") or data.get("items") or []
        rows = nested if isinstance(nested, list) else []
    else:
        rows = []
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        instances = row.get("instances_data")
        if isinstance(instances, list):
            total += len(instances)
    return total


def _ssh_key_names(payload: Any) -> List[str]:
    data = _unwrap(payload)
    rows = data if isinstance(data, list) else []
    names: List[str] = []
    for row in rows:
        if isinstance(row, dict) and row.get("pub_key_name"):
            names.append(str(row["pub_key_name"]))
        elif isinstance(row, dict) and row.get("name"):
            names.append(str(row["name"]))
    return names


def _ssh_key_items(payload: Any, config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    data = _unwrap(payload)
    rows = data if isinstance(data, list) else []
    local = "yes" if _private_key_path(config).is_file() else "no"
    items: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "name": row.get("pub_key_name") or row.get("name"),
                "fingerprint": row.get("fingerprint"),
                "local_private_key": local,
            }
        )
    return items


def _fail(error: str, code: int = 1) -> Any:
    from spa.api import CommandResult

    return CommandResult(ok=False, error=error, code=code)


def _confirm(label: str, confirm: bool, agent: bool) -> Optional[Any]:
    from spa.confirm import ConfirmationError, ConfirmationUsageError, ensure_confirmed

    try:
        ensure_confirmed(label, confirm=confirm, agent=agent, risk="mutating")
    except ConfirmationUsageError as exc:
        return _fail(str(exc), 2)
    except ConfirmationError as exc:
        return _fail(str(exc), 1)
    return None


def _require_client(client: Optional[UrllibCcmClient]) -> UrllibCcmClient:
    return client or UrllibCcmClient.from_env()


def _meta_catalog(http: UrllibCcmClient, attribute: str) -> Dict[str, Any]:
    status, payload = http.request("GET", META_PATH, query={"attribute": attribute})
    if status >= 400:
        raise CcmError("CCM API returned HTTP %s" % status)
    return {"items": _meta_items(payload, attribute)}


def _provider(
    paths: Optional[SpaPaths],
    config: Optional[Mapping[str, Any]],
    client: Optional[UrllibCcmClient],
    now: Optional[Any] = None,
) -> Provider:
    if paths is None:
        from spa.paths import resolve_spa_paths

        paths = resolve_spa_paths()
    kwargs: Dict[str, Any] = {}
    if now is not None:
        kwargs["now"] = now if callable(now) else (lambda: now)
    return Provider(paths, dict(config or {}), client=client, **kwargs)


def validate_ccm(
    paths: SpaPaths,
    config: Mapping[str, Any],
    client: Optional[UrllibCcmClient] = None,
) -> Any:
    """Local CCM checks, plus live account/key checks when a token or client is present."""
    from spa.api import CommandResult

    hosts = expected_hostnames(load_deployment_config(paths))
    if len(hosts) > MAX_INSTANCES:
        return _fail(
            "This env has %s hosts; CCM accepts at most %s instances in one create."
            % (len(hosts), MAX_INSTANCES),
            2,
        )
    ttl_days = config.get("ttl_days")
    if ttl_days is not None:
        try:
            ttl_value = int(ttl_days)
        except (TypeError, ValueError):
            ttl_value = -1
        if ttl_value < 1 or ttl_value > TTL_MAX_DAYS:
            return _fail(
                "ccm.ttl_days must be 1–%s, got %s." % (TTL_MAX_DAYS, ttl_days),
                2,
            )
    ebs = config.get("ebs_storage")
    if isinstance(ebs, dict):
        count = ebs.get("ebs_count")
        size = ebs.get("ebs_size")
        if count is not None:
            try:
                count_value = int(count)
            except (TypeError, ValueError):
                count_value = -1
            if count_value < 1 or count_value > 3:
                return _fail("ccm.ebs_storage.ebs_count must be 1–3, got %s." % count, 2)
        if size is not None:
            try:
                size_value = int(size)
            except (TypeError, ValueError):
                size_value = -1
            if size_value not in EBS_SIZES:
                return _fail(
                    "ccm.ebs_storage.ebs_size must be one of %s, got %s."
                    % (", ".join(str(item) for item in EBS_SIZES), size),
                    2,
                )
    key_file = _private_key_path(config)
    if not key_file.is_file():
        return _fail("ccm.ssh_private_key_file is missing: %s" % key_file, 1)

    if client is None and not token_present():
        return CommandResult(ok=True, data={"ok": True})

    problems: List[str] = []
    try:
        http = _require_client(client)
        status, deployments = http.request("GET", DEPLOYMENTS_PATH)
        if status >= 400:
            raise CcmError("CCM API returned HTTP %s" % status)
        current = _instance_count(deployments)
        if current + len(hosts) > ACCOUNT_INSTANCE_CAP:
            problems.append(
                "This env has %s hosts; the account already has %s instances; "
                "CCM allows at most %s total."
                % (len(hosts), current, ACCOUNT_INSTANCE_CAP)
            )
        status, keys = http.request("GET", SSH_KEYS_PATH)
        if status >= 400:
            raise CcmError("CCM API returned HTTP %s" % status)
        key_name = str(config.get("key_name") or "").strip()
        names = _ssh_key_names(keys)
        if key_name and key_name not in names:
            problems.append("ccm.key_name %r is not in the CCM SSH key list." % key_name)
    except CcmError as exc:
        return _fail(str(exc), 1)
    if problems:
        return _fail(" ".join(problems), 1)
    return CommandResult(ok=True, data={"ok": True})


def execute(
    *,
    action: str,
    resource: Optional[str] = None,
    subaction: Optional[str] = None,
    hours: Optional[str] = None,
    days: Optional[int] = None,
    confirm: bool = False,
    agent: bool = False,
    paths: Optional[SpaPaths] = None,
    config: Optional[Mapping[str, Any]] = None,
    client: Optional[UrllibCcmClient] = None,
    now: Optional[Any] = None,
) -> Any:
    """Run one spa provider ccm action. Discovery does not need a provisioned env."""
    from spa.api import CommandResult
    from spa.providers import ProviderError

    del resource
    if not action:
        return CommandResult(ok=False, error=PROVIDER_CCM_NEEDS_ACTION, code=2)
    cfg = dict(config or {})

    try:
        if action == "check-auth":
            if client is None and not token_present():
                return _fail("%s is not set" % TOKEN_ENV, 1)
            ping(client=_require_client(client))
            return CommandResult(ok=True, data={"ccm_token": "set"})

        if action == "business-purposes" and subaction in (None, "list"):
            return CommandResult(ok=True, data=_named_catalog(BUSINESS_PURPOSES))

        if action == "operation-hours" and subaction in (None, "list"):
            return CommandResult(ok=True, data=_named_catalog(OPERATION_HOURS))

        if action == "survey":
            http = _require_client(client)
            data: Dict[str, Any] = {}
            for attribute in META_ATTRIBUTES:
                data[attribute] = _meta_catalog(http, attribute)
            data["business_purposes"] = _named_catalog(BUSINESS_PURPOSES)
            data["operation_hours"] = _named_catalog(OPERATION_HOURS)
            return CommandResult(ok=True, data=data)

        if action in _META_ACTIONS and subaction in (None, "list"):
            http = _require_client(client)
            return CommandResult(
                ok=True,
                data=_meta_catalog(http, _META_ACTIONS[action]),
            )

        if action == "ssh-keys" and subaction in (None, "list"):
            http = _require_client(client)
            status, payload = http.request("GET", SSH_KEYS_PATH)
            if status >= 400:
                raise CcmError("CCM API returned HTTP %s" % status)
            return CommandResult(ok=True, data={"items": _ssh_key_items(payload, cfg)})

        if action == "ttl" and subaction == "extend":
            blocked = _confirm("spa provider ccm ttl extend", confirm, agent)
            if blocked is not None:
                return blocked
            if days is None:
                return _fail(
                    "--days must be 1–%s for spa provider ccm ttl extend." % TTL_MAX_DAYS,
                    2,
                )
            try:
                day_count = int(days)
            except (TypeError, ValueError):
                day_count = -1
            if day_count < 1 or day_count > TTL_MAX_DAYS:
                return _fail(
                    "--days must be 1–%s for spa provider ccm ttl extend." % TTL_MAX_DAYS,
                    2,
                )
            when = now() if callable(now) else now
            data = _provider(paths, cfg, client, now=when).extend_ttl(day_count, when)
            return CommandResult(ok=True, data=data)

        if action == "operation-hours" and subaction == "set":
            blocked = _confirm("spa provider ccm operation-hours set", confirm, agent)
            if blocked is not None:
                return blocked
            if hours not in OPERATION_HOURS:
                return _fail(
                    "Hours must be %s for spa provider ccm operation-hours set."
                    % " or ".join(OPERATION_HOURS),
                    2,
                )
            data = _provider(paths, cfg, client).set_operation_hours(str(hours))
            return CommandResult(ok=True, data=data)
    except CcmError as exc:
        message = str(exc)
        if message == "%s: not set" % TOKEN_ENV:
            message = "%s is not set" % TOKEN_ENV
        return _fail(message, 1)
    except ProviderError as exc:
        return _fail(str(exc), exc.code or 1)

    return CommandResult(ok=False, error=PROVIDER_CCM_NEEDS_ACTION, code=2)
