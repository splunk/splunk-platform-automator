"""Test-only Splunkbase HTTP stub. Active when SPA_TEST_SPLUNKBASE_STUB=1."""

import json
import os
import re

if os.environ.get("SPA_TEST_SPLUNKBASE_STUB") == "1":
    from spa.splunkbase import UrllibSplunkbaseClient

    _APPS = {
        1841: {
            "uid": 1841,
            "appid": "itsi",
            "title": "Splunk IT Service Intelligence",
            "type": "app",
            "release": {"title": "4.21.0", "path": "https://example.invalid/1841"},
        },
        5391: {
            "uid": 5391,
            "appid": "DA-ITSI-ContentLibrary",
            "title": "Splunk Content Pack for ITSI Content Library",
            "type": "app",
            "release": {"title": "2.0.0", "path": "https://example.invalid/5391"},
        },
        833: {
            "uid": 833,
            "appid": "Splunk_TA_nix",
            "title": "Splunk Add-on for Unix and Linux",
            "type": "addon",
            "release": {"title": "10.3.4", "path": "https://example.invalid/833"},
        },
        1621: {
            "uid": 1621,
            "appid": "Splunk_SA_CIM",
            "title": "Splunk Common Information Model (CIM)",
            "type": "app",
            "release": {"title": "6.2.0", "path": "https://example.invalid/1621"},
        },
        2882: {
            "uid": 2882,
            "appid": "Splunk_SA_Scientific_Python_linux_x86_64",
            "title": "Python for Scientific Computing",
            "type": "app",
            "release": {"title": "4.2.0", "path": "https://example.invalid/2882"},
        },
        2890: {
            "uid": 2890,
            "appid": "Splunk_ML_Toolkit",
            "title": "Splunk Machine Learning Toolkit",
            "type": "app",
            "release": {"title": "5.6.0", "path": "https://example.invalid/2890"},
        },
    }

    def _get(self, url, headers=None):
        match = re.search(r"/app/(\d+)/", url)
        if match:
            app = _APPS.get(int(match.group(1)))
            if app is None:
                return 404, "{}"
            return 200, json.dumps(app)
        query_match = re.search(r"[?&]query=([^&]*)", url)
        if query_match is None:
            return 404, "{}"
        from urllib.parse import unquote_plus

        query = unquote_plus(query_match.group(1)).lower()
        terms = [term for term in re.split(r"\s+", query) if term]
        hits = []
        for app in _APPS.values():
            blob = " ".join(
                [
                    str(app.get("uid") or ""),
                    str(app.get("appid") or ""),
                    str(app.get("title") or ""),
                ]
            ).lower()
            if terms and all(term in blob for term in terms):
                hits.append(app)
        return 200, json.dumps({"results": hits})

    UrllibSplunkbaseClient.get = _get
