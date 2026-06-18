"""
Monocular depth estimation using Depth Anything V2 Small.

Pipeline:
  1. Run Depth-Anything-V2-Small-hf on the first image → disparity map
  2. If YOLO detected a known-size object, use it to calibrate absolute scale (ft)
  3. Estimate floor area (sq ft) from the floor region of the disparity map
  4. Estimate object dimensions (ft) for each YOLO bounding box
  5. Return structured depth_measurements dict consumed by quantity_estimator

Disparity convention (Depth Anything V2):
  Higher value → object is CLOSER to the camera
  Lower value  → object is FARTHER (wall, floor across the room)
"""
import logging
import math
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

# Smartphone horizontal FOV — used for perspective projection
FOV_H_DEG = 73.0

# Fallback room depth when no calibration anchor is available (feet)
DEFAULT_ROOM_DEPTH_FT = 12.0

_pipe = None
_lock = threading.Lock()


def _get_pipeline():
    global _pipe
    if _pipe is None:
        with _lock:
            if _pipe is None:
                from transformers import pipeline as hf_pipeline
                logger.info("[depth] loading Depth-Anything-V2-Small-hf...")
                t0 = time.monotonic()
                _pipe = hf_pipeline(
                    task="depth-estimation",
                    model="depth-anything/Depth-Anything-V2-Small-hf",
                    device="cpu",
                )
                logger.info("[depth] ✓ model ready in %.1fs", time.monotonic() - t0)
    return _pipe


def estimate_depth_map(image_b64: str) -> tuple[np.ndarray, int, int]:
    """
    Return (disparity_map, img_w, img_h).
    disparity_map is a float32 ndarray shaped (H, W), normalised to [0, 1].
    Higher values are CLOSER to camera.
    """
    from base64 import b64decode
    from PIL import Image
    pipe = _get_pipeline()

    img_bytes = b64decode(image_b64)
    image = Image.open(__import__('io').BytesIO(img_bytes)).convert('RGB')
    img_w, img_h = image.size

    t0 = time.monotonic()
    output = pipe(image)
    elapsed_ms = (time.monotonic() - t0) * 1000

    # predicted_depth is a torch tensor (1, H, W) or (H, W)
    import torch
    raw = output['predicted_depth']
    if isinstance(raw, torch.Tensor):
        raw = raw.detach().cpu().numpy()
    raw = np.squeeze(raw).astype(np.float32)

    # Normalise to [0, 1]
    d_min, d_max = raw.min(), raw.max()
    if d_max > d_min:
        disp = (raw - d_min) / (d_max - d_min)
    else:
        disp = np.zeros_like(raw)

    logger.info("[depth] ✓ %.0fms  map=%s  min=%.3f  max=%.3f",
                elapsed_ms, disp.shape, disp.min(), disp.max())
    return disp, img_w, img_h


