"""Splunkbase HTTP for spa apps (search / app info / download).

Never log or return Splunkbase passwords. Callers report credentials as
set / not set only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple
from xml.etree import ElementTree

API_ROOT = "https://splunkbase.splunk.com/api/v1"
LOGIN_URL = "https://splunkbase.splunk.com/api/account:login"
DEFAULT_TIMEOUT = 60
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024

_ID_IN_XML = re.compile(r"<id>([^<]+)</id>", re.IGNORECASE)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward a Splunkbase token across origins or an HTTPS downgrade."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlparse(req.full_url)
        new = urllib.parse.urlparse(newurl)
        if old.scheme == "https" and new.scheme != "https":
            return None
        redirected = super().redirect_request(
            req, fp, code, msg, headers, newurl
        )
        if redirected is None:
            return None
        old_origin = (old.scheme.lower(), (old.hostname or "").lower(), old.port)
        new_origin = (new.scheme.lower(), (new.hostname or "").lower(), new.port)
        if old_origin != new_origin:
            redirected.remove_header("X-Auth-Token")
            redirected.remove_header("Authorization")
        return redirected


class SplunkbaseError(RuntimeError):
    """HTTP or payload failure. Message must not contain secrets."""


class SplunkbaseClient(Protocol):
    def get(
        self, url: str, headers: Optional[Mapping[str, str]] = None
    ) -> Tuple[int, str]: ...

    def post_form(
        self, url: str, fields: Mapping[str, str], headers: Optional[Mapping[str, str]] = None
    ) -> Tuple[int, str]: ...

    def get_bytes(
        self, url: str, headers: Optional[Mapping[str, str]] = None
    ) -> Tuple[int, bytes]: ...

    def download_to(
        self,
        url: str,
        dest: Any,
        headers: Optional[Mapping[str, str]] = None,
    ) -> int: ...


class UrllibSplunkbaseClient:
    """Default client. Does not attach Splunkbase credentials to GET search/info."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        ctx = ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            _SafeRedirectHandler(),
            urllib.request.HTTPSHandler(context=ctx),
        )

    def _request(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        method: Optional[str] = None,
    ) -> Tuple[int, bytes]:
        hdrs = {"User-Agent": "spa-apps"}
        if headers:
            hdrs.update({k: v for k, v in headers.items() if k.lower() != "authorization"})
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                return int(getattr(resp, "status", 200) or 200), resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() or b""
            return int(exc.code), body
        except urllib.error.URLError as exc:
            raise SplunkbaseError("Splunkbase request failed") from exc

    def get(self, url: str, headers: Optional[Mapping[str, str]] = None) -> Tuple[int, str]:
        status, raw = self._request(url, headers=headers)
        return status, raw.decode("utf-8", errors="replace")

    def post_form(
        self, url: str, fields: Mapping[str, str], headers: Optional[Mapping[str, str]] = None
    ) -> Tuple[int, str]:
        payload = urllib.parse.urlencode(fields).encode("utf-8")
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            hdrs.update(headers)
        status, raw = self._request(url, data=payload, headers=hdrs, method="POST")
        return status, raw.decode("utf-8", errors="replace")

    def get_bytes(
        self, url: str, headers: Optional[Mapping[str, str]] = None
    ) -> Tuple[int, bytes]:
        return self._request(url, headers=headers)

    def download_to(
        self,
        url: str,
        dest: Any,
        headers: Optional[Mapping[str, str]] = None,
    ) -> int:
        """Stream a bounded response to disk without retaining the archive."""
        hdrs = {"User-Agent": "spa-apps"}
        if headers:
            hdrs.update(
                {
                    key: value
                    for key, value in headers.items()
                    if key.lower() != "authorization"
                }
            )
        request = urllib.request.Request(url, headers=hdrs)
        path = Path(dest)
        partial: Optional[Path] = None
        total = 0
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200) or 200)
                if status != 200:
                    return status
                fd, partial_name = tempfile.mkstemp(
                    prefix=".%s." % path.name,
                    suffix=".part",
                    dir=str(path.parent),
                )
                partial = Path(partial_name)
                with os.fdopen(fd, "wb") as stream:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise SplunkbaseError(
                                "Splunkbase archive exceeds maximum download size"
                            )
                        stream.write(chunk)
            partial.replace(path)
            return 200
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except urllib.error.URLError as exc:
            raise SplunkbaseError("Splunkbase request failed") from exc
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)


ENV_USERNAME = "SPLUNKBASE_USERNAME"
ENV_PASSWORD = "SPLUNKBASE_PASSWORD"

# splunk_config.yml usually stores lookup('env', 'NAME'); Ansible renders it at
# deploy time, so spa resolves that one lookup itself. Vault refs stay opaque.
_ENV_LOOKUP = re.compile(
    r"""lookup\(\s*['"]env['"]\s*,\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s*\)"""
)


