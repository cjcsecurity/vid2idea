"""Per-job HTTP proxy. Resolve, reject non-public addresses, then connect to that IP.

Both upstream readers use this transport so redirect/CDN requests cannot re-resolve
to the local network. HTTPS remains end-to-end TLS; no certificate interception.
"""
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .urls import SourceError, canonicalize_url, public_addresses


def connect_public(host, port):
    if port not in (80, 443):
        raise SourceError('unsafe_url')
    addresses = public_addresses(host, port)
    for address in addresses:
        try:
            return socket.create_connection((address, port), timeout=30)
        except OSError:
            continue
    raise SourceError('network_unavailable', transient=True)


class SafeProxy:
    def __init__(self, byte_limit=200 * 1024 * 1024, seconds=900):
        self.remaining = byte_limit
        self.deadline = time.monotonic() + seconds
        self.error = None
        self.lock = threading.Lock()

    def consume(self, count):
        with self.lock:
            self.remaining -= count
            if self.remaining < 0:
                raise SourceError('download_limit')
        if time.monotonic() > self.deadline:
            raise SourceError('job_timeout', transient=True)

    def __enter__(self):
        guard = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *args):
                pass

            def relay(self, upstream):
                idle_since = time.monotonic()
                while time.monotonic() < guard.deadline:
                    readable, _, _ = select.select([self.connection, upstream], [], [], 1)
                    if not readable and time.monotonic() - idle_since > 30:
                        return
                    for source in readable:
                        block = source.recv(65536)
                        if not block:
                            return
                        idle_since = time.monotonic()
                        if source is upstream:
                            guard.consume(len(block))
                        (self.connection if source is upstream else upstream).sendall(block)

            def do_CONNECT(self):
                try:
                    p = urlsplit('https://' + self.path)
                    canonicalize_url('https://' + self.path)
                    if p.port not in (None, 443):
                        raise SourceError('unsafe_url')
                    with connect_public(p.hostname, 443) as upstream:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.flush()
                        self.relay(upstream)
                except SourceError as error:
                    guard.error = error
                    self.close_connection = True
                except (OSError, ValueError):
                    self.close_connection = True

            def forward(self):
                try:
                    target = canonicalize_url(self.path)
                    p = urlsplit(target)
                    if p.scheme != 'http':
                        raise SourceError('unsafe_url')
                    if self.headers.get('Transfer-Encoding'):
                        raise SourceError('unsafe_request')
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 <= size <= 1024 * 1024:
                        raise SourceError('request_limit')
                    self.connection.settimeout(30)
                    body = self.rfile.read(size)
                    with connect_public(p.hostname, p.port or 80) as upstream:
                        path = p.path + ('?' + p.query if p.query else '')
                        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host','connection','proxy-connection','proxy-authorization')}
                        headers.update({'Host': p.netloc, 'Connection': 'close'})
                        request = f'{self.command} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in headers.items()) + '\r\n'
                        upstream.sendall(request.encode('latin-1') + body)
                        while block := upstream.recv(65536):
                            guard.consume(len(block))
                            self.connection.sendall(block)
                except SourceError as error:
                    guard.error = error
                    self.send_error(403, 'Source request rejected')
                except (OSError, ValueError):
                    self.close_connection = True

            do_GET = forward
            do_HEAD = forward
            do_POST = forward

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
