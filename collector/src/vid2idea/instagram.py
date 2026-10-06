"""Carousel evidence from yt-dlp's Instagram metadata, through the media safety proxy."""
from io import BytesIO
from itertools import islice
from pathlib import Path

import httpx
from PIL import Image, ImageOps
from yt_dlp.extractor.instagram import InstagramIE

from .models import Evidence, EvidenceKind, EvidenceImage
from .ocr import scan_frame_text
from .urls import SourceError, validate_public_url


class InstagramSlidesIE(InstagramIE):
    @classmethod
    def ie_key(cls):
        return 'Instagram'

    def _extract_product_media(self, media):
        # Keep the upstream mapping; only retain the distinction it discards.
        return {**super()._extract_product_media(media), '_vid2idea_image': media.get('media_type') == 1}


def read_slides(info, source_url, settings, workdir, proxy, video_options):
    import yt_dlp
    from .videos import read_video_file
    entries = list(islice(info.get('entries', [info]), 21))
    if len(entries) > 20:
        raise SourceError('carousel_limit')
    frames, numbers, gaps = [], [], []
    total = 0
    video_seconds = 0
    clips = {}
    with httpx.Client(proxy=proxy.url, trust_env=False, follow_redirects=True, timeout=20) as client:
        for number, entry in enumerate(entries, 1):
            if not entry.get('_vid2idea_image'):
                if not entry.get('formats'):
                    gaps.append(f'Slide {number} could not be read as an image or video.')
                    continue
                remaining = settings.max_video_seconds - video_seconds
                if remaining <= 0 or (entry.get('duration') or 0) > remaining:
                    raise SourceError('video_limit')
                folder = workdir / f'slide-{number:03d}'
                folder.mkdir()
                try:
                    options = {**video_options, 'outtmpl': str(folder / 'source.%(ext)s')}
                    with yt_dlp.YoutubeDL(options) as downloader:
                        clip_info = downloader.process_ie_result(entry, download=True)
                        path = Path(downloader.prepare_filename(clip_info))
                    clip, duration = read_video_file(path, {**clip_info, 'description': ''},
                        settings.model_copy(update={'max_video_seconds': remaining}), folder, source_url)
                    video_seconds += duration
                    total += path.stat().st_size
                    if total > settings.max_download_bytes:
                        raise SourceError('download_limit')
                    clips[number] = clip
                except Exception as error:
                    error = proxy.error or error
                    if isinstance(error, SourceError) and error.code in ('unsafe_url', 'download_limit', 'video_limit', 'job_timeout'):
                        raise error from None
                    gaps.append(f'Slide {number} video could not be analyzed.')
                continue
            candidates = entry.get('thumbnails') or []
            if not candidates:
                gaps.append(f'Slide {number} could not be retrieved.')
                continue
            target = max(candidates, key=lambda item: (item.get('width') or 0) * (item.get('height') or 0))['url']
            try:
                target = validate_public_url(target)
                with client.stream('GET', target) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        total += len(chunk)
                        content.extend(chunk)
                        if len(content) > 4 * 1024 * 1024 or total > settings.max_download_bytes:
                            raise SourceError('download_limit')
                with Image.open(BytesIO(content)) as original:
                    if original.format not in ('JPEG', 'PNG', 'WEBP') or original.width * original.height > 16_000_000:
                        raise ValueError('Unsupported source image')
                    image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1600, 1600))
                path = workdir / f'slide-{number:03d}.jpg'
                image.save(path, format='JPEG', quality=85)
                frames.append(path)
                numbers.append(number)
            except SourceError as error:
                if error.code != 'dns_unavailable':
                    raise
                gaps.append(f'Slide {number} could not be retrieved.')
            except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError):
                if proxy.error:
                    raise proxy.error from None
                gaps.append(f'Slide {number} could not be retrieved or decoded.')
    if not frames and not clips:
        raise SourceError('no_image_evidence')
    selected, text, images, ocr_gaps = scan_frame_text(frames, 1, slide_numbers=numbers) if frames else ([], '', [], [])
    gaps.extend(ocr_gaps)
    groups = {number: [path] for number, path in zip(numbers, frames)}
    kinds = [EvidenceKind.image_slides]
    video_text = []
    for number, clip in clips.items():
        groups[number] = clip.frames
        video_text.append(f'[Slide {number} video; times relative to this clip]\n{clip.text}')
        text += f'\n\n[Slide {number} video]\n{clip.ocr_text}' if clip.ocr_text else ''
        gaps.extend(f'Slide {number}: {gap}' for gap in clip.gaps)
        kinds.extend(kind for kind in clip.kinds if kind not in kinds)
    # Preserve representation across slides before adding extra video moments.
    groups = {number: paths for number, paths in sorted(groups.items()) if paths}
    order = list(groups)
    if len(order) > 12:
        order = [order[round(i * (len(order)-1) / 11)] for i in range(12)]
    selected = []
    for depth in range(12):
        for number in order:
            if depth < len(groups[number]) and len(selected) < 12:
                selected.append(groups[number][depth])
    all_frames = [path for paths in groups.values() for path in paths]
    selected.sort(key=all_frames.index)
    labels = {path: number for number, paths in groups.items() for path in paths}
    if len(all_frames) > len(selected):
        gaps.append(f'OCR inspected {len(frames)} photo slides and sampled video frames; only {len(selected)} selected images are supplied for visual analysis.')
    preview_numbers = list(dict.fromkeys(labels[path] for path in selected))[:3]
    previews = [next(path for path in selected if labels[path] == number) for number in preview_numbers]
    images = [EvidenceImage(path=path, caption=f'Instagram slide {labels[path]}' + (' (video still)' if labels[path] in clips else ''))
              for path in previews]
    description = (info.get('description') or '')[:12000]
    if description and EvidenceKind.captions not in kinds:
        kinds.append(EvidenceKind.captions)
    if text and EvidenceKind.on_screen_text not in kinds:
        kinds.append(EvidenceKind.on_screen_text)
    label_text = ', '.join(str(labels[path]) for path in selected)
    content = f'Instagram post: {len(entries)} slides. Selected images in slide order: {label_text}.\n\nCreator caption:\n{description}\n\nSlide text (OCR):\n{text}'
    content += '\n\n' + '\n\n'.join(video_text) if video_text else ''
    if len(content) > 48000 or len(text) > 24000:
        gaps.append('Some extracted slide text could not be included within the text limit.')
    return Evidence(text=content[:48000], kinds=kinds, frames=selected, images=images,
                    ocr_text=text[:24000], gaps=gaps, source_url=source_url)