def _config_credentials(config: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    if not isinstance(config, Mapping):
        return {}
    section = config.get("splunk_app_deployment")
    if not isinstance(section, Mapping):
        section = config
    out = {}
    for key in ("splunkbase_username", "splunkbase_password"):
        raw = section.get(key)
        value = "" if raw is None else str(raw).strip()
        if not value:
            continue
        if "{{" in value:
            match = _ENV_LOOKUP.search(value)
            if not match:
                continue
            value = (os.environ.get(match.group(1)) or "").strip()
            if not value:
                continue
        out[key] = value
    return out


def _resolve_creds(config: Optional[Mapping[str, Any]] = None) -> Tuple[str, str]:
    """splunk_config.yml wins over the plain environment variables."""
    from_config = _config_credentials(config)
    user = from_config.get("splunkbase_username") or (
        os.environ.get(ENV_USERNAME) or ""
    ).strip()
    password = from_config.get("splunkbase_password") or (
        os.environ.get(ENV_PASSWORD) or ""
    ).strip()
    return user, password


def credentials_present(config: Optional[Mapping[str, Any]] = None) -> Tuple[bool, bool]:
    """Return (username_set, password_set) without exposing values."""
    user, password = _resolve_creds(config)
    return bool(user), bool(password)


def _require_creds(config: Optional[Mapping[str, Any]] = None) -> Tuple[str, str]:
    user, password = _resolve_creds(config)
    missing = []
    if not user:
        missing.append("%s: not set" % ENV_USERNAME)
    if not password:
        missing.append("%s: not set" % ENV_PASSWORD)
    if missing:
        raise SplunkbaseError(
            "%s (set the env vars, or splunk_app_deployment.splunkbase_username / "
            "splunkbase_password in splunk_config.yml)" % "; ".join(missing)
        )
    return user, password


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SplunkbaseError("Splunkbase returned invalid JSON") from exc


def _as_app_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "objects", "items", "apps"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise SplunkbaseError("Splunkbase search payload was not a list of apps")


def search_apps(
    query: str,
    *,
    limit: int = 10,
    client: Optional[SplunkbaseClient] = None,
) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        raise SplunkbaseError("spa apps search QUERY")
    if limit < 1:
        raise SplunkbaseError("spa apps search --limit must be at least 1")
    http = client or UrllibSplunkbaseClient()
    # include=release is the only way the list endpoint returns a version;
    # callers project it down to the latest version string.
    params = urllib.parse.urlencode(
        {
            "query": q,
            "order": "relevance",
            "limit": str(limit),
            "offset": "0",
            "include": "release",
        }
    )
    url = "%s/app/?%s" % (API_ROOT, params)
    status, text = http.get(url)
    if status != 200:
        raise SplunkbaseError("Splunkbase search failed (HTTP %s)" % status)
    return _as_app_list(_load_json(text))


def get_app(
    app_id: int,
    *,
    client: Optional[SplunkbaseClient] = None,
) -> Dict[str, Any]:
    http = client or UrllibSplunkbaseClient()
    url = "%s/app/%s/?include=release,releases" % (API_ROOT, app_id)
    status, text = http.get(url)
    if status == 404:
        raise SplunkbaseError("Unknown Splunkbase app_id: %s" % app_id)
    if status != 200:
        raise SplunkbaseError("Splunkbase app lookup failed (HTTP %s)" % status)
    data = _load_json(text)
    if not isinstance(data, dict):
        raise SplunkbaseError("Splunkbase app payload was not an object")
    return data


def _login_token(
    client: SplunkbaseClient, config: Optional[Mapping[str, Any]] = None
) -> str:
    user, password = _require_creds(config)
    status, text = client.post_form(LOGIN_URL, {"username": user, "password": password})
    if status != 200:
        raise SplunkbaseError("Splunkbase login failed (HTTP %s)" % status)
    match = _ID_IN_XML.search(text)
    if match:
        token = match.group(1).strip()
        if token:
            return token
    try:
        root = ElementTree.fromstring(text)
        for elem in root.iter():
            if (elem.tag or "").lower().endswith("id") and (elem.text or "").strip():
                return elem.text.strip()
    except ElementTree.ParseError:
        pass
    raise SplunkbaseError("Splunkbase login failed")


def download_release(
    release_url: str,
    dest: Any,
    *,
    client: Optional[SplunkbaseClient] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> None:
    """Write the release archive to dest (path-like). Token is not logged."""
    http = client or UrllibSplunkbaseClient()
    token = _login_token(http, config)
    headers = {"X-Auth-Token": token}
    if hasattr(http, "download_to"):
        status = http.download_to(release_url, dest, headers=headers)
        if status != 200:
            raise SplunkbaseError("Splunkbase download failed (HTTP %s)" % status)
        return
    status, raw = http.get_bytes(release_url, headers=headers)
    if status != 200:
        raise SplunkbaseError("Splunkbase download failed (HTTP %s)" % status)
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise SplunkbaseError("Splunkbase archive exceeds maximum download size")
    path = dest if hasattr(dest, "write_bytes") else None
    if path is not None:
        dest.write_bytes(raw)
        return
    from pathlib import Path

    Path(dest).write_bytes(raw)
