"""Synthetic-only QAIRT 2.46 official SDK HEAD preflight tests."""
import json

import pytest

from scripts import qairt_246_official_host_head as source


class Response:
    def __init__(self, *, url=source.OFFICIAL_URL, status=200,
                 length="2000000000", mime="application/zip"):
        self.url, self.status = url, status
        self.headers = {"Content-Length": length, "Content-Type": mime}
    def geturl(self):
        return self.url
    def getcode(self):
        return self.status
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


def fake(response):
    calls = []
    def open_once(req, timeout):
        calls.append((req.get_method(), req.full_url, timeout))
        return response
    return open_once, calls


def test_fixed_exact_official_246_source_is_https():
    assert source.SDK_RELEASE == "2.46.0.260424"
    assert source.OFFICIAL_URL.endswith(
        "/2.46.0.260424/v2.46.0.260424.zip"
    )
    assert source.source_allowed(source.OFFICIAL_URL)


def test_compatible_head_does_not_claim_sdk_or_npu_executed():
    opener, calls = fake(Response())
    result = source.head_probe(machine="x86_64", opener=opener)
    assert calls == [("HEAD", source.OFFICIAL_URL, 20)]
    assert result["status"] == "head_metadata_compatible_not_downloaded"
    assert result["official_host_reached"] is True
    assert result["declared_size_within_cap"] is True
    assert result["sdk_downloaded"] is False
    assert result["sdk_installed_or_executed"] is False
    assert result["model_converted"] is False
    assert result["npu_or_htp_executed"] is False
    assert result["ventuno_accessed"] is False


@pytest.mark.parametrize("url", [
    "http://softwarecenter.qualcomm.com/test.zip",
    "https://softwarecenter.qualcomm.com.evil.example/test.zip",
    "https://attacker.invalid/test.zip",
    "https://account:password@softwarecenter.qualcomm.com/test.zip",
    "file:///tmp/test.zip",
])
def test_untrusted_source_rejected(url):
    assert source.source_allowed(url) is False


def test_untrusted_redirect_not_claimed_as_official_availability():
    opener, calls = fake(Response(url="https://attacker.invalid/test.zip"))
    result = source.head_probe(machine="x86_64", opener=opener)
    assert result["status"] == "reject_untrusted_redirect"
    assert result["official_host_reached"] is False
    assert len(calls) == 1


@pytest.mark.parametrize("size,mime,expected", [
    ("", "application/zip", "no_go_size_unknown"),
    ("900", "application/zip", "reject_archive_size"),
    ("4000000000", "application/zip", "reject_archive_size"),
    ("not-a-number", "application/zip", "no_go_size_unknown"),
    ("1234567", "text/html", "no_go_content_type_unverified"),
    ("1234567", "application/zip", "head_metadata_compatible_not_downloaded"),
])
def test_size_and_content_type_are_bounded(size, mime, expected):
    opener, _ = fake(Response(length=size, mime=mime))
    result = source.head_probe(machine="x86_64", opener=opener)
    assert result["status"] == expected


def test_nonhost_refuses_any_request():
    def fail_open(*args, **kwargs):
        pytest.fail("Network should not be touched on board")
    assert source.head_probe(
        machine="aarch64", opener=fail_open
    )["status"] == "reject_nonhost_architecture"


def test_unavailable_source_sanitizes_error_and_exposes_no_sensitive_data():
    def unavailable(*args, **kwargs):
        raise OSError("SECRET_FAKE_TOKEN at /private/sdk-cache")
    result = source.head_probe(machine="x86_64", opener=unavailable)
    encoded = json.dumps(result)
    assert result["status"] == "no_go_official_transport_unavailable"
    assert "SECRET" not in encoded
    assert "/private/" not in encoded
    assert result["sdk_downloaded"] is False
    assert result["ventuno_accessed"] is False


def test_http_non_success_response_is_no_go():
    opener, _ = fake(Response(status=403))
    result = source.head_probe(machine="x86_64", opener=opener)
    assert result["status"] == "no_go_official_source_unavailable"


def test_http_redirect_is_always_head_and_never_off_domain():
    from urllib.error import URLError
    from urllib.request import Request
    handler = source._HeadOnlyAllowedRedirect()
    origin = Request(source.OFFICIAL_URL, method="HEAD")
    new_url = "https://download.qualcomm.com/official-archive.zip"
    redirected = handler.redirect_request(
        origin, None, 302, "Found", {}, new_url
    )
    assert redirected.get_method() == "HEAD"
    assert redirected.full_url == new_url
    with pytest.raises(URLError):
        handler.redirect_request(
            origin, None, 302, "Found", {},
            "https://untrusted.invalid/binary"
        )


@pytest.mark.parametrize("code,reason", [
    (401, "no_go_official_http_auth_required"),
    (403, "no_go_official_http_forbidden"),
    (404, "no_go_official_http_not_found"),
    (405, "no_go_official_head_not_allowed"),
    (429, "no_go_official_http_rate_limited"),
    (503, "no_go_official_http_unavailable"),
])
def test_http_error_status_is_sanitized_without_raw_server_data(code, reason):
    from urllib.error import HTTPError
    def unavailable(*args, **kwargs):
        raise HTTPError(source.OFFICIAL_URL, code, "SECRET HEADER", {}, None)
    result = source.head_probe(machine="x86_64", opener=unavailable)
    assert result["status"] == reason
    assert "SECRET" not in json.dumps(result)
    assert result["sdk_downloaded"] is False
