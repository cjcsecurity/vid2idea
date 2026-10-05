from .urls import SourceError


def transcribe_audio(path, settings):
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(settings.whisper_model, device='cpu', compute_type='int8', cpu_threads=4)
        segments, _ = model.transcribe(str(path), vad_filter=True, beam_size=1)
        return ' '.join(segment.text.strip() for segment in segments)[:48000]
    except Exception:
        raise SourceError('transcription_unavailable') from None
