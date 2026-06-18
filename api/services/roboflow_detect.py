"""
Roboflow YOLOv8 object detection — B7.

Calls the Roboflow hosted inference API, maps class labels to internal keys,
returns [{label, confidence, bounding_box}] with normalized 0-1 coordinates.
"""
import logging

import requests

from config import Config

logger = logging.getLogger(__name__)

ROBOFLOW_BASE_URL = "https://detect.roboflow.com"
MIN_CONFIDENCE = 0.40   # drop detections below this threshold
MAX_IMAGES = 3          # run detection on at most this many images

# After a 401 or 404, skip all further Roboflow calls in this worker process.
# Avoids wasting 5-6s per image on a misconfigured key/model.
_ROBOFLOW_DISABLED: bool = False
_ROBOFLOW_DISABLE_REASON: str = ''

# Roboflow class label → internal item key
LABEL_MAP: dict[str, str] = {
    # Cabinets
    'cabinet': 'cabinets',
    'cabinets': 'cabinets',
    'upper_cabinet': 'cabinets',
    'lower_cabinet': 'cabinets',
    'kitchen_cabinet': 'cabinets',
    # Countertops
    'counter': 'countertop',
    'countertop': 'countertop',
    'countertops': 'countertop',
    'kitchen_counter': 'countertop',
    'island': 'countertop',
    # Plumbing
    'sink': 'sink',
    'kitchen_sink': 'sink',
    'bathroom_sink': 'sink',
    'faucet': 'sink',
    'toilet': 'toilet',
    'tub': 'tub',
    'bathtub': 'tub',
    'shower': 'shower',
    'shower_pan': 'shower',
    # Appliances
    'refrigerator': 'refrigerator',
    'fridge': 'refrigerator',
    'dishwasher': 'dishwasher',
    'stove': 'range',
    'range': 'range',
    'oven': 'range',
    'cooktop': 'range',
    'microwave': 'microwave',
    # Bathroom fixtures
    'vanity': 'vanity',
    'bathroom_vanity': 'vanity',
    'mirror': 'mirror',
    # Surfaces
    'flooring': 'flooring',
    'floor': 'flooring',
    'tile_floor': 'tile_floor',
    'hardwood': 'flooring',
    'carpet': 'flooring',
    'backsplash': 'backsplash',
    'tile_wall': 'tile_wall',
    'drywall': 'drywall',
    # Openings
    'window': 'window',
    'windows': 'window',
    'door': 'door',
    'interior_door': 'door',
    'exterior_door': 'door',
    # Lighting
    'light': 'lighting_fixture',
    'lighting': 'lighting_fixture',
    'light_fixture': 'lighting_fixture',
    'ceiling_light': 'lighting_fixture',
    'pendant': 'lighting_fixture',
}