def compute_measurements(
    image_b64: str,
    yolo_detections: list[dict],
) -> dict:
    """
    Run depth estimation and return measurement dict:

    {
        "floor_area_sqft":   float,   # visible floor area estimate
        "wall_area_sqft":    float,   # ≈ floor_area × 2.5 (ceiling 8 ft)
        "room_width_ft":     float,
        "room_depth_ft":     float,
        "scale_source":      str,     # "anchor:<label>" | "heuristic"
        "object_dims":       {        # keyed by YOLO label
            "refrigerator": {"width_ft": 2.5, "height_ft": 5.8, "dist_ft": 6.2},
            ...
        },
        "depth_map_available": True,
    }
    """
    try:
        disp, img_w, img_h = estimate_depth_map(image_b64)
    except Exception as exc:
        logger.warning("[depth] depth estimation failed: %s", exc)
        return _fallback()

    fov_h = math.radians(FOV_H_DEG)
    aspect = img_w / img_h
    fov_v = 2 * math.atan(math.tan(fov_h / 2) / aspect)

    # ── Scale calibration ────────────────────────────────────────────────────
    # Try to find an anchor object with known real-world size
    scale_ft_per_disp = None  # feet represented by disp range [0,1]
    scale_source = "heuristic"

    for det in yolo_detections:
        if det.get('is_room_hint'):
            continue
        known = det.get('known_size_ft')
        if not known:
            continue
        bbox = det.get('bounding_box', {})
        bh_frac = bbox.get('h', 0)       # box height as fraction of image height
        by_frac = bbox.get('y', 0)       # box top-y as fraction
        if bh_frac < 0.02:
            continue

        # Median disparity within the bounding box
        y1 = int(by_frac * disp.shape[0])
        y2 = min(int((by_frac + bh_frac) * disp.shape[0]), disp.shape[0])
        x1 = int(bbox.get('x', 0) * disp.shape[1])
        x2 = min(int((bbox.get('x', 0) + bbox.get('w', 0)) * disp.shape[1]), disp.shape[1])
        region = disp[y1:y2, x1:x2]
        if region.size == 0:
            continue
        obj_disp = float(np.median(region))

        # Pinhole model: real_height = 2 * dist * tan(fov_v/2) * box_h_fraction
        # Solve for dist: dist = real_height / (2 * tan(fov_v/2) * bh_frac)
        real_h_ft = known['height']
        dist_ft = real_h_ft / max(2 * math.tan(fov_v / 2) * bh_frac, 1e-6)

        # Map: obj_disp (normalised) ↔ dist_ft
        # Disparity is inverse to distance; we use a simple linear scale for this range
        # scale_ft_per_disp: at disp=0 the scene is DEFAULT_ROOM_DEPTH_FT away
        # at disp=obj_disp it is dist_ft away → fit a simple 2-point linear model
        # disp=1 → dist=near_ft, disp=0 → dist=far_ft
        near_ft = dist_ft
        far_ft = dist_ft / max(obj_disp, 0.05) * 1.0  # rough extrapolation
        scale_ft_per_disp = far_ft - near_ft
        scale_source = f"anchor:{det['label']}"
        logger.info("[depth] ✓ scale calibrated via %s  dist_ft=%.1f  disp=%.2f",
                    det['label'], dist_ft, obj_disp)
        break

    def disp_to_ft(d_norm: float) -> float:
        """Convert normalised disparity to approximate distance in feet."""
        if scale_ft_per_disp is not None:
            # Linear mapping: disp=1 → near, disp=0 → far
            near_ft_val = DEFAULT_ROOM_DEPTH_FT * 0.3
            return near_ft_val + (1.0 - d_norm) * scale_ft_per_disp
        else:
            # Heuristic: disparity=0 ≈ 20 ft, disparity=1 ≈ 2 ft
            return 2.0 + (1.0 - d_norm) * 18.0

    # ── Floor area ───────────────────────────────────────────────────────────
    # Floor is in the bottom 35% of the image; far pixels have LOW disparity
    floor_top = int(disp.shape[0] * 0.65)
    floor_region = disp[floor_top:, :]
    floor_disp = float(np.percentile(floor_region, 20))  # low-disparity = far floor
    floor_dist_ft = disp_to_ft(floor_disp)

    near_disp = float(np.percentile(floor_region, 80))   # near edge of floor
    near_dist_ft = disp_to_ft(near_disp)

    visible_width_ft = 2 * floor_dist_ft * math.tan(fov_h / 2)
    floor_depth_span_ft = abs(floor_dist_ft - near_dist_ft)
    floor_area_sqft = max(40.0, min(visible_width_ft * floor_depth_span_ft, 800.0))

    # Wall area ≈ perimeter × ceiling height (8 ft) ÷ 2 (visible side only)
    wall_area_sqft = floor_area_sqft * 2.5

    # Room dimensions
    far_wall_disp = float(np.percentile(disp[:int(disp.shape[0] * 0.25), :], 20))
    room_depth_ft = min(disp_to_ft(far_wall_disp), 30.0)
    room_width_ft = min(2 * room_depth_ft * math.tan(fov_h / 2), 30.0)

    # ── Per-object dimensions ────────────────────────────────────────────────
    object_dims: dict[str, dict] = {}
    for det in yolo_detections:
        if det.get('is_room_hint'):
            continue
        label = det['label']
        bbox = det.get('bounding_box', {})
        bw = bbox.get('w', 0)
        bh = bbox.get('h', 0)
        if bw < 0.01 or bh < 0.01:
            continue
        y1 = int(bbox.get('y', 0) * disp.shape[0])
        y2 = min(int((bbox.get('y', 0) + bh) * disp.shape[0]), disp.shape[0])
        x1 = int(bbox.get('x', 0) * disp.shape[1])
        x2 = min(int((bbox.get('x', 0) + bw) * disp.shape[1]), disp.shape[1])
        region = disp[y1:y2, x1:x2]
        if region.size == 0:
            continue
        obj_disp_val = float(np.median(region))
        obj_dist_ft = disp_to_ft(obj_disp_val)
        obj_width_ft = 2 * obj_dist_ft * math.tan(fov_h / 2) * bw
        obj_height_ft = 2 * obj_dist_ft * math.tan(fov_v / 2) * bh
        object_dims[label] = {
            'width_ft':  round(obj_width_ft, 2),
            'height_ft': round(obj_height_ft, 2),
            'dist_ft':   round(obj_dist_ft, 1),
        }
        logger.info("[depth]   %s  dist=%.1fft  w=%.1fft  h=%.1fft",
                    label, obj_dist_ft, obj_width_ft, obj_height_ft)

    result = {
        'floor_area_sqft':       round(floor_area_sqft, 1),
        'wall_area_sqft':        round(wall_area_sqft, 1),
        'room_width_ft':         round(room_width_ft, 1),
        'room_depth_ft':         round(room_depth_ft, 1),
        'scale_source':          scale_source,
        'object_dims':           object_dims,
        'depth_map_available':   True,
    }
    logger.info("[depth] measurements: floor=%.0f sqft  wall=%.0f sqft  "
                "room=%.1fx%.1f ft  scale=%s",
                floor_area_sqft, wall_area_sqft,
                room_width_ft, room_depth_ft, scale_source)
    return result


def _fallback() -> dict:
    return {
        'floor_area_sqft':     0.0,
        'wall_area_sqft':      0.0,
        'room_width_ft':       0.0,
        'room_depth_ft':       0.0,
        'scale_source':        'unavailable',
        'object_dims':         {},
        'depth_map_available': False,
    }
