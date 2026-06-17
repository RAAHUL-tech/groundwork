"""
Image preprocessing for the vision pipeline.

Before sending images to Claude Vision or Roboflow:
  1. Auto-rotate using EXIF orientation tag
  2. Strip all EXIF metadata (privacy + size reduction)
  3. Resize so the longest edge ≤ MAX_PX (preserves aspect ratio)
  4. Normalise to RGB JPEG

This runs inside the Celery worker, not in Flask — keeps the API server
fast and moves CPU work to the background.
"""
import base64
import io
import logging
from typing import Optional

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

MAX_PX = 2048       # longest edge; Claude Vision is efficient below this
JPEG_QUALITY = 85   # good enough for vision tasks, ~30–50 % smaller than 95


def preprocess(image_bytes: bytes, max_px: int = MAX_PX) -> bytes:
    """
    Accept raw image bytes (any PIL-supported format).
    Return preprocessed JPEG bytes with EXIF stripped and dimensions capped.
    """
    img = Image.open(io.BytesIO(image_bytes))

    original_size = img.size
    original_mode = img.mode

    # Step 1: Auto-rotate from EXIF orientation (e.g. photos taken in portrait)
    img = ImageOps.exif_transpose(img)

    # Step 2: Normalise colour mode → RGB (handles RGBA, P, CMYK, L, etc.)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Step 3: Resize if needed — thumbnail() keeps aspect ratio and never upscales
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)

    # Step 4: Encode as JPEG (naturally strips all EXIF)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    result = buf.getvalue()

    logger.debug(
        "[preprocess] %s %s → RGB %s  %.1f KB → %.1f KB",
        original_mode, original_size, img.size,
        len(image_bytes) / 1024, len(result) / 1024,
    )
    return result


def to_base64(image_bytes: bytes) -> str:
    """Encode bytes to a base64 string (no data-URL prefix)."""
    return base64.b64encode(image_bytes).decode('utf-8')


def preprocess_to_base64(image_bytes: bytes, max_px: int = MAX_PX) -> str:
    """Preprocess and return a base64 string ready for Claude Vision."""
    return to_base64(preprocess(image_bytes, max_px))


def get_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) without full decode."""
    img = Image.open(io.BytesIO(image_bytes))
    return img.size
