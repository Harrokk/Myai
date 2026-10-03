import pytest

from core import public_web_client


def public_resolver(host, port, type=None):
    return [
        (
            public_web_client.socket.AF_INET,
            public_web_client.socket.SOCK_STREAM,
            6,
            "",
            ("8.8.8.8", port),
        )
    ]


def private_resolver(host, port, type=None):
    return [
        (
            public_web_client.socket.AF_INET,
            public_web_client.socket.SOCK_STREAM,
            6,
            "",
            ("127.0.0.1", port),
        )
    ]


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        headers=None,
        body=b"",
        encoding="utf-8",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.body = body
        self.encoding = encoding

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def iter_content(self, chunk_size=16384):
        yield self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_validate_url_blocks_private_network():
    client = public_web_client.PublicWebClient(
        resolver=private_resolver,
    )

    with pytest.raises(ValueError):
        client.validate_url("http://localhost/admin")


def test_validate_url_blocks_non_http_scheme():
    client = public_web_client.PublicWebClient(
        resolver=public_resolver,
    )

    with pytest.raises(ValueError):
        client.validate_url("file:///etc/passwd")


def test_fetch_extracts_visible_html_text():
    session = FakeSession(
        [
            FakeResponse(
                headers={"Content-Type": "text/html; charset=utf-8"},
                body=(
                    b"<html><head><title>Test title</title>"
                    b"<style>hidden style</style></head>"
                    b"<body>Hello <script>hidden script</script>world</body></html>"
                ),
            )
        ]
    )
    client = public_web_client.PublicWebClient(
        session=session,
        resolver=public_resolver,
    )

    result = client.fetch("https://example.com/page")

    assert result["title"] == "Test title"
    assert "Hello" in result["text"]
    assert "world" in result["text"]
    assert "hidden script" not in result["text"]
    assert "hidden style" not in result["text"]


def test_redirect_to_private_address_is_blocked():
    session = FakeSession(
        [
            FakeResponse(
                status_code=302,
                headers={"Location": "http://127.0.0.1/private"},
            )
        ]
    )

    def resolver(host, port, type=None):
        if host == "example.com":
            return public_resolver(host, port, type)
        return private_resolver(host, port, type)

    client = public_web_client.PublicWebClient(
        session=session,
        resolver=resolver,
    )

    with pytest.raises(ValueError):
        client.fetch("https://example.com/start")

    assert len(session.calls) == 1


def test_binary_content_is_rejected():
    session = FakeSession(
        [
            FakeResponse(
                headers={"Content-Type": "application/octet-stream"},
                body=b"binary",
            )
        ]
    )
    client = public_web_client.PublicWebClient(
        session=session,
        resolver=public_resolver,
    )

    with pytest.raises(ValueError):
        client.fetch("https://example.com/file")


def test_page_size_limit_is_enforced():
    session = FakeSession(
        [
            FakeResponse(
                headers={"Content-Type": "text/plain"},
                body=b"x" * 50,
            )
        ]
    )
    client = public_web_client.PublicWebClient(
        session=session,
        resolver=public_resolver,
        max_bytes=10,
    )

    with pytest.raises(ValueError):
        client.fetch("https://example.com/large")
