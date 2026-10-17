"""Socket-level SSRF regression tests: no outbound network or live hardware."""
import ssl

import pytest

from core import public_web_client as client
from core.public_web_transport import PinnedPublicWebTransport


class Socket:
    def __init__(self, ip):
        self.ip = ip
        self.closed = False

    def getpeername(self):
        return self.ip, 443

    def close(self):
        self.closed = True


class RawResponse:
    status = 200
    def __init__(self, text=b"socket-pinned"):
        self.text = text
        self.read_count = 0
        self.closed = False

    def getheaders(self):
        return [("content-type", "text/plain")]

    def read(self, amount):
        self.read_count += 1
        if not self.text:
            return b""
        result, self.text = self.text[:amount], self.text[amount:]
        return result

    def close(self):
        self.closed = True


class FakeHTTPConnection:
    made = []

    def __init__(self, host, *, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = None
        self.requests = []
        self.raw = RawResponse()
        self.closed = False
        self.__class__.made.append(self)

    def request(self, method, path, *, headers):
        assert self.sock is not None
        self.requests.append((method, path, headers))

    def getresponse(self):
        assert self.requests
        return self.raw

    def close(self):
        self.closed = True
        if self.sock:
            self.sock.close()


class FakeVerifyingSSL:
    verify_mode = ssl.CERT_REQUIRED
    check_hostname = True

    def __init__(self):
        self.names = []

    def wrap_socket(self, sock, *, server_hostname):
        self.names.append(server_hostname)
        return sock


def make_client(*, resolver, actual_ip="93.184.216.34", ssl_factory=FakeVerifyingSSL):
    sent = []
    ssl_instance = ssl_factory()
    def connect(endpoint, *, timeout):
        sent.append(endpoint)
        return Socket(actual_ip)
    transport = PinnedPublicWebTransport(
        connector=connect,
        connection_factory=FakeHTTPConnection,
        ssl_context_factory=lambda: ssl_instance,
    )
    fake = client.PublicWebClient(resolver=resolver)
    fake.session = transport
    return fake, sent, ssl_instance


def public_resolver(host, port, type=None):
    return [(client.socket.AF_INET, client.socket.SOCK_STREAM, 6, "",
             ("93.184.216.34", port))]


def test_socket_is_connected_to_the_approved_ip_not_hostname():
    FakeHTTPConnection.made.clear()
    f, connects, tls = make_client(resolver=public_resolver)
    result = f.fetch("https://example.com/some/page?x=1")
    assert result["text"] == "socket-pinned"
    assert connects == [("93.184.216.34", 443)]
    assert tls.names == ["example.com"]
    conn = FakeHTTPConnection.made[-1]
    assert conn.host == "example.com"
    assert conn.requests[0][0:2] == ("GET", "/some/page?x=1")
    assert conn.requests[0][2]["Host"] == "example.com"
    assert conn.closed is True and conn.raw.closed is True


def test_dns_is_resolved_once_per_hop_not_rechecked_by_socket():
    queries = []
    def rebinding(host, port, type=None):
        queries.append(host)
        if len(queries) > 1:
            raise AssertionError("Unapproved second DNS resolution")
        return public_resolver(host, port, type)
    f, connected, _ = make_client(resolver=rebinding)
    f.fetch("https://example.com/rebinding")
    assert queries == ["example.com"]
    assert connected == [("93.184.216.34", 443)]


def test_private_peer_is_rejected_before_any_http_request():
    FakeHTTPConnection.made.clear()
    f, connected, _ = make_client(
        resolver=public_resolver, actual_ip="127.0.0.1"
    )
    with pytest.raises(ValueError, match="avviker"):
        f.fetch("https://example.com/private-service")
    assert connected == [("93.184.216.34", 443)]
    conn = FakeHTTPConnection.made[-1]
    assert conn.requests == []
    assert conn.closed is True


def test_resolver_with_private_and_public_ip_is_rejected_before_connect():
    def mixed(host, port, type=None):
        return public_resolver(host, port, type) + [
            (client.socket.AF_INET, client.socket.SOCK_STREAM, 6,
             "", ("127.0.0.1", port))
        ]
    FakeHTTPConnection.made.clear()
    f, connected, _ = make_client(resolver=mixed)
    with pytest.raises(ValueError, match="Privat"):
        f.fetch("http://example.com/")
    assert connected == []
    assert FakeHTTPConnection.made == []


def test_wrong_or_disabled_tls_verification_fails_before_http():
    class NotVerifying(FakeVerifyingSSL):
        check_hostname = False
    FakeHTTPConnection.made.clear()
    f, connected, _ = make_client(
        resolver=public_resolver, ssl_factory=NotVerifying
    )
    with pytest.raises(ValueError, match="TLS"):
        f.fetch("https://example.com/no-certificate")
    assert connected == [("93.184.216.34", 443)]
    assert FakeHTTPConnection.made[-1].requests == []


def test_transport_never_calls_environment_proxy_or_requests_session(monkeypatch):
    FakeHTTPConnection.made.clear()
    def forbidden(*a, **k):
        raise AssertionError("requests proxy session was used")
    monkeypatch.setattr(client.socket, "getaddrinfo", forbidden)
    f, connected, _ = make_client(resolver=public_resolver)
    assert f.fetch("https://example.com/")["text"] == "socket-pinned"
    assert connected == [("93.184.216.34", 443)]


def test_username_even_if_empty_is_blocked_before_socket():
    FakeHTTPConnection.made.clear()
    f, connected, _ = make_client(resolver=public_resolver)
    with pytest.raises(ValueError):
        f.fetch("https://@example.com/secret")
    assert connected == []


def test_failed_peer_socket_is_closed_even_before_response():
    FakeHTTPConnection.made.clear()
    f, _, _ = make_client(resolver=public_resolver, actual_ip="10.0.0.1")
    with pytest.raises(ValueError):
        f.fetch("http://example.com/fail")
    assert FakeHTTPConnection.made[-1].closed is True
    assert FakeHTTPConnection.made[-1].requests == []



def test_pinned_redirect_to_private_host_never_connects_to_target():
    class RedirectHTTPConnection(FakeHTTPConnection):
        def __init__(self, host, *, port, timeout):
            super().__init__(host, port=port, timeout=timeout)
            self.raw.status = 302
            self.raw.getheaders = lambda: [
                ("Location", "http://localhost/admin"),
            ]

    def resolve(host, port, type=None):
        if host == "localhost":
            return [(client.socket.AF_INET, client.socket.SOCK_STREAM, 6,
                     "", ("127.0.0.1", port))]
        return public_resolver(host, port, type)

    sockets = []
    def connector(address, *, timeout):
        sockets.append(address)
        return Socket(address[0])

    transport = PinnedPublicWebTransport(
        connector=connector,
        connection_factory=RedirectHTTPConnection,
        ssl_context_factory=FakeVerifyingSSL,
    )
    f = client.PublicWebClient(resolver=resolve, session=transport)
    with pytest.raises(ValueError, match="Privat"):
        f.fetch("https://example.com/start")
    assert sockets == [("93.184.216.34", 443)]


def test_dns_rebind_on_second_redirect_hop_denied_before_new_connection():
    class RedirectHTTPConnection(FakeHTTPConnection):
        def __init__(self, host, *, port, timeout):
            super().__init__(host, port=port, timeout=timeout)
            self.raw.status = 302
            self.raw.getheaders = lambda: [("Location", "/again")]

    dns_queries = []
    def resolve(host, port, type=None):
        dns_queries.append(host)
        if len(dns_queries) == 1:
            return public_resolver(host, port, type)
        return [(client.socket.AF_INET, client.socket.SOCK_STREAM, 6,
                 "", ("10.10.10.10", port))]

    sockets = []
    def connector(address, *, timeout):
        sockets.append(address)
        return Socket(address[0])

    transport = PinnedPublicWebTransport(
        connector=connector,
        connection_factory=RedirectHTTPConnection,
        ssl_context_factory=FakeVerifyingSSL,
    )
    f = client.PublicWebClient(resolver=resolve, session=transport)
    with pytest.raises(ValueError, match="Privat"):
        f.fetch("https://example.com/first")
    assert dns_queries == ["example.com", "example.com"]
    assert sockets == [("93.184.216.34", 443)]



@pytest.mark.parametrize("url", [
    "http://example.com:443/unsafe",
    "https://example.com:8080/private",
    "https://example.com:0/invalid",
    "http://example.com:2375/docker",
])
def test_nonstandard_or_cross_protocol_ports_never_connect(url):
    f, connections, _ = make_client(resolver=public_resolver)
    with pytest.raises(ValueError, match="standardport"):
        f.fetch(url)
    assert connections == []


# IPv6 transition addresses can look global while carrying a private IPv4
# destination. These tests must never open a real socket.
@pytest.mark.parametrize("address", [
    "64:ff9b::a9fe:a9fe",                 # NAT64 -> 169.254.169.254
    "64:ff9b::a00:1",                    # NAT64 -> 10.0.0.1
    "64:ff9b::808:808",                  # conservative: even public NAT64
    "64:ff9b:1::a00:1",                 # local-use translation
    "2002:0808:0808::1",                # 6to4
    "2001:0000:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
    "::ffff:127.0.0.1",                 # IPv4 mapped loopback
])
def test_ipv6_transition_dns_addresses_blocked_before_socket(address):
    assert client._is_public_ip(address) is False
    connections = []

    def resolve(host, port, type=None):
        return [(client.socket.AF_INET6, client.socket.SOCK_STREAM, 6,
                 "", (address, port, 0, 0))]

    f, connections, _ = make_client(resolver=resolve)
    FakeHTTPConnection.made.clear()
    with pytest.raises(ValueError, match="Privat"):
        f.fetch("https://example.com/page")
    assert connections == []
    assert FakeHTTPConnection.made == []


@pytest.mark.parametrize("address", [
    "64:ff9b::a9fe:a9fe",
    "64:ff9b::a00:1",
    "2002:0808:0808::1",
])
def test_pinned_transport_rejects_transition_ip_even_if_preapproved(address):
    def forbidden_connector(*args, **kwargs):
        pytest.fail("A transition IPv6 address reached the socket connector")

    FakeHTTPConnection.made.clear()
    transport = PinnedPublicWebTransport(
        connector=forbidden_connector,
        connection_factory=FakeHTTPConnection,
        ssl_context_factory=FakeVerifyingSSL,
    )
    with pytest.raises(ValueError, match="Privat"):
        transport.get(
            "https://example.com/",
            approved_ips=(address,),
            timeout=5,
            headers={"Accept": "text/plain"},
            allow_redirects=False,
            stream=True,
        )
    assert FakeHTTPConnection.made == []


@pytest.mark.parametrize("address", [
    "93.184.216.34",
    "2606:4700:4700::1111",
])
def test_ordinary_public_ip_addresses_remain_eligible(address):
    assert client._is_public_ip(address) is True
