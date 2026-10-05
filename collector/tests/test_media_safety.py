"""Exercise real demuxer behavior: downloaded playlists must not fetch more URLs."""
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vid2idea.urls import SourceError
from vid2idea.videos import run_media


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg/FFprobe not installed')
def test_playlist_cannot_read_another_local_media_file(tmp_path):
    private = tmp_path / 'private.ts'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=32x32:r=10',
                    '-t', '1', '-c:v', 'mpeg2video', '-f', 'mpegts', str(private)], check=True, timeout=15)
    playlist = tmp_path / 'source.m3u8'
    playlist.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:1,\n'
                        'private.ts\n#EXT-X-ENDLIST\n')
    with pytest.raises(SourceError):
        run_media(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', str(playlist)], timeout=10)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg/FFprobe not installed')
def test_regular_mp4_still_probes(tmp_path):
    path = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=32x32:r=10',
                    '-t', '1', '-c:v', 'mpeg4', str(path)], check=True, timeout=15)
    result = run_media(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', str(path)], timeout=10)
    assert 0 < float(result.strip()) <= 2


@pytest.mark.skipif(not shutil.which('ffprobe'), reason='FFprobe not installed')
def test_playlist_cannot_open_network_resources(tmp_path):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_error(404)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        path = tmp_path / 'source.m3u8'
        path.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:1,\n'
                        f'http://127.0.0.1:{server.server_port}/private.ts\n#EXT-X-ENDLIST\n')
        with pytest.raises(SourceError):
            run_media(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', str(path)], timeout=10)
        assert requests == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
