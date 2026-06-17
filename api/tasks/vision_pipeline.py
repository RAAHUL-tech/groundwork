import logging
import time
from typing import Optional

from celery_worker import celery_app

logger = logging.getLogger(__name__)

# ─── Hardcoded mock result (matches the GET /estimate/status response schema) ─
_MOCK_RESULT = {
    "room_type": "kitchen",
    "room_confidence": 0.94,
    "condition": "fair",
    "condition_notes": "Dated cabinets with original hardware, laminate countertops showing wear.",
    "detected_items": [
        {"label": "cabinets",     "confidence": 0.91, "quantity": 18.5, "unit": "linear_ft"},
        {"label": "countertop",   "confidence": 0.88, "quantity": 32,   "unit": "sq_ft"},
        {"label": "flooring",     "confidence": 0.93, "quantity": 210,  "unit": "sq_ft"},
        {"label": "sink",         "confidence": 0.95, "quantity": 1,    "unit": "each"},
        {"label": "dishwasher",   "confidence": 0.82, "quantity": 1,    "unit": "each"},
        {"label": "refrigerator", "confidence": 0.97, "quantity": 1,    "unit": "each"},
    ],
    "voice_scope_items": [],
    "estimate_breakdown": [
        {
            "item": "Cabinet replacement",
            "scope": "Semi-custom cabinets, like-for-like swap",
            "qty": 18.5, "unit": "lin ft",
            "material_unit_cost": 180, "labor_unit_cost": 65,
            "total": 4532,
            "hd_price_reference": "$159 – $210 / lin ft (Hampton Bay, Home Depot)",
        },
        {
            "item": "Quartz countertops",
            "scope": "Full slab replacement, standard edge profile",
            "qty": 32, "unit": "sq ft",
            "material_unit_cost": 75, "labor_unit_cost": 35,
            "total": 3520,
        },
        {
            "item": "LVP flooring",
            "scope": "Luxury vinyl plank, full room replacement",
            "qty": 210, "unit": "sq ft",
            "material_unit_cost": 4.50, "labor_unit_cost": 4.00,
            "total": 1785,
        },
        {
            "item": "Sink + faucet replacement",
            "scope": "Drop-in sink with mid-range faucet",
            "qty": 1, "unit": "each",
            "material_unit_cost": 450, "labor_unit_cost": 220,
            "total": 670,
        },
        {
            "item": "Interior painting",
            "scope": "Walls + ceiling, 2 coats",
            "qty": 480, "unit": "sq ft",
            "material_unit_cost": 0.80, "labor_unit_cost": 2.20,
            "total": 1440,
        },
    ],
    "subtotal_materials": 8160,
    "subtotal_labor": 4865,
    "permits": 1220,
    "contingency": 1425,
    "total_estimate": 15670,
    "estimate_range": {"low": 13320, "high": 18804},
    "confidence": {
        "score": 0.84,
        "label": "High",
        "range_pct": 15,
        "factors": {
            "vision_confidence": 0.91,
            "quantity_method": "pixel_heuristic",
            "voice_scope_provided": False,
        },
    },
    "tier": "standard",
    "regional_multiplier": 1.00,
    "scope_narrative": (
        "Kitchen remodel including semi-custom cabinet replacement (18.5 LF), "
        "quartz countertop installation (32 SF), luxury vinyl plank flooring (210 SF), "
        "sink and faucet replacement, and full interior painting."
    ),
    "timeline_estimate_weeks": 4,
    "_mock": True,
}


