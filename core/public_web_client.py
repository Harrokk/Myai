import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests


ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
    "application/xhtml+xml",
}


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return

        value = " ".join((data or "").split())

        if not value:
            return

        self.text_parts.append(value)

        if self._in_title:
            self.title_parts.append(value)

    @property
    def title(self):
        return " ".join(self.title_parts).strip()

    @property
    def text(self):
        return " ".join(self.text_parts).strip()


def _public_ip(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    return ip.is_global


class PublicWebClient:
    def __init__(
        self,
        timeout_seconds=15,
        max_bytes=1_000_000,
        max_redirects=5,
        session=None,
        resolver=None,
    ):
        self.timeout_seconds = float(timeout_seconds)
        self.max_bytes = int(max_bytes)
        self.max_redirects = int(max_redirects)
        self.session = session or requests.Session()
        self.resolver = resolver or socket.getaddrinfo

    def validate_url(self, url):
        try:
            parsed = urlparse(url)
        except ValueError as error:
            raise ValueError("Ogiltig URL.") from error

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Endast http/https är tillåtet.")

        if parsed.username or parsed.password:
            raise ValueError("URL med inbäddade inloggningsuppgifter blockeras.")

        hostname = parsed.hostname

        if not hostname:
            raise ValueError("URL saknar värdnamn.")

        port = parsed.port or (
            443 if parsed.scheme == "https" else 80
        )

        try:
            resolved = self.resolver(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError as error:
            raise ValueError(
                f"Värdnamnet kunde inte lösas: {hostname}"
            ) from error

        addresses = {
            item[4][0]
            for item in resolved
            if item and len(item) >= 5 and item[4]
        }

        if not addresses:
            raise ValueError("Värdnamnet gav ingen IP-adress.")

        blocked = [
            address
            for address in addresses
            if not _public_ip(address)
        ]

        if blocked:
            raise ValueError(
                "Privat, lokal eller icke-publik IP-adress blockeras."
            )

        return url

    def _read_body(self, response):
        chunks = []
        total = 0

        for chunk in response.iter_content(
            chunk_size=16_384,
        ):
            if not chunk:
                continue

            total += len(chunk)

            if total > self.max_bytes:
                raise ValueError(
                    "Webbsidan överskrider maximal tillåten storlek."
                )

            chunks.append(chunk)

        encoding = response.encoding or "utf-8"
        return b"".join(chunks).decode(
            encoding,
            errors="replace",
        )

    def fetch(self, url):
        current = url

        for redirect_index in range(
            self.max_redirects + 1
        ):
            self.validate_url(current)

            response = self.session.get(
                current,
                timeout=self.timeout_seconds,
                headers={
                    "User-Agent": "MyAI/1.0 local-assistant",
                    "Accept": (
                        "text/html,text/plain,application/json,"
                        "application/xml;q=0.9"
                    ),
                },
                allow_redirects=False,
                stream=True,
            )

            if response.status_code in {
                301,
                302,
                303,
                307,
                308,
            }:
                location = response.headers.get("Location")

                if not location:
                    raise ValueError(
                        "Redirect saknar Location-header."
                    )

                if redirect_index >= self.max_redirects:
                    raise ValueError(
                        "För många redirects."
                    )

                current = urljoin(current, location)
                continue

            response.raise_for_status()

            content_type = (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )

            if content_type not in ALLOWED_CONTENT_TYPES:
                raise ValueError(
                    f"Otillåten eller okänd innehållstyp: "
                    f"{content_type or 'saknas'}"
                )

            raw_text = self._read_body(response)
            title = ""

            if content_type in {
                "text/html",
                "application/xhtml+xml",
            }:
                parser = _VisibleTextParser()
                parser.feed(raw_text)
                title = parser.title
                text = parser.text
            else:
                text = raw_text.strip()

            return {
                "requested_url": url,
                "final_url": current,
                "status_code": response.status_code,
                "content_type": content_type,
                "title": title,
                "text": text,
                "redirects": redirect_index,
            }

        raise ValueError("Webbsidan kunde inte hämtas.")
