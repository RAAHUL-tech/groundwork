"""
Extract frames from a video file using ffmpeg.

Strategy for room walkthroughs (15–30 sec):
  - Extract up to MAX_FRAMES evenly spaced frames
  - Each frame is preprocessed (resize + EXIF-strip) via Pillow
  - Returns base64 strings ready for Claude Vision
"""
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

MAX_FRAMES = 4
FFMPEG_TIMEOUT = 90   # seconds


def extract_frames_from_s3(s3_video_key: str, max_frames: int = MAX_FRAMES) -> list[str]:
    """
    Download a video from S3, extract evenly-spaced frames with ffmpeg,
    preprocess each frame, and return base64-encoded JPEG strings.

    Falls back to an empty list if ffmpeg is unavailable or the video is unreadable.
    """
    from services.s3_storage import download_bytes
    from services.image_preprocessor import preprocess, to_base64

    logger.info("[video] extracting frames from s3 key: %s", s3_video_key)

    try:
        video_bytes = download_bytes(s3_video_key)
    except Exception as exc:
        logger.error("[video] failed to download video: %s", exc)
        return []

    try:
        return _extract(video_bytes, max_frames, to_base64, preprocess)
    except FileNotFoundError:
        logger.warning("[video] ffmpeg not found — skipping frame extraction")
        return []
    except Exception as exc:
        logger.error("[video] frame extraction failed: %s", exc)
        return []


def _extract(
    video_bytes: bytes,
    max_frames: int,
    to_base64_fn,
    preprocess_fn,
) -> list[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, 'input.mp4')
        frame_glob = os.path.join(tmpdir, 'frame_%04d.jpg')

        with open(video_path, 'wb') as f:
            f.write(video_bytes)

        # Probe duration so we can pick the right interval
        duration = _probe_duration(video_path)
        if duration and duration > 0:
            # Evenly distribute frames across the video length
            interval = max(1, int(duration / max_frames))
            vf = f'fps=1/{interval}'
        else:
            # Unknown duration — take one frame per second, cap at max_frames
            vf = 'fps=1'

        result = subprocess.run(
            [
                'ffmpeg', '-i', video_path,
                '-vf', vf,
                '-vframes', str(max_frames),
                '-q:v', '3',       # JPEG quality 1–31 (lower = better)
                frame_glob,
                '-y',
            ],
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
        )

        if result.returncode != 0:
            logger.warning("[video] ffmpeg exited %d: %s",
                           result.returncode, result.stderr.decode()[-500:])

        frames: list[str] = []
        for i in range(1, max_frames + 1):
            path = os.path.join(tmpdir, f'frame_{i:04d}.jpg')
            if not os.path.exists(path):
                break
            with open(path, 'rb') as f:
                raw = f.read()
            processed = preprocess_fn(raw)
            frames.append(to_base64_fn(processed))
            logger.info("[video] frame %d extracted and preprocessed", i)

        logger.info("[video] extracted %d frame(s) from video", len(frames))
        return frames


def extract_audio_bytes_from_s3(s3_video_key: str) -> bytes:
    """
    Download a video from S3 and extract its audio track as a 16-kHz mono WAV.
    Returns WAV bytes ready for Whisper transcription.
    Raises on download failure or ffmpeg error.
    """
    from services.s3_storage import download_bytes

    logger.info("[video] extracting audio from s3 key: %s", s3_video_key)
    video_bytes = download_bytes(s3_video_key)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, 'input.mp4')
        audio_path = os.path.join(tmpdir, 'audio.wav')

        with open(video_path, 'wb') as f:
            f.write(video_bytes)

        result = subprocess.run(
            [
                'ffmpeg', '-i', video_path,
                '-vn',               # strip video track
                '-ar', '16000',      # 16 kHz — Whisper's native sample rate
                '-ac', '1',          # mono
                '-acodec', 'pcm_s16le',  # uncompressed WAV
                audio_path, '-y',
            ],
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio extraction failed: {result.stderr.decode()[-300:]}"
            )

        with open(audio_path, 'rb') as f:
            audio_bytes = f.read()

    logger.info("[video] extracted %d bytes of audio", len(audio_bytes))
    return audio_bytes


def _probe_duration(video_path: str) -> float | None:
    """Return video duration in seconds using ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path,
            ],
            capture_output=True,
            timeout=10,
        )
        return float(result.stdout.decode().strip())
    except Exception:
        return None