def _download_and_preprocess(s3_keys: list[str]) -> list[str]:
    """
    Download each S3 key, run Pillow preprocessing (resize + EXIF strip),
    upload the preprocessed version back to S3, and return base64 strings
    for the vision API calls.
    """
    from services.s3_storage import download_bytes, upload_bytes, preprocessed_key
    from services.image_preprocessor import preprocess, to_base64

    base64_images = []
    for key in s3_keys:
        logger.info("[preprocess] downloading s3://%s", key)
        raw = download_bytes(key)

        processed = preprocess(raw)

        # Store preprocessed copy alongside original (useful for debugging + reuse)
        p_key = preprocessed_key(key)
        upload_bytes(p_key, processed, content_type='image/jpeg')
        logger.info("[preprocess] stored preprocessed → %s", p_key)

        base64_images.append(to_base64(processed))

    return base64_images


def _persist_result(room_scan_id: str | None, project_id: str | None,
                    result: dict, tier: str) -> None:
    """Write the pipeline result to Supabase estimates + line_items tables."""
    try:
        from models.supabase_models import (
            create_estimate, bulk_create_line_items, update_room_scan,
        )

        conf = result.get('confidence', {})
        er = result.get('estimate_range', {})

        estimate = create_estimate(
            room_scan_id=room_scan_id or None,
            project_id=project_id or None,
            tier=tier,
            subtotal_materials=result.get('subtotal_materials'),
            subtotal_labor=result.get('subtotal_labor'),
            permits=result.get('permits'),
            contingency=result.get('contingency'),
            total_estimate=result.get('total_estimate'),
            estimate_low=er.get('low'),
            estimate_high=er.get('high'),
            confidence_score=conf.get('score'),
            confidence_label=conf.get('label'),
            regional_multiplier=result.get('regional_multiplier'),
            scope_narrative=result.get('scope_narrative'),
            timeline_weeks=result.get('timeline_estimate_weeks'),
            raw_response=result,
        )

        line_items = [
            {
                'item_label': item['item'],
                'scope_description': item.get('scope'),
                'quantity': item.get('qty'),
                'unit': item.get('unit'),
                'material_unit_cost': item.get('material_unit_cost'),
                'labor_unit_cost': item.get('labor_unit_cost'),
                'total': item.get('total'),
                'hd_price_reference': item.get('hd_price_reference'),
                'source': 'vision',
            }
            for item in result.get('estimate_breakdown', [])
        ]
        if line_items:
            bulk_create_line_items(estimate['id'], line_items)

        if room_scan_id:
            update_room_scan(room_scan_id, status='complete')

        logger.info("[vision_pipeline] persisted estimate=%s", estimate['id'])

    except Exception as exc:
        # Don't fail the task over a DB write — the result is still in Redis
        logger.error("[vision_pipeline] failed to persist to Supabase: %s", exc)


@celery_app.task(bind=True, name='tasks.run_vision_pipeline', max_retries=2)
def run_vision_pipeline(  # noqa: C901
    self,
    images: list,                           # base64 strings (legacy / direct POST)
    video_url: Optional[str] = None,
    voice_transcript: Optional[str] = None,
    room_hints: Optional[list] = None,
    tier: str = 'standard',
    zip_code: str = '90210',
    project_id: Optional[str] = None,
    # ── Phase 2: S3-backed upload path ──────────────────────────────────────
    s3_image_keys: Optional[list] = None,   # keys for images uploaded via presign
    s3_video_key: Optional[str] = None,     # key for video uploaded via presign
    room_scan_id: Optional[str] = None,     # Supabase room_scan to update
) -> dict:
    """
    Main vision analysis pipeline.

    Phase 1: mock AI result, correct schema.
    Phase 2: real S3 download + Pillow preprocessing wired in.
    Phase 3+: real Claude Vision / Roboflow / SAM 2 / Whisper / cost engine.

    Two input paths:
      A) images=["<base64>", ...]             — direct POST /estimate (testing)
      B) s3_image_keys=["uploads/images/..."] — mobile presign/confirm flow
    """
    job_id = self.request.id
    room_hints = room_hints or []
    s3_image_keys = s3_image_keys or []

    logger.info("=" * 60)
    logger.info("[vision_pipeline] START  job=%s", job_id)
    logger.info("  base64 images : %d", len(images))
    logger.info("  s3 image keys : %d  %s", len(s3_image_keys), s3_image_keys)
    logger.info("  s3 video key  : %s", s3_video_key)
    logger.info("  voice         : %s", "yes" if voice_transcript else "no")
    logger.info("  room_hints    : %s", room_hints)
    logger.info("  tier          : %s", tier)
    logger.info("  zip_code      : %s", zip_code)
    logger.info("  project_id    : %s", project_id)
    logger.info("  room_scan_id  : %s", room_scan_id)
    logger.info("=" * 60)

    try:
        return _run(self, job_id, images, s3_image_keys, s3_video_key,
                    voice_transcript, room_hints, tier, zip_code,
                    project_id, room_scan_id)
    except Exception as exc:
        _mark_scan_failed(room_scan_id)
        raise exc


