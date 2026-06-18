"""
Local YOLOv8s object detection — replaces Roboflow hosted inference.
Uses ultralytics YOLOv8s pretrained on COCO80. First call downloads
model weights (~22 MB) and caches them for subsequent runs.
"""
import io
import logging
import threading
import time
from base64 import b64decode

logger = logging.getLogger(__name__)

# COCO class name → internal label (None = skip, not construction-relevant)
# Only appliances, fixtures, and plumbing are directly estimable from COCO.
# Room-context items (furniture) are prefixed _ and excluded from estimate.
COCO_MAP: dict[str, str | None] = {
    'refrigerator': 'refrigerator',
    'oven':         'range',
    'microwave':    'microwave',
    'sink':         'sink',
    'toilet':       'toilet',
    # Room-type hints — detected but not priced
    'couch':        '_living_room',
    'bed':          '_bedroom',
    'dining table': '_dining_room',
    'chair':        '_chair',
    'tv':           '_tv',
    # Everything else → None (skip)
}

# Real-world dimensions for known COCO objects — used to calibrate depth scale
KNOWN_SIZES_FT: dict[str, dict] = {
    'refrigerator': {'width': 2.50, 'height': 5.83},   # 30" × 70"
    'range':        {'width': 2.50, 'height': 4.00},   # 30" × 48"
    'microwave':    {'width': 1.83, 'height': 1.00},   # 22" × 12"
    'toilet':       {'width': 1.25, 'height': 2.50},   # 15" × 30"
    'sink':         {'width': 1.50, 'height': 0.67},   # 18" × 8"
}

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from ultralytics import YOLO
                logger.info("[yolo] loading YOLOv8s (COCO pretrained)...")
                t0 = time.monotonic()
                _model = YOLO('yolov8s.pt')
                logger.info("[yolo] ✓ model ready in %.1fs", time.monotonic() - t0)
    return _model


def detect_objects(image_b64: str) -> list[dict]:
    """
    Run YOLOv8s on a base64-encoded JPEG image.
    Returns list of {label, confidence, bounding_box, known_size_ft?}.
    """
    from PIL import Image
    model = _get_model()

    img_bytes = b64decode(image_b64)
    image = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    img_w, img_h = image.size

    t0 = time.monotonic()
    results = model(image, conf=0.25, iou=0.45, verbose=False)
    elapsed_ms = (time.monotonic() - t0) * 1000

    detections: list[dict] = []
    for r in results:
        for box in r.boxes:
            coco_name = r.names[int(box.cls[0])]
            label = COCO_MAP.get(coco_name)
            if label is None:
                continue        # not a class we care about
            conf = round(float(box.conf[0]), 3)

            # Normalised bounding box [0,1]
            x1, y1, x2, y2 = box.xyxyn[0].tolist()
            bbox = {
                'x': round(x1, 4),
                'y': round(y1, 4),
                'w': round(x2 - x1, 4),
                'h': round(y2 - y1, 4),
            }

            det: dict = {
                'label':        label,
                'coco_class':   coco_name,
                'confidence':   conf,
                'bounding_box': bbox,
                'is_room_hint': label.startswith('_'),
            }

            # Attach known real-world size for depth calibration
            clean = label.lstrip('_')
            if clean in KNOWN_SIZES_FT:
                det['known_size_ft'] = KNOWN_SIZES_FT[clean]

            detections.append(det)

    logger.info("[yolo] ✓ %.0fms  %d detection(s)  img=%dx%d",
                elapsed_ms, len(detections), img_w, img_h)
    for d in detections:
        logger.info("[yolo]   %-18s  conf=%.2f  box=(%.2f,%.2f,%.2f,%.2f)",
                    d['label'], d['confidence'],
                    d['bounding_box']['x'], d['bounding_box']['y'],
                    d['bounding_box']['w'], d['bounding_box']['h'])
    return detections


def detect_objects_multi(image_b64_list: list[str]) -> list[dict]:
    """
    Run YOLO on up to the first 3 images; merge results keeping the
    highest-confidence detection per label.
    """
    best: dict[str, dict] = {}
    for b64 in image_b64_list[:3]:
        try:
            for det in detect_objects(b64):
                label = det['label']
                if label not in best or det['confidence'] > best[label]['confidence']:
                    best[label] = det
        except Exception as exc:
            logger.warning("[yolo] detection failed for one image: %s", exc)

    results = list(best.values())
    # Separate construction items from room-hint items
    construction = [d for d in results if not d['is_room_hint']]
    hints = [d for d in results if d['is_room_hint']]
    logger.info("[yolo] merged: %d construction items, %d room hints",
                len(construction), len(hints))
    return results
