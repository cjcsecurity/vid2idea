import socket
import pytest

@pytest.mark.parametrize('url', ['https://[bad]/', 'https://example.com/\r\nInjected: value', 'https://example.com/with space', 'https://example.com/\x00'])
def test_malformed_urls_fail_with_safe_error(url):
    from vid2idea.urls import canonicalize_url, SourceError
    with pytest.raises(SourceError, match='unsafe_url'):
        canonicalize_url(url)

def test_canonical_url_preserves_content_query():
    from vid2idea.urls import canonicalize_url
    assert canonicalize_url('https://EXAMPLE.com/watch?v=abc&utm_source=feed#top') == 'https://example.com/watch?v=abc'

@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://me:secret@example.com/', 'http://localhost/', 'http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/'])
def test_rejects_private_urls(url):
    from vid2idea.urls import validate_public_url, SourceError
    with pytest.raises(SourceError):
        validate_public_url(url)

def test_rejects_mixed_private_dns(monkeypatch):
    from vid2idea.urls import validate_public_url, SourceError
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('93.184.216.34',80)), (2,1,6,'',('10.0.0.1',80))])
    with pytest.raises(SourceError):
        validate_public_url('http://example.com')

def test_proxy_connects_to_verified_ip_and_rejects_redirect_target(monkeypatch):
    from vid2idea.safe_proxy import connect_public
    from vid2idea.urls import SourceError
    connected = []
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('93.184.216.34',443))])
    monkeypatch.setattr(socket, 'create_connection', lambda target, **k: connected.append(target))
    connect_public('example.com', 443)
    assert connected == [('93.184.216.34', 443)]
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(SourceError):
        connect_public('redirect.example.com', 443)
    assert len(connected) == 1
