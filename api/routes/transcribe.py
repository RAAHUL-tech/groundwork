"""
POST /transcribe — synchronous local Whisper transcription.
Accepts multipart/form-data with an 'audio' file field.
Returns {"transcript": "..."} within ~2–8 s for typical voice notes.
"""
import logging

from flask import Blueprint, jsonify, request

transcribe_bp = Blueprint("transcribe", __name__)
logger = logging.getLogger(__name__)


@transcribe_bp.post("/transcribe")
def transcribe_audio():
    if "audio" not in request.files:
        return jsonify({"error": "Missing 'audio' file field in multipart form"}), 400

    audio_file = request.files["audio"]
    filename = audio_file.filename or "audio.m4a"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "m4a"

    audio_bytes = audio_file.read()
    if not audio_bytes:
        return jsonify({"error": "Empty audio file"}), 400

    logger.info("[transcribe] received %d bytes  file=%s  ext=%s",
                len(audio_bytes), filename, ext)

    try:
        from services.whisper_transcribe import transcribe
        text = transcribe(audio_bytes, file_ext=ext)
        return jsonify({"transcript": text})
    except Exception as exc:
        logger.error("[transcribe] ✗ failed: %s", exc, exc_info=True)
        return jsonify({"error": f"Transcription failed: {exc}"}), 500
