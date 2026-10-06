import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from .models import Evidence, EvidenceKind
from .safe_proxy import SafeProxy
from .transcribe import transcribe_audio
from .urls import SourceError, validate_public_url
from .ocr import scan_frame_text


def is_video_url(url):
    host = (urlsplit(url).hostname or '').lower()
    return any(host == base or host.endswith('.' + base) for base in ('tiktok.com','instagram.com','youtube.com','youtu.be'))


@contextmanager
def media_workspace(root: Path):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with TemporaryDirectory(prefix='media-', dir=root) as directory:
        yield Path(directory)


def combine_evidence(captions, transcript, frames, gaps):
    kinds = []
    if captions:
        kinds.append(EvidenceKind.captions)
    elif transcript:
        kinds.append(EvidenceKind.audio_transcript)
    return Evidence(text=(captions or transcript)[:48000], kinds=kinds, frames=frames, gaps=gaps)


def run_media(args, timeout=120):
    # Downloaded files must be self-contained video containers. Playlist/image
    # demuxers can dereference other files or URLs outside the source guard.
    args = [args[0], '-protocol_whitelist', 'file,pipe', '-format_whitelist',
            'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm', *args[1:]]
    try:
        return subprocess.run(args, capture_output=True, check=True, timeout=timeout).stdout
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise SourceError('media_processing_unavailable') from None


def read_video(url, settings, workdir):
    import yt_dlp
    from .instagram import InstagramSlidesIE, read_slides
    url = validate_public_url(url)
    if not is_video_url(url):
        raise SourceError('unsupported_video')
    instagram_post = InstagramSlidesIE.suitable(url)
    class Quiet:
        def debug(self, *args): pass
        def warning(self, *args): pass
        def error(self, *args): pass
    def progress(event):
        if event.get('downloaded_bytes', 0) > settings.max_download_bytes:
            raise SourceError('download_limit')
    def limit(info, **kwargs):
        # Some platforms omit duration. Download within the byte/deadline caps;
        # FFprobe must verify the actual duration before any evidence analysis.
        duration = info.get('duration')
        if duration is not None and not 0 < duration <= settings.max_video_seconds:
            return 'Video duration exceeds the configured limit'
        if (info.get('filesize') or info.get('filesize_approx') or 0) > settings.max_download_bytes:
            return 'Video size exceeds the configured limit'
    with SafeProxy(byte_limit=settings.max_download_bytes) as proxy:
        options = {
            'proxy': proxy.url, 'socket_timeout': 30, 'retries': 0, 'fragment_retries': 0,
            'noplaylist': True, 'allowed_extractors': ['TikTok.*','Instagram.*','Youtube.*'],
            'format': 'best[height<=?720][protocol=https]/best[height<=?720][protocol=http]',
            'outtmpl': str(workdir / 'source.%(ext)s'), 'logger': Quiet(), 'quiet': True,
            'match_filter': limit, 'max_filesize': settings.max_download_bytes,
            'progress_hooks': [progress], 'writesubtitles': True, 'writeautomaticsub': True,
            'subtitleslangs': ['en'], 'subtitlesformat': 'vtt', 'cachedir': False,
            'ignore_no_formats_error': instagram_post,
            'enable_file_urls': False, 'js_runtimes': {}, 'remote_components': [],
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                if instagram_post:
                    downloader.add_info_extractor(InstagramSlidesIE())
                    info = downloader.extract_info(url, download=False, process=False)
                    if info and (info.get('_vid2idea_image') or info.get('_type') == 'playlist'):
                        return read_slides(info, url, settings, workdir, proxy, options)
                else:
                    info = downloader.extract_info(url, download=False)
                if not info or info.get('_type') in ('playlist', 'multi_video'):
                    raise SourceError('unsupported_video')
                if limit(info):
                    raise SourceError('video_limit')
                info = downloader.process_ie_result(info, download=True)
                path = Path(downloader.prepare_filename(info))
        except SourceError:
            raise
        except Exception:
            raise proxy.error or SourceError('video_unavailable') from None
    return read_video_file(path, info, settings, workdir, url)[0]


def read_video_file(path, info, settings, workdir, url):
    if not path.is_file():
        raise SourceError('video_unavailable')
    if path.stat().st_size > settings.max_download_bytes:
        raise SourceError('download_limit')
    duration = float(run_media(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)]).decode().strip())
    if not 0 < duration <= settings.max_video_seconds:
        raise SourceError('video_limit')
    gaps, captions, transcript, frames = [], '', '', []
    for caption in workdir.glob('*.vtt'):
        lines = caption.read_text(errors='replace').splitlines()
        captions = '\n'.join(dict.fromkeys(re.sub(r'<[^>]+>', '', line).strip() for line in lines if line and not re.match(r'^(WEBVTT|Kind:|Language:|\d|NOTE|STYLE)', line)))[:48000]
        break
    if not captions and info.get('acodec') != 'none':
        try:
            audio = workdir / 'audio.wav'
            run_media(['ffmpeg','-nostdin','-v','error','-y','-i',str(path),'-vn','-ar','16000','-ac','1',str(audio)])
            transcript = transcribe_audio(audio, settings)
        except SourceError:
            gaps.append('Speech could not be transcribed.')
    try:
        interval = max(duration / 90, 1)
        run_media(['ffmpeg','-nostdin','-v','error','-y','-i',str(path),'-vf',f'fps=1/{interval},scale=1600:1600:force_original_aspect_ratio=decrease','-frames:v','90',str(workdir / 'frame-%03d.jpg')])
        dense_frames = sorted(workdir.glob('frame-*.jpg'))[:90]
        frames,ocr_text,images,ocr_gaps=scan_frame_text(dense_frames,interval)
        gaps.extend(ocr_gaps)
    except SourceError:
        gaps.append('Visual frames could not be sampled.')
    if not frames and not captions and not transcript:
        raise SourceError('no_video_evidence')
    gaps.append('Only sampled moments are inspected; details between frames may be missed.')
    evidence=combine_evidence(captions, transcript, frames, gaps)
    evidence.source_url=url
    evidence.ocr_text=ocr_text if 'ocr_text' in locals() else ''
    evidence.images=images if 'images' in locals() else []
    if evidence.ocr_text:
        evidence.kinds.append(EvidenceKind.on_screen_text)
        evidence.text=evidence.text[:23000]+'\n\nOn-screen text (OCR):\n'+evidence.ocr_text
    description=info.get('description') or ''
    if description:
        evidence.text=(evidence.text+'\n\nCreator description:\n'+description[:1000])[:48000]
    return evidence, duration