def _run(self, job_id, images, s3_image_keys, s3_video_key,
         voice_transcript, room_hints, tier, zip_code, project_id, room_scan_id):

    # ── Phase 2: Download + preprocess S3 images ──────────────────────────────
    if s3_image_keys:
        logger.info("[vision_pipeline] Preprocessing %d S3 image(s)...", len(s3_image_keys))
        try:
            processed_b64 = _download_and_preprocess(s3_image_keys)
            images = images + processed_b64
            logger.info("[vision_pipeline] Preprocessing complete — %d image(s) ready", len(images))
        except Exception as exc:
            logger.error("[vision_pipeline] S3 image preprocessing failed: %s", exc)

    # ── Phase 2: Extract frames from S3 video ─────────────────────────────────
    if s3_video_key:
        logger.info("[vision_pipeline] Extracting frames from video: %s", s3_video_key)
        try:
            from services.video_processor import extract_frames_from_s3
            video_frames = extract_frames_from_s3(s3_video_key)
            images = images + video_frames
            logger.info("[vision_pipeline] Added %d video frame(s) — total images: %d",
                        len(video_frames), len(images))
        except Exception as exc:
            logger.error("[vision_pipeline] Video frame extraction failed: %s", exc)

    # ── Simulate 5-step pipeline ──────────────────────────────────────────────
    # Phase 3 replaces these sleeps with real AI calls.
    steps = [
        ("Classifying room type",   1.4),   # → Claude Vision
        ("Detecting objects",       1.6),   # → Roboflow YOLOv8
        ("Estimating quantities",   1.2),   # → pixel heuristics / AR
        ("Pulling live pricing",    1.0),   # → SerpApi / RSMeans
        ("Generating estimate",     0.8),   # → cost engine + narrator
    ]
    for step_name, duration in steps:
        logger.info("[vision_pipeline] %s...", step_name)
        time.sleep(duration)

    # ── Build result ──────────────────────────────────────────────────────────
    input_source = "video" if s3_video_key else ("s3" if s3_image_keys else "base64")
    result = {
        **_MOCK_RESULT,
        "tier": tier,
        "zip_code": zip_code,
        "images_processed": len(images),
        "input_source": input_source,
    }

    if voice_transcript:
        result["voice_scope_items"] = [
            {
                "item": "voice_scope",
                "action": "replace",
                "source": "voice",
                "notes": voice_transcript[:200],
            }
        ]
        result["confidence"]["factors"]["voice_scope_provided"] = True

    # ── Phase 2: Persist result to Supabase ──────────────────────────────────
    _persist_result(room_scan_id, project_id, result, tier)

    logger.info(
        "[vision_pipeline] DONE  job=%s  total=$%s  source=%s",
        job_id, f"{result['total_estimate']:,}", result['input_source'],
    )
    return result


def _mark_scan_failed(room_scan_id: str | None) -> None:
    if not room_scan_id:
        return
    try:
        from models.supabase_models import update_room_scan
        update_room_scan(room_scan_id, status='failed')
    except Exception:
        pass
