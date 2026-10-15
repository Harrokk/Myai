"""QAIRT 2.46.0.260424 official SDK HEAD-only source probe on x86.

Official release-specific URL is pinned; no remote input may change it.
Perform only one HTTPS HEAD on a disposable hosted x86 runner. No SDK bytes
are downloaded, installed, extracted, executed or uploaded. No secrets,
cookies, user data or credentials. Redirects are verified before any
positive source-availability claim. This is NOT an HTP model build.
"""
from __future__ import annotations

import json
import platform
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SDK_RELEASE = "2.46.0.260424"
OFFICIAL_URL = (
    "https://softwarecenter.qualcomm.com/api/download/software/"
    "sdks/Qualcomm_AI_Runtime_Community/All/2.46.0.260424/"
    "v2.46.0.260424.zip"
)
ALLOWED_HOSTS = frozenset({
    "softwarecenter.qualcomm.com",
    "download.qualcomm.com",
    "apigwx-aws.qualcomm.com",
})
MAX_ARCHIVE_BYTES = 2_900_000_000
MIN_ARCHIVE_BYTES = 1000


def source_allowed(url):
    if not isinstance(url, str) or len(url) > 2048:
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_HOSTS
        and not parsed.username
        and not parsed.password
    )


def head_probe(*, machine=None, opener=urlopen):
    result = {
        "probe": "qairt_246_official_host_source_head_only",
        "status": "no_go",
        "expected_release": SDK_RELEASE,
        "official_host_reached": False,
        "source_redirect_allowlisted": False,
        "declared_size_within_cap": False,
        "declared_content_is_archive": False,
        "sdk_downloaded": False,
        "sdk_installed_or_executed": False,
        "model_converted": False,
        "npu_or_htp_executed": False,
        "ventuno_accessed": False,
    }
    if (machine if machine is not None else platform.machine()).casefold() not in {
        "x86_64", "amd64",
    }:
        result["status"] = "reject_nonhost_architecture"
        return result
    if not source_allowed(OFFICIAL_URL):
        result["status"] = "reject_nonofficial_sdk_url"
        return result
    req = Request(
        OFFICIAL_URL,
        method="HEAD",
        headers={"User-Agent": "MyAI-QAIRT246-Host-Source-Preflight/1.0"},
    )
    try:
        with opener(req, timeout=20) as response:
            target = response.geturl()
            if not source_allowed(target):
                result["status"] = "reject_untrusted_redirect"
                return result
            result["source_redirect_allowlisted"] = True
            code = response.getcode()
            result["official_host_reached"] = code == 200
            if code != 200:
                result["status"] = "no_go_official_source_unavailable"
                return result
            header = response.headers.get("Content-Length", "")
            mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
            if not isinstance(header, str) or not header.isascii() or not header.isdecimal():
                result["status"] = "no_go_size_unknown"
                return result
            count = int(header)
            result["declared_size_within_cap"] = MIN_ARCHIVE_BYTES <= count <= MAX_ARCHIVE_BYTES
            result["declared_content_is_archive"] = mime in {
                "application/zip", "application/octet-stream",
                "binary/octet-stream", "application/x-zip-compressed",
            }
            if not result["declared_size_within_cap"]:
                result["status"] = "reject_archive_size"
            elif not result["declared_content_is_archive"]:
                result["status"] = "no_go_content_type_unverified"
            else:
                result["status"] = "head_metadata_compatible_not_downloaded"
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        result["status"] = "no_go_official_head_unavailable"
    return result


if __name__ == "__main__":
    print("MYAI_QAIRT246_SDK_HEAD_JSON=" + json.dumps(head_probe(), sort_keys=True))
