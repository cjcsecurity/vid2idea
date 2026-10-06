"""Exercise the real yt-dlp mapper/dispatcher with synthetic network responses."""
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from yt_dlp.extractor.instagram import InstagramIE

from vid2idea.config import Settings
from vid2idea.models import EvidenceKind
from vid2idea.urls import SourceError
from vid2idea.videos import read_video


@pytest.fixture
def carousel(monkeypatch, tmp_path):
    from vid2idea import urls
    import rapidocr
    product = {'pk': '12345', 'user': {'username': 'fixture'},
               'caption': {'text': 'Build a garden with these steps.'},
               'carousel_media': [
                   {'pk': str(i), 'media_type': 1, 'image_versions2': {'candidates': [
                       {'url': f'https://cdn.example.org/{i}.jpg', 'width': 320, 'height': 240}]}}
                   for i in range(1, 4)]}
    body = BytesIO()
    Image.new('RGB', (320, 240), 'green').save(body, format='PNG')
    responses = {f'/{i}.jpg': (200, body.getvalue()) for i in range(1, 22)}
    hits = []
    def respond(request):
        hits.append(request.url.path)
        status, data = responses[request.url.path]
        return httpx.Response(status, content=data)
    client = httpx.Client
    def fixture_client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['proxy'].startswith('http://127.0.0.1:')
        return client(transport=httpx.MockTransport(respond), follow_redirects=True)
    monkeypatch.setattr(httpx, 'Client', fixture_client)
    monkeypatch.setattr(urls.socket, 'getaddrinfo', lambda host, port, **kwargs: [(2, 1, 6, '', (host if host == '127.0.0.1' else '93.184.216.34', port))])
    monkeypatch.setattr(InstagramIE, '_real_initialize', lambda self: None)
    monkeypatch.setattr(InstagramIE, '_can_impersonate', True)
    monkeypatch.setattr(InstagramIE, '_download_json', lambda self, url, *args, **kwargs:
        {'status': 'ok'} if 'get_ruling_for_content' in url else
        {'data': {'xig_polaris_media': {'if_not_gated_logged_out': product}}})
    monkeypatch.setattr(rapidocr, 'RapidOCR', lambda **kwargs: lambda path: SimpleNamespace(txts=['Garden instructions'], scores=[.99]))
    return product, responses, hits, lambda settings=None: read_video('https://www.instagram.com/p/Fixture/', settings or Settings(), tmp_path)


def test_carousel_preserves_order_caption_and_slide_provenance(carousel):
    product, responses, hits, read = carousel
    evidence = read()
    assert hits == ['/1.jpg', '/2.jpg', '/3.jpg']
    assert [p.name for p in evidence.frames] == ['slide-001.jpg', 'slide-002.jpg', 'slide-003.jpg']
    assert 'Build a garden' in evidence.text
    assert '[Slide 1]' in evidence.ocr_text and '[Slide 3]' in evidence.ocr_text
    assert evidence.ocr_text.count('Garden instructions') == 3
    assert [image.caption for image in evidence.images] == ['Instagram slide 1', 'Instagram slide 2', 'Instagram slide 3']
    assert all(image.timestamp_seconds is None for image in evidence.images)
    assert 'image_slides' in evidence.kinds
    assert not evidence.gaps
    for path in evidence.frames:
        with Image.open(path) as image:
            assert image.format == 'JPEG'


def test_single_photo_uses_same_reader(carousel):
    product, _, _, read = carousel
    product.update(product.pop('carousel_media')[0])
    assert len(read().frames) == 1


def test_failed_middle_slide_keeps_original_numbers(carousel):
    _, responses, _, read = carousel
    responses['/2.jpg'] = (200, b'not an image')
    evidence = read()
    assert [image.caption for image in evidence.images] == ['Instagram slide 1', 'Instagram slide 3']
    assert '[Slide 3]' in evidence.text
    assert any('Slide 2' in gap and 'could not' in gap for gap in evidence.gaps)


def test_all_failed_slides_do_not_become_caption_only_success(carousel):
    _, responses, _, read = carousel
    for key in responses:
        responses[key] = (403, b'blocked')
    with pytest.raises(SourceError, match='no_image_evidence'):
        read()


def test_mixed_post_keeps_video_transcript_and_frames(carousel, video_media):
    product, _, hits, read = carousel
    product['carousel_media'][1].update(media_type=2, video_versions=[{'url': 'https://cdn.example.org/video.mp4'}])
    evidence = read()
    assert hits == ['/1.jpg', '/3.jpg']
    assert 'Water the seedlings daily.' in evidence.text
    assert '[Slide 2' in evidence.text
    assert 'audio_transcript' in evidence.kinds
    assert len(evidence.frames) == 4
    assert [image.caption for image in evidence.images] == ['Instagram slide 1', 'Instagram slide 2 (video still)', 'Instagram slide 3']
    assert not any('could not' in gap for gap in evidence.gaps)
    assert any('slide-002' in str(path) for path in evidence.frames)



