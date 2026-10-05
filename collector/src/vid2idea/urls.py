import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class SourceError(Exception):
    def __init__(self, code: str, transient: bool = False, retry_after: float | None = None):
        super().__init__(code)
        self.code, self.transient, self.retry_after = code, transient, retry_after


def canonicalize_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 8192 or any(ord(char) < 33 or ord(char) == 127 for char in url):
        raise SourceError('unsafe_url')
    try:
        p = urlsplit(url)
        host = (p.hostname or '').lower().encode('idna').decode()
    except (ValueError, UnicodeError):
        raise SourceError('unsafe_url') from None
    if p.scheme.lower() not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise SourceError('unsafe_url')
    try:
        port = p.port
    except ValueError:
        raise SourceError('unsafe_url') from None
    if port not in (None, 80, 443):
        raise SourceError('unsafe_url')
    if ':' in host:
        host = f'[{host}]'
    scheme = p.scheme.lower()
    authority = host + (f':{port}' if port and port != {'http': 80, 'https': 443}[scheme] else '')
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'igsh', 'igshid')]
    return urlunsplit((scheme, authority, p.path or '/', urlencode(query), ''))


def public_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    except (socket.gaierror, UnicodeError):
        raise SourceError('dns_unavailable', transient=True) from None
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise SourceError('unsafe_url')
    return addresses


def validate_public_url(url: str) -> str:
    normalized = canonicalize_url(url)
    p = urlsplit(normalized)
    public_addresses(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
    return normalized