def detect_objects(base64_image: str, image_index: int = 1) -> list[dict]:
    """
    Detect objects in a single base64 JPEG image via Roboflow hosted inference.
    """
    import time
    global _ROBOFLOW_DISABLED, _ROBOFLOW_DISABLE_REASON

    if _ROBOFLOW_DISABLED:
        logger.info("[roboflow] skipped (disabled: %s)", _ROBOFLOW_DISABLE_REASON)
        return []

    if not Config.ROBOFLOW_API_KEY or not Config.ROBOFLOW_MODEL_ID:
        logger.warning("[roboflow] ✗ API key or model ID missing — skipping detection")
        _ROBOFLOW_DISABLED = True
        _ROBOFLOW_DISABLE_REASON = "API key or model ID not configured"
        return []

    url = f"{ROBOFLOW_BASE_URL}/{Config.ROBOFLOW_MODEL_ID}"
    logger.info("[roboflow] image[%d] — POST %s", image_index, url)

    t0 = time.monotonic()
    try:
        response = requests.post(
            url,
            params={"api_key": Config.ROBOFLOW_API_KEY},
            data=base64_image,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("[roboflow] image[%d] — HTTP %d  %.0fms",
                    image_index, response.status_code, elapsed)

        if response.status_code in (401, 403):
            msg = response.json().get('message', response.text[:200])
            logger.error("[roboflow] ✗ auth error (%d): %s", response.status_code, msg)
            logger.error("[roboflow] Fix: set ROBOFLOW_API_KEY to a key authorized for "
                         "serverless inference, or update ROBOFLOW_MODEL_ID")
            _ROBOFLOW_DISABLED = True
            _ROBOFLOW_DISABLE_REASON = f"HTTP {response.status_code} auth error"
            return []

        if response.status_code == 404:
            msg = response.json().get('message', response.text[:200])
            logger.error("[roboflow] ✗ model not found (%s): %s", Config.ROBOFLOW_MODEL_ID, msg)
            logger.error("[roboflow] Fix: update ROBOFLOW_MODEL_ID in .env to a model that "
                         "exists in your Roboflow workspace")
            _ROBOFLOW_DISABLED = True
            _ROBOFLOW_DISABLE_REASON = f"model not found: {Config.ROBOFLOW_MODEL_ID}"
            return []

        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        logger.error("[roboflow] image[%d] ✗ request timed out (>10s)", image_index)
        return []
    except requests.exceptions.HTTPError as exc:
        logger.error("[roboflow] image[%d] ✗ HTTP %s: %s",
                     image_index, exc.response.status_code, exc.response.text[:300])
        return []
    except Exception as exc:
        logger.error("[roboflow] image[%d] ✗ unexpected error: %s", image_index, exc)
        return []

    img_w = data.get('image', {}).get('width', 640) or 640
    img_h = data.get('image', {}).get('height', 480) or 480
    predictions = data.get('predictions', [])
    logger.info("[roboflow] image[%d] — %d raw prediction(s) from API (image %dx%d)",
                image_index, len(predictions), img_w, img_h)

    results = []
    skipped = 0
    for pred in predictions:
        confidence = float(pred.get('confidence', 0))
        if confidence < MIN_CONFIDENCE:
            skipped += 1
            continue

        raw_label = str(pred.get('class', '')).lower().replace(' ', '_')
        label = LABEL_MAP.get(raw_label, raw_label)

        cx = pred.get('x', 0) / img_w
        cy = pred.get('y', 0) / img_h
        bw = pred.get('width', 0) / img_w
        bh = pred.get('height', 0) / img_h

        results.append({
            'label': label,
            'confidence': round(confidence, 3),
            'bounding_box': {
                'x': round(max(0.0, cx - bw / 2), 4),
                'y': round(max(0.0, cy - bh / 2), 4),
                'w': round(min(bw, 1.0), 4),
                'h': round(min(bh, 1.0), 4),
            },
        })
        logger.info("[roboflow] image[%d]   ✓ %-20s conf=%.0f%%  raw_label=%s",
                    image_index, label, confidence * 100, raw_label)

    if skipped:
        logger.info("[roboflow] image[%d]   skipped %d prediction(s) below %.0f%% threshold",
                    image_index, skipped, MIN_CONFIDENCE * 100)
    logger.info("[roboflow] image[%d] — %d object(s) kept", image_index, len(results))
    return results


def detect_objects_multi(base64_images: list[str]) -> list[dict]:
    """
    Run detection on up to MAX_IMAGES evenly-sampled frames and merge results.
    Unit items accumulate counts; area/linear items keep highest-confidence bbox.
    """
    if not base64_images:
        logger.warning("[roboflow] detect_objects_multi called with no images")
        return []

    from services.quantity_estimator import UNIT_ITEMS

    sample = _sample(base64_images, MAX_IMAGES)
    logger.info("[roboflow] multi-detect — %d image(s) sampled from %d total (cap=%d)",
                len(sample), len(base64_images), MAX_IMAGES)

    best: dict[str, dict] = {}
    unit_counts: dict[str, int] = {}

    for i, img in enumerate(sample):
        logger.info("[roboflow] ── image %d/%d ──", i + 1, len(sample))
        for det in detect_objects(img, image_index=i + 1):
            label = det['label']
            if label in UNIT_ITEMS:
                unit_counts[label] = unit_counts.get(label, 0) + 1
                if label not in best or det['confidence'] > best[label]['confidence']:
                    best[label] = det
            elif label not in best or det['confidence'] > best[label]['confidence']:
                best[label] = det

    results = []
    for label, det in best.items():
        item = dict(det)
        if label in UNIT_ITEMS and unit_counts.get(label, 0) > 1:
            item['instance_count'] = unit_counts[label]
        results.append(item)

    logger.info("[roboflow] ✓ merged result — %d unique object(s): %s",
                len(results), [r['label'] for r in results])
    return results


def _sample(images: list[str], n: int) -> list[str]:
    if len(images) <= n:
        return images
    step = len(images) / n
    return [images[int(i * step)] for i in range(n)]
