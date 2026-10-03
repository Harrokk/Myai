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
        self.meta = {}
        self.canonical_url = ""
        self.links = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attributes = {
            str(key).lower(): value
            for key, value in attrs
            if key
        }

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

        if tag == "title":
            self._in_title = True

        if tag == "meta":
            key = (
                attributes.get("name")
                or attributes.get("property")
                or attributes.get("itemprop")
                or ""
            ).strip().lower()
            content = str(attributes.get("content") or "").strip()

            if key and content and key not in self.meta:
                self.meta[key] = content

        if tag == "link":
            rel = str(attributes.get("rel") or "").lower().split()
            href = str(attributes.get("href") or "").strip()

            if "canonical" in rel and href:
                self.canonical_url = href

        if tag == "a":
            href = str(attributes.get("href") or "").strip()

            if href:
                self.links.append(href)

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


def _is_public_ip(address):
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

        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("timeout_seconds måste vara > 0 och <= 120.")

        if self.max_bytes < 1 or self.max_bytes > 10_000_000:
            raise ValueError("max_bytes måste vara mellan 1 och 10000000.")

        if self.max_redirects < 0 or self.max_redirects > 10:
            raise ValueError("max_redirects måste vara mellan 0 och 10.")

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

        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as error:
            raise ValueError("URL innehåller ogiltig port.") from error

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
            if not _is_public_ip(address)
        ]

        if blocked:
            raise ValueError(
                "Privat, lokal eller icke-publik IP-adress blockeras."
            )

        return url

    def _read_body(self, response):
        content_length = response.headers.get("Content-Length")

        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    raise ValueError(
                        "Webbsidan överskrider maximal tillåten storlek."
                    )
            except ValueError as error:
                if "överskrider" in str(error):
                    raise

        chunks = []
        total = 0

        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue

            total += len(chunk)

            if total > self.max_bytes:
                raise ValueError(
                    "Webbsidan överskrider maximal tillåten storlek."
                )

            chunks.append(chunk)

        encoding = response.encoding or "utf-8"
        return b"".join(chunks).decode(encoding, errors="replace")

    def fetch(self, url):
        current = str(url or "").strip()

        for redirect_index in range(self.max_redirects + 1):
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

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")

                if not location:
                    raise ValueError("Redirect saknar Location-header.")

                if redirect_index >= self.max_redirects:
                    raise ValueError("För många redirects.")

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
                    "Otillåten eller okänd innehållstyp: "
                    f"{content_type or 'saknas'}"
                )

            raw_text = self._read_body(response)
            title = ""

            metadata = {}
            canonical_url = ""
            external_links = []

            if content_type in {"text/html", "application/xhtml+xml"}:
                parser = _VisibleTextParser()
                parser.feed(raw_text)
                title = parser.title
                text = parser.text
                metadata = dict(parser.meta)
                canonical_url = (
                    urljoin(current, parser.canonical_url)
                    if parser.canonical_url
                    else ""
                )
                current_host = (urlparse(current).hostname or "").lower()

                for href in parser.links:
                    absolute = urljoin(current, href)
                    parsed_link = urlparse(absolute)
                    host = (parsed_link.hostname or "").lower()

                    if (
                        parsed_link.scheme in {"http", "https"}
                        and host
                        and host != current_host
                    ):
                        external_links.append(absolute)
            else:
                text = raw_text.strip()

            return {
                "requested_url": url,
                "final_url": current,
                "status_code": response.status_code,
                "content_type": content_type,
                "title": title,
                "text": text,
                "metadata": metadata,
                "canonical_url": canonical_url,
                "external_links": sorted(set(external_links)),
                "redirects": redirect_index,
            }

        raise ValueError("Webbsidan kunde inte hämtas.")
