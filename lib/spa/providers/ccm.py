"""Corporate Cloud Manager (CCM) EC2 lifecycle.

Auth is the process environment variable CCM_TOKEN only. Never print the PAT.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple

from spa.paths import SpaPaths
from spa.providers import ProviderError, ProvisionState

TOKEN_ENV = "CCM_TOKEN"
API_ROOT = "https://api.ccm.splunkits.io"
DEFAULT_TIMEOUT = 30
DEPLOYMENTS_PATH = "/api/v1/deployments"


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

    def request(self, method: str, path: str) -> Tuple[int, Any]:
        url = self._url(path)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "spa",
                "Authorization": "Bearer %s" % self._token,
                "Accept": "application/json",
            },
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


class Provider:
    name = "ccm"

    def __init__(self, paths: SpaPaths, config: Dict[str, Any]):
        self.paths = paths
        # Slice 3 reads these from the ccm: block (not hardcoded here):
        # operating_system, instance_type, disk_storage, key_name (API ssh_key_name),
        # ssh_private_key_file, ssh_username.
        self.config = config
        self.state_dir = paths.spa_env_dir / "ccm"

    def provision_state(self) -> ProvisionState:
        state_file = self.state_dir / "state.json"
        if not state_file.is_file():
            return ProvisionState(
                provider=self.name,
                provisioned=False,
                reason="No CCM state for this env: %s" % self.state_dir,
                hint="spa provision --yes",
            )
        return ProvisionState(provider=self.name, provisioned=True)

    def _not_implemented(self, action: str) -> None:
        raise ProviderError("CCM %s is not implemented yet." % action)

    def provision(self, extra: List[str], **kwargs: Any) -> int:
        del extra, kwargs
        self._not_implemented("provision")

    def destroy(self, extra: List[str], **kwargs: Any) -> int:
        del extra, kwargs
        self._not_implemented("destroy")

    def suspend(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self._not_implemented("suspend")

    def resume(self, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self._not_implemented("resume")
