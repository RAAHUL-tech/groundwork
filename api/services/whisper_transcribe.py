"""
Local Whisper transcription using faster-whisper (CTranslate2 backend).
Model: whisper-small (~460 MB, downloads on first use, cached in ~/.cache).
No external API calls — runs entirely on CPU inside the Docker container.
"""
import logging
import os
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from faster_whisper import WhisperModel
                logger.info("[whisper] loading 'small' model — first call downloads weights if needed...")
                t0 = time.monotonic()
                _model = WhisperModel("small", device="cpu", compute_type="int8")
                logger.info("[whisper] ✓ model ready in %.1fs", time.monotonic() - t0)
    return _model


def transcribe(audio_bytes: bytes, file_ext: str = "m4a") -> str:
    """
    Transcribe raw audio bytes with the local Whisper small model.
    Supports any format ffmpeg can decode (m4a, mp3, wav, ogg, webm, …).
    Returns the full transcript as a single string.
    """
    model = _get_model()

    suffix = f".{file_ext}" if not file_ext.startswith(".") else file_ext
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        t0 = time.monotonic()
        segments, info = model.transcribe(tmp_path, language="en", beam_size=5)
        # faster-whisper returns a generator — consume it before the temp file is deleted
        text = " ".join(seg.text for seg in segments).strip()
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "[whisper] ✓ transcribed %.0fms  lang=%s(%.0f%%)  chars=%d  text=%r",
            elapsed_ms,
            info.language,
            info.language_probability * 100,
            len(text),
            text[:120],
        )
        return text
    finally:
        os.unlink(tmp_path)