def test_download_limit_fails_closed(carousel):
    _, responses, _, read = carousel
    responses['/1.jpg'] = (200, b'x' * (4 * 1024 * 1024 + 1))
    with pytest.raises(SourceError, match='download_limit'):
        read()


def test_large_carousel_rejected_before_image_download(carousel):
    product, _, hits, read = carousel
    product['carousel_media'] *= 7
    with pytest.raises(SourceError, match='carousel_limit'):
        read()
    assert hits == []


def test_private_slide_url_fails_closed(carousel):
    product, _, hits, read = carousel
    product['carousel_media'][0]['image_versions2']['candidates'][0]['url'] = 'http://127.0.0.1/private.jpg'
    with pytest.raises(SourceError, match='unsafe_url'):
        read()
    assert hits == []


def test_twenty_slides_all_reach_ocr_but_vision_is_bounded(carousel):
    product, _, hits, read = carousel
    from copy import deepcopy
    template = product['carousel_media'][0]
    product['carousel_media'] = []
    for number in range(1, 21):
        item = deepcopy(template)
        item['pk'] = str(number)
        item['image_versions2']['candidates'][0]['url'] = f'https://cdn.example.org/{number}.jpg'
        product['carousel_media'].append(item)
    evidence = read()
    assert len(hits) == 20 and len(evidence.frames) == 12
    assert '[Slide 20]' in evidence.ocr_text
    assert evidence.frames == sorted(evidence.frames)
    assert any('20' in gap and '12' in gap for gap in evidence.gaps)


def test_aggregate_download_budget_is_enforced(carousel):
    _, responses, hits, read = carousel
    budget = len(responses['/1.jpg'][1]) * 2 - 1
    with pytest.raises(SourceError, match='download_limit'):
        read(Settings(max_download_bytes=budget))
    assert hits == ['/1.jpg', '/2.jpg']


def test_missing_slide_dns_preserves_other_slides(carousel, monkeypatch):
    product, _, _, read = carousel
    from vid2idea import urls
    original = urls.socket.getaddrinfo
    def resolve(host, *args, **kwargs):
        if host == 'missing.example.org':
            raise urls.socket.gaierror('missing')
        return original(host, *args, **kwargs)
    monkeypatch.setattr(urls.socket, 'getaddrinfo', resolve)
    product['carousel_media'][1]['image_versions2']['candidates'][0]['url'] = 'https://missing.example.org/slide.jpg'
    evidence = read()
    assert len(evidence.frames) == 2
    assert any('Slide 2' in gap and 'could not' in gap for gap in evidence.gaps)


def test_oversized_pixel_dimensions_preserve_other_slides(carousel):
    _, responses, _, read = carousel
    content = BytesIO()
    Image.new('1', (4001, 4000)).save(content, format='PNG')
    responses['/2.jpg'] = (200, content.getvalue())
    evidence = read()
    assert len(evidence.frames) == 2
    assert any('Slide 2' in gap and 'could not' in gap for gap in evidence.gaps)


@pytest.fixture
def video_media(monkeypatch):
    from pathlib import Path
    from vid2idea import videos
    import yt_dlp
    def download(self, entry, download):
        entry.update(ext='mp4', title='Fixture clip')
        Path(self.prepare_filename(entry)).write_bytes(b'clip fixture')
        return entry
    durations = [5]
    def media(args, **kwargs):
        if args[0] == 'ffprobe':
            return str(durations.pop(0) if len(durations) > 1 else durations[0]).encode()
        path = Path(args[-1].replace('%03d', '001'))
        Image.new('RGB', (320, 240), 'blue').save(path, format='JPEG')
        if '%03d' in args[-1]:
            Image.new('RGB', (320, 240), 'red').save(Path(args[-1].replace('%03d', '002')), format='JPEG')
        return b''
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'process_ie_result', download)
    monkeypatch.setattr(videos, 'run_media', media)
    monkeypatch.setattr(videos, 'transcribe_audio', lambda *args: 'Water the seedlings daily.')
    return durations


def test_combined_video_duration_is_bounded(carousel, video_media):
    product, _, _, read = carousel
    for entry in product['carousel_media'][:2]:
        entry.update(media_type=2, video_versions=[{'url': 'https://cdn.example.org/clip.mp4'}])
    video_media[:] = [400, 400]
    with pytest.raises(SourceError, match='video_limit'):
        read()


def test_unreadable_video_preserves_photos(carousel, video_media, monkeypatch):
    product, _, _, read = carousel
    from vid2idea import videos
    product['carousel_media'][1].update(media_type=2, video_versions=[{'url': 'https://cdn.example.org/clip.mp4'}])
    def unavailable(*args, **kwargs):
        raise SourceError('media_processing_unavailable')
    monkeypatch.setattr(videos, 'run_media', unavailable)
    evidence = read()
    assert len(evidence.frames) == 2
    assert any('Slide 2' in gap and 'could not' in gap for gap in evidence.gaps)
