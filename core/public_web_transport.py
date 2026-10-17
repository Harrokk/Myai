"""Public-only HTTP transport that pins the *socket* to an approved DNS IP.

No proxy is used. DNS resolution and the IP public-range check occur in the
caller before this transport is invoked. The numeric IP is used for the TCP
connect; for HTTPS the original DNS hostname is used for SNI and certificate
verification. A proxy or second DNS lookup must never override the pin.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from requests.structures import CaseInsensitiveDict


# RFC 6052 NAT64 and IPv6 tunnelling can encode a private IPv4
# destination inside an apparently global IPv6 literal. A plain
# ipaddress.is_global check is insufficient for the well-known NAT64
# prefix (e.g. 64:ff9b::a9fe:a9fe maps to 169.254.169.254).
# Public-page fetching denies these transition networks completely;
# IPv6-only NAT64 deployments need a separately reviewed egress policy.
_BLOCKED_IPV6_TRANSITION_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),    # well-known NAT64
    ipaddress.ip_network("64:ff9b:1::/48"),  # local-use translation prefix
    ipaddress.ip_network("2002::/16"),       # 6to4
    ipaddress.ip_network("2001::/32"),       # Teredo
)


def is_public_connect_address(address):
    """Fail closed on non-global and IPv4-carrying transition addresses."""
    try:
        parsed = ipaddress.ip_address(address)
    except (TypeError, ValueError):
        return False

    if not parsed.is_global:
        return False

    if isinstance(parsed, ipaddress.IPv6Address):
        return not any(
            parsed in network for network in _BLOCKED_IPV6_TRANSITION_NETWORKS
        )
    return True


class _PinnedResponse:
    def __init__(self, connection, http_response, verified_peer_ip):
        self._connection = connection
        self._response = http_response
        self._pinned_peer_ip = verified_peer_ip
        self.status_code = http_response.status
        self.headers = CaseInsensitiveDict(http_response.getheaders())
        self.encoding = "utf-8"
        self._closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError("Fjärrwebbsidan svarade med ett HTTP-fel.")

    def iter_content(self, chunk_size=16384):
        if not isinstance(chunk_size, int) or chunk_size < 1:
            raise ValueError("Ogiltig storlek på nätverksblock.")
        while True:
            chunk = self._response.read(chunk_size)
            if not chunk:
                break
            yield chunk

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        finally:
            self._connection.close()


class PinnedPublicWebTransport:
    """Send GET only after the socket peer equals a previously allowed IP.

    The injected factories exist only for offline unit tests. Default use is
    the real system socket and a default certificate-verifying SSL context.
    """

    def __init__(
        self,
        *,
        connector=None,
        connection_factory=None,
        ssl_context_factory=None,
    ):
        self._connector = connector or socket.create_connection
        self._connection_factory = connection_factory or http.client.HTTPConnection
        self._ssl_context_factory = ssl_context_factory or ssl.create_default_context

    def get(
        self,
        url,
        *,
        approved_ips,
        timeout,
        headers,
        allow_redirects=False,
        stream=True,
    ):
        if allow_redirects or not stream:
            raise ValueError("Omdirigeringar och obundna svar är otillåtna.")

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Endast http/https är tillåtet.")
        if not parsed.hostname or "@" in parsed.netloc:
            raise ValueError("Ogiltigt värdnamn.")

        expected_port = 443 if parsed.scheme == "https" else 80
        port = parsed.port if parsed.port is not None else expected_port
        if port != expected_port:
            raise ValueError("Publik webb får bara använda standardport 80/443.")
        if not isinstance(approved_ips, (tuple, list)) or not approved_ips:
            raise ValueError("Ingen verifierad publik IP-adress finns.")

        # The caller has verified ALL resolved addresses. Do not ask DNS a
        # second time when the connection is created.
        try:
            approved = tuple(str(ipaddress.ip_address(ip)) for ip in approved_ips)
        except ValueError as error:
            raise ValueError("Ogiltig verifierad IP-adress.") from error
        if not all(is_public_connect_address(ip) for ip in approved):
            raise ValueError("Privat eller icke-publik anslutningsadress.")
        target_ip = approved[0]

        try:
            hostname = parsed.hostname.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise ValueError("Ogiltigt DNS-värdnamn.") from error
        connection = self._connection_factory(
            hostname, port=port, timeout=timeout
        )
        raw_socket = None
        response = None
        try:
            # Numeric address: no resolver, local proxy or DNS rebound here.
            raw_socket = self._connector((target_ip, port), timeout=timeout)
            try:
                peer = str(ipaddress.ip_address(raw_socket.getpeername()[0]))
            except (OSError, ValueError, IndexError, TypeError) as error:
                raise ValueError("TCP-anslutningens faktiska IP kan inte intygas.") from error
            if peer != target_ip or not is_public_connect_address(peer):
                raise ValueError("Anslutningens IP avviker från verifierad publik IP.")

            if parsed.scheme == "https":
                # Default context verifies CA chain and the *original*
                # hostname, never the numerical connection target.
                context = self._ssl_context_factory()
                if not context.verify_mode == ssl.CERT_REQUIRED or not context.check_hostname:
                    raise ValueError("TLS-certifikatverifiering får inte inaktiveras.")
                raw_socket = context.wrap_socket(raw_socket, server_hostname=hostname)

            connection.sock = raw_socket
            raw_socket = None
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            host_header = hostname
            if ":" in host_header:
                host_header = f"[{host_header}]"
            if port != (443 if parsed.scheme == "https" else 80):
                host_header += f":{port}"
            safe_headers = dict(headers)
            safe_headers["Host"] = host_header
            safe_headers["Connection"] = "close"
            connection.request("GET", path, headers=safe_headers)
            response = connection.getresponse()
            return _PinnedResponse(connection, response, peer)
        except BaseException:
            if response is not None:
                response.close()
            if raw_socket is not None:
                raw_socket.close()
            connection.close()
            raise
