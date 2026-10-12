"""Fetch the known official QAIRT Community Edition 2.45 archive, bounded.

GitHub-hosted x86 only. HTTPS from Qualcomm Software Center. No credentials,
cookies, arbitrary URL arguments, model data, SDK execution, extraction or
persistent archive upload. Network, time and disk limits are mandatory.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import signal
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

URL = ("https://softwarecenter.qualcomm.com/api/download/software/"
       "sdks/Qualcomm_AI_Runtime_Community/All/2.45.0.260326/"
       "v2.45.0.260326.zip")
MAX_BYTES = 2_900_000_000
MIN_FREE_BYTES = 5_000_000_000
MAX_SECONDS = 270
ALLOWED_DOMAINS = (
    "softwarecenter.qualcomm.com",
    "download.qualcomm.com",
)


def allowed_redirect(final_url: str) -> bool:
    obj = urlparse(final_url)
    return obj.scheme == "https" and obj.hostname in ALLOWED_DOMAINS


def free_space_enough(path: Path) -> bool:
    return shutil.disk_usage(path).free >= MIN_FREE_BYTES


def fetch_known_sdk(target: Path) -> dict[str, object]:
    base: dict[str, object] = {
        "status": "not-attempted",
        "release": "2.45.0.260326",
        "source": "qualcomm-software-center",
        "downloaded_bytes": 0,
        "archive_written": False,
        "source_host_allowed": False,
        "sdk_executed": False,
        "sdk_extracted": False,
        "production_services_changed": False,
    }
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        base["status"] = "reject-nonhost-architecture"
        return base
    if (target.exists() or target.is_symlink()
            or not target.parent.is_dir()
            or target.parent.is_symlink()):
        base["status"] = "reject-unsafe-output-target"
        return base
    if not free_space_enough(target.parent):
        base["status"] = "reject-insufficient-free-space"
        return base
    start = time.monotonic()
    # HEAD is advisory: no download happens if the official URL explicitly
    # declares a size beyond the cap or redirects outside allowlisted hosts.
    try:
        req = Request(URL, method="HEAD", headers={
            "User-Agent": "MyAI-QAIRT-245-Archive-Audit/1.0",
        })
        with urlopen(req, timeout=15) as response:
            base["source_host_allowed"] = allowed_redirect(response.geturl())
            header = response.headers.get("Content-Length")
            if not base["source_host_allowed"]:
                base["status"] = "reject-external-download-redirect"
                return base
            if header and header.isdigit() and int(header) > MAX_BYTES:
                base["status"] = "reject-oversize-content-length"
                return base
    except (HTTPError, URLError, OSError, TimeoutError) as err:
        base["status"] = "official-head-unavailable-" + type(err).__name__
        return base

    try:
        req = Request(URL, headers={
            "User-Agent": "MyAI-QAIRT-245-Archive-Audit/1.0",
        })
        with urlopen(req, timeout=30) as response:
            if not allowed_redirect(response.geturl()):
                base["status"] = "reject-external-download-redirect"
                return base
            if "html" in response.headers.get("Content-Type", "").lower():
                base["status"] = "reject-html-instead-of-sdk-archive"
                return base
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                base["status"] = "reject-oversize-content-length"
                return base
            with target.open("xb") as output:
                total = 0
                while True:
                    if time.monotonic() - start > MAX_SECONDS:
                        raise TimeoutError("download-time-limit")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("archive-download-size-limit")
                    output.write(chunk)
                base["downloaded_bytes"] = total
                if total < 1000:
                    raise ValueError("archive-download-too-small")
        base["status"] = "downloaded-for-metadata-audit"
        base["archive_written"] = True
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as err:
        base["status"] = "official-download-unavailable-" + type(err).__name__
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = fetch_known_sdk(args.output)
    print("QAIRT 2.45 download preflight:", json.dumps(result, sort_keys=True))
    return 0 if result["archive_written"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
