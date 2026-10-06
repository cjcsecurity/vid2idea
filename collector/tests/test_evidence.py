import pytest

def test_redirected_article_uses_destination_for_relative_links_and_images(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from scrapling.fetchers import Fetcher
    from vid2idea import articles
    from vid2idea.config import Settings
    from vid2idea import urls
    monkeypatch.setattr(urls,'public_addresses',lambda *args:['93.184.216.34'])
    html='<main><p>A detailed article about a useful project with links and an illustration.</p><a href="../tool">Featured tool</a><img src="./image.jpg" /></main>'
    monkeypatch.setattr(Fetcher,'get',lambda *args,**kwargs:SimpleNamespace(status=200,url='https://destination.example.org/posts/article',html_content=html))
    calls=[]
    def candidates(html,url):
        calls.append(url)
        return []
    monkeypatch.setattr(articles,'article_image_candidates',candidates)
    evidence=articles.read_article('https://example.com/short',Settings(),tmp_path)
    assert evidence.links[0].url=='https://destination.example.org/tool'
    assert calls == ['https://destination.example.org/posts/article']

def test_article_cannot_bypass_guard_with_no_proxy(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from vid2idea import articles
    from vid2idea.config import Settings
    from vid2idea.urls import SourceError

    hits = []
    class Fixture(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<main><p>This private fixture must never become source evidence.</p></main>')
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv('NO_PROXY', '*')
        monkeypatch.setenv('no_proxy', '*')
        # Simulate a target becoming private after initial URL validation.
        # The actual transport must still enforce its own public-address guard.
        monkeypatch.setattr(articles, 'validate_public_url', lambda url: url)
        with pytest.raises(SourceError):
            articles.read_article(f'http://127.0.0.1:{server.server_port}/private', Settings())
        assert hits == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

def test_article_requires_real_content():
    from vid2idea.articles import evidence_from_html
    from vid2idea.urls import SourceError
    with pytest.raises(SourceError, match='empty_article'):
        evidence_from_html('<html><body></body></html>')
    evidence = evidence_from_html('<html><main><h1>A clever garden</h1><p>Build a garden using wooden trays and a timer for irrigation.</p></main></html>')
    assert 'wooden trays' in evidence.text
    assert evidence.kinds == ['article_text']

def test_video_combines_only_successful_evidence(tmp_path):
    from vid2idea.videos import combine_evidence
    frame = tmp_path / 'frame.jpg'
    frame.write_bytes(b'image')
    evidence = combine_evidence('How to make a lamp', '', [frame], [])
    assert evidence.kinds == ['captions']
    assert evidence.frames == [frame]
    assert 'video_frames' not in evidence.kinds  # only added after a vision model accepts them

def test_temporary_media_removed_on_error(tmp_path):
    from vid2idea.videos import media_workspace
    with pytest.raises(RuntimeError):
        with media_workspace(tmp_path) as workdir:
            (workdir / 'video.mp4').write_bytes(b'private')
            raise RuntimeError('stop')
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def video_reader(monkeypatch, tmp_path):
    import yt_dlp
    from vid2idea import videos
    from vid2idea.config import Settings
    from vid2idea.urls import SourceError

    calls = []
    real_downloader = yt_dlp.YoutubeDL
    metadata = {'duration': None, 'ext': 'mp4', 'formats': [
        {'format_id': 'progressive', 'height': 720, 'protocol': 'https', 'vcodec': None, 'acodec': None, 'ext': 'mp4'}
    ]}
    actual_duration = [30]
    path = tmp_path / 'source.mp4'

    class Downloader:
        def __init__(self, options):
            self.options = options
            assert options['max_filesize'] == Settings().max_download_bytes
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def add_info_extractor(self, extractor): pass
        def extract_info(self, url, download, process=False): return metadata
        def process_ie_result(self, info, download):
            with real_downloader({'quiet': True}) as selector_client:
                select = selector_client.build_format_selector(self.options['format'])
                if not list(select({'formats': info['formats'], 'has_merged_format': False, 'incomplete_formats': False})):
                    raise SourceError('video_unavailable')
            calls.append('download')
            assert self.options['match_filter'](info) is None
            path.write_bytes(b'bounded media fixture')
            self.options['progress_hooks'][0]({'downloaded_bytes': path.stat().st_size})
            return info
        def prepare_filename(self, info): return str(path)

    class Proxy:
        url = 'http://127.0.0.1:12345'
        error = None
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    def media(args):
        if args[0] == 'ffprobe':
            calls.append('probe')
            return str(actual_duration[0]).encode()
        if '-vn' in args:
            calls.append('audio')
            (tmp_path / 'audio.wav').write_bytes(b'audio')
        else:
            calls.append('frames')
            (tmp_path / 'frame-01.jpg').write_bytes(b'frame')
        return b''

    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Downloader)
    monkeypatch.setattr(videos, 'SafeProxy', Proxy)
    monkeypatch.setattr(videos, 'validate_public_url', lambda url: url)
    monkeypatch.setattr(videos, 'run_media', media)
    monkeypatch.setattr(videos, 'transcribe_audio', lambda *args: 'Build a lamp from recycled wood.')
    monkeypatch.setattr(videos, 'scan_frame_text', lambda frames,interval: (frames[:12],'',[],[]))
    return lambda: videos.read_video('https://www.instagram.com/reel/fixture/', Settings(), tmp_path), metadata, actual_duration, calls


def test_missing_video_duration_is_verified_after_bounded_download(video_reader):
    read, metadata, duration, calls = video_reader
    evidence = read()
    assert calls == ['download', 'probe', 'audio', 'frames']
    assert evidence.kinds == ['audio_transcript']
    assert 'recycled wood' in evidence.text
    assert len(evidence.frames) == 1


def test_unknown_video_height_keeps_public_progressive_format(video_reader):
    read, metadata, duration, calls = video_reader
    metadata['formats'][0]['height'] = None
    evidence = read()
    assert calls == ['download', 'probe', 'audio', 'frames']
    assert evidence.text


def test_unknown_video_duration_over_limit_stops_before_analysis(video_reader):
    from vid2idea.urls import SourceError
    read, metadata, duration, calls = video_reader
    duration[0] = 601
    with pytest.raises(SourceError, match='video_limit'):
        read()
    assert calls == ['download', 'probe']


def test_known_long_video_is_rejected_before_download(video_reader):
    from vid2idea.urls import SourceError
    read, metadata, duration, calls = video_reader
    metadata['duration'] = 601
    with pytest.raises(SourceError, match='video_limit'):
        read()
    assert calls == []


def test_installed_whisper_decoder_reads_collector_wav(tmp_path):
    import wave
    from faster_whisper.audio import decode_audio
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 16000)
    decoded = decode_audio(str(path))
    assert len(decoded) == 16000
    assert not decoded.any()


def test_silent_video_uses_visual_evidence_without_transcription_error(video_reader):
    read, metadata, duration, calls = video_reader
    metadata['acodec'] = 'none'
    evidence = read()
    assert calls == ['download', 'probe', 'frames']
    assert not any('Speech could not' in gap for gap in evidence.gaps)
