import logging
import time
from typing import Optional

from celery_worker import celery_app
from logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# Items valid per room type — prevents hallucinated cross-room items in estimate
_VALID_ROOM_ITEMS: dict[str, set] = {
    'kitchen':    {'cabinets', 'countertop', 'sink', 'range', 'dishwasher', 'refrigerator',
                   'microwave', 'flooring', 'backsplash', 'lighting_fixture', 'window', 'paint', 'drywall'},
    'bathroom':   {'vanity', 'toilet', 'tub', 'shower', 'tile_floor', 'tile_wall', 'mirror',
                   'lighting_fixture', 'faucet', 'flooring', 'paint', 'drywall'},
    'bedroom':    {'flooring', 'paint', 'drywall', 'window', 'door', 'lighting_fixture',
                   'ceiling_fan', 'closet'},
    'living_room':{'flooring', 'paint', 'drywall', 'window', 'door', 'lighting_fixture', 'ceiling_fan'},
    'basement':   {'flooring', 'paint', 'drywall', 'window', 'door', 'lighting_fixture'},
    'laundry':    {'flooring', 'paint', 'drywall', 'window', 'door', 'lighting_fixture', 'sink'},
    'garage':     {'flooring', 'paint', 'drywall', 'window', 'door', 'lighting_fixture'},
    'exterior':   {'window', 'door', 'paint', 'drywall'},
}
# These items are valid regardless of room type (voice-directed removals / installs)
_ALWAYS_VALID_ITEMS = {
    'flooring', 'paint', 'window', 'door', 'lighting_fixture',
    'ac_unit_removal', 'hvac_disconnect', 'ceiling_fan',
}


def _filter_by_room(items: list[dict], room_type: str) -> list[dict]:
    valid = _VALID_ROOM_ITEMS.get(room_type, set()) | _ALWAYS_VALID_ITEMS
    kept, removed = [], []
    for i in items:
        (kept if i.get('label') in valid else removed).append(i)
    if removed:
        logger.info("[vision_pipeline] room filter: removed %d item(s) not valid for '%s': %s",
                    len(removed), room_type, [i['label'] for i in removed])
    return kept


# Fallback detected items when both Roboflow and Claude return nothing
_FALLBACK_DETECTED_ITEMS = [
    {"label": "cabinets",     "confidence": 0.50, "quantity": 18.5, "unit": "linear_ft"},
    {"label": "countertop",   "confidence": 0.50, "quantity": 32,   "unit": "sq_ft"},
    {"label": "flooring",     "confidence": 0.50, "quantity": 144,  "unit": "sq_ft"},
    {"label": "sink",         "confidence": 0.50, "quantity": 1,    "unit": "each"},
]


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

        p_key = preprocessed_key(key)
        upload_bytes(p_key, processed, content_type='image/jpeg')
        logger.info("[preprocess] stored preprocessed → %s", p_key)

        base64_images.append(to_base64(processed))

    return base64_images


def _resolve_project_id(project_id: str | None, room_scan_id: str | None) -> str | None:
    """Inherit project_id from room_scan, then fall back to DEV_PROJECT_ID."""
    if project_id:
        return project_id
    if room_scan_id:
        try:
            from models.supabase_models import get_room_scan
            scan = get_room_scan(room_scan_id)
            if scan and scan.get('project_id'):
                logger.info("[vision_pipeline] inherited project_id=%s from room_scan", scan['project_id'])
                return scan['project_id']
        except Exception as exc:
            logger.warning("[vision_pipeline] could not load room_scan for project_id: %s", exc)
    from config import Config
    logger.info("[vision_pipeline] using DEV_PROJECT_ID=%s", Config.DEV_PROJECT_ID)
    return Config.DEV_PROJECT_ID


def _persist_result(
    room_scan_id: str | None,
    project_id: str | None,
    result: dict,
    tier: str,
    voice_transcript: str | None = None,
) -> None:
    """Write the pipeline result to Supabase estimates + line_items tables."""
    try:
        from models.supabase_models import (
            create_estimate, bulk_create_line_items, update_room_scan,
        )

        project_id = _resolve_project_id(project_id, room_scan_id)
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

        meta = result.get('_breakdown_meta', [])
        line_items = []
        for idx, item in enumerate(result.get('estimate_breakdown', [])):
            meta_item = meta[idx] if idx < len(meta) else {}
            line_items.append({
                'item_label': item['item'],
                'scope_description': item.get('scope'),
                'quantity': item.get('qty'),
                'unit': item.get('unit'),
                'material_unit_cost': item.get('material_unit_cost'),
                'labor_unit_cost': item.get('labor_unit_cost'),
                'total': item.get('total'),
                'hd_price_reference': item.get('hd_price_reference'),
                'source': 'vision',
                'detection_confidence': meta_item.get('_detection_confidence'),
            })
        if line_items:
            bulk_create_line_items(estimate['id'], line_items)

        if room_scan_id:
            scan_updates: dict = {
                'status': 'complete',
                'room_type': result.get('room_type'),
                'room_confidence': result.get('room_confidence'),
                'condition': result.get('condition'),
            }
            if voice_transcript:
                scan_updates['voice_transcript'] = voice_transcript
            update_room_scan(room_scan_id, **scan_updates)

        logger.info("[vision_pipeline] persisted estimate=%s", estimate['id'])

    except Exception as exc:
        logger.error("[vision_pipeline] failed to persist to Supabase: %s", exc)


def _compute_confidence(
    room_confidence: float,
    detected_items: list[dict],
    yolo_count: int,
    voice_transcript: str | None,
    quantity_method: str,
    depth_available: bool = False,
) -> dict:
    has_quantities = sum(1 for d in detected_items if d.get('quantity'))
    qty_score = min(1.0, has_quantities / max(len(detected_items), 1))
    vision_score = (room_confidence + qty_score) / 2
    voice_bonus  = 0.05 if voice_transcript else 0.0
    yolo_bonus   = 0.10 if yolo_count > 0 else 0.0
    depth_bonus  = 0.08 if depth_available else 0.0
    score = min(0.95, vision_score * 0.77 + yolo_bonus + depth_bonus + voice_bonus)

    if score >= 0.80:
        label, range_pct = 'High', 15
    elif score >= 0.60:
        label, range_pct = 'Medium', 20
    else:
        label, range_pct = 'Low', 25

    return {
        'score': round(score, 2),
        'label': label,
        'range_pct': range_pct,
        'factors': {
            'vision_confidence':    round(room_confidence, 2),
            'quantity_method':      quantity_method,
            'voice_scope_provided': bool(voice_transcript),
            'yolo_objects_found':   yolo_count,
            'depth_map_used':       depth_available,
        },
    }


@celery_app.task(bind=True, name='tasks.run_vision_pipeline', max_retries=2)
def run_vision_pipeline(  # noqa: C901
    self,
    images: list,
    voice_transcript: Optional[str] = None,
    room_hints: Optional[list] = None,
    tier: str = 'standard',
    zip_code: str = '90210',
    project_id: Optional[str] = None,
    s3_image_keys: Optional[list] = None,
    s3_video_key: Optional[str] = None,
    room_scan_id: Optional[str] = None,
    user_id: Optional[str] = None,
    ar_measurements: Optional[dict] = None,
) -> dict:
    """
    Main vision analysis pipeline.

    Input paths:
      A) images=["<base64>", ...]             — direct POST /estimate (testing)
      B) s3_image_keys=["uploads/images/..."] — mobile presign flow
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
    logger.info("  ar_measurements: %s", "yes" if ar_measurements else "no")
    logger.info("=" * 60)

    try:
        return _run(
            self, job_id, images, s3_image_keys, s3_video_key,
            voice_transcript, room_hints, tier, zip_code,
            project_id, room_scan_id, ar_measurements,
        )
    except Exception as exc:
        _mark_scan_failed(room_scan_id)
        raise exc


def _run(
    self, job_id, images, s3_image_keys, s3_video_key,
    voice_transcript, room_hints, tier, zip_code, project_id, room_scan_id,
    ar_measurements=None,
):

    pipeline_start = time.monotonic()

    def _step(name: str):
        """Return a context-manager-like dict for step timing."""
        return {'name': name, 't0': time.monotonic()}

    def _done(step: dict, ok: bool = True, detail: str = ''):
        ms = (time.monotonic() - step['t0']) * 1000
        status = '✓' if ok else '✗'
        logger.info("[vision_pipeline] %s %s  %.0fms  %s", status, step['name'], ms, detail)

    # ── Media ingestion ───────────────────────────────────────────────────────
    if s3_image_keys:
        s = _step(f"S3 preprocess ({len(s3_image_keys)} image(s))")
        try:
            processed_b64 = _download_and_preprocess(s3_image_keys)
            images = images + processed_b64
            _done(s, ok=True, detail=f"total images ready: {len(images)}")
        except Exception as exc:
            _done(s, ok=False, detail=str(exc))
            logger.error("[vision_pipeline] S3 image preprocessing failed: %s", exc)

    if s3_video_key:
        s = _step(f"video frame extraction ({s3_video_key})")
        try:
            from services.video_processor import extract_frames_from_s3
            video_frames = extract_frames_from_s3(s3_video_key)
            images = images + video_frames
            _done(s, ok=True, detail=f"frames extracted: {len(video_frames)}  total: {len(images)}")
        except Exception as exc:
            _done(s, ok=False, detail=str(exc))
            logger.error("[vision_pipeline] Video frame extraction failed: %s", exc)

        # Transcribe the video's audio track if no manual voice note was provided
        if not voice_transcript:
            s = _step("video audio transcription (Whisper)")
            try:
                from services.video_processor import extract_audio_bytes_from_s3
                from services.whisper_transcribe import transcribe
                audio_bytes = extract_audio_bytes_from_s3(s3_video_key)
                voice_transcript = transcribe(audio_bytes, file_ext='wav') or None
                _done(s, ok=True, detail=f"transcript ({len(voice_transcript or '')} chars): {(voice_transcript or '')[:80]!r}")
            except Exception as exc:
                _done(s, ok=False, detail=str(exc))
                logger.warning("[vision_pipeline] video audio transcription failed: %s", exc)

    logger.info("[vision_pipeline] total images for AI analysis: %d", len(images))
    input_source = "video" if s3_video_key else ("s3" if s3_image_keys else "base64")
    quantity_method = "ar_measured" if ar_measurements else "pixel_heuristic"

    # ── Step 1: Claude Vision — room classification ───────────────────────────
    s = _step("Step 1 — Claude Vision classification")
    logger.info("[vision_pipeline] %s ...", s['name'])
    classification = {
        "room_type": "unknown", "confidence": 0.0,
        "condition": "fair", "condition_notes": "",
        "detected_features": [], "scope_observations": "",
    }
    step1_ok = False
    try:
        from services.claude_vision import classify_room
        classification = classify_room(
            images,
            room_hints=room_hints,
            voice_transcript=voice_transcript,
        )
        step1_ok = True
        _done(s, ok=True, detail=(
            f"room={classification.get('room_type')}  "
            f"conf={classification.get('confidence', 0):.0%}  "
            f"features={len(classification.get('detected_features', []))}"
        ))
    except Exception as exc:
        _done(s, ok=False, detail=str(exc))
        logger.error("[vision_pipeline] Claude Vision failed: %s", exc)

    room_type       = classification.get('room_type', 'unknown')
    room_confidence = float(classification.get('confidence', 0.5))
    condition       = classification.get('condition', 'fair')

    # ── Step 1.5: Extract structured scope items from voice transcript ────────
    voice_scope_items: list[dict] = []
    voice_detections: list[dict] = []
    if voice_transcript:
        s = _step("Step 1.5 — Voice scope extraction (Claude)")
        logger.info("[vision_pipeline] %s ...", s['name'])
        try:
            from services.claude_vision import extract_voice_scope
            voice_scope_items = extract_voice_scope(voice_transcript, room_type)
            for vi in voice_scope_items:
                label = vi.get('item', '').strip()
                if not label:
                    continue
                voice_detections.append({
                    'label':      label,
                    'confidence': 0.90,
                    'quantity':   vi.get('qty'),
                    'unit':       vi.get('unit'),
                    'is_room_hint': False,
                    'source':     'voice',
                })
            _done(s, ok=True, detail=(
                f"{len(voice_scope_items)} item(s): "
                f"{[v.get('item') for v in voice_scope_items]}"
            ))
        except Exception as exc:
            _done(s, ok=False, detail=str(exc))
            logger.warning("[vision_pipeline] voice scope extraction failed: %s", exc)

    # ── Step 2: Local YOLOv8s — object detection (COCO pretrained) ──────────
    s = _step("Step 2 — YOLOv8s local detection")
    logger.info("[vision_pipeline] %s ...", s['name'])
    yolo_detections: list[dict] = []
    try:
        from services.yolo_detect import detect_objects_multi
        yolo_detections = detect_objects_multi(images)
        construction = [d for d in yolo_detections if not d.get('is_room_hint')]
        _done(s, ok=True, detail=(
            f"total={len(yolo_detections)}  "
            f"construction={len(construction)}  "
            f"labels={[d['label'] for d in construction]}"
        ))
    except Exception as exc:
        _done(s, ok=False, detail=str(exc))
        logger.error("[vision_pipeline] YOLO detection failed: %s", exc)

    # ── Step 3: Depth estimation → floor area + object dimensions ────────────
    s = _step("Step 3 — Depth Anything V2 (floor area + object dims)")
    logger.info("[vision_pipeline] %s ...", s['name'])
    depth_measurements: dict = {}
    try:
        from services.depth_estimator import compute_measurements
        # Use the first available image for depth (best single-frame result)
        first_image = images[0] if images else None
        if first_image:
            depth_measurements = compute_measurements(first_image, yolo_detections)
            _done(s, ok=True, detail=(
                f"floor={depth_measurements.get('floor_area_sqft', 0):.0f} sqft  "
                f"room={depth_measurements.get('room_width_ft', 0):.1f}x"
                f"{depth_measurements.get('room_depth_ft', 0):.1f} ft  "
                f"scale={depth_measurements.get('scale_source', 'n/a')}"
            ))
        else:
            _done(s, ok=False, detail="no images available")
    except Exception as exc:
        _done(s, ok=False, detail=str(exc))
        logger.warning("[vision_pipeline] Depth estimation failed: %s", exc)

    # ── Step 4: Quantity estimation ───────────────────────────────────────────
    # Merge YOLO + voice detections; voice items for labels not already in YOLO
    existing_yolo_labels = {d['label'] for d in yolo_detections if not d.get('is_room_hint')}
    merged_detections = yolo_detections + [
        v for v in voice_detections if v['label'] not in existing_yolo_labels
    ]

    s = _step("Step 4 — Quantity estimation (YOLO + voice + depth + Claude)")
    logger.info("[vision_pipeline] %s ...", s['name'])
    detected_items: list[dict] = []
    try:
        from services.quantity_estimator import estimate_quantities
        detected_items = estimate_quantities(
            merged_detections,
            room_type,
            classification.get('detected_features', []),
            ar_measurements=ar_measurements,
            depth_measurements=depth_measurements or None,
            condition=condition,
        )
        # Filter items that don't belong in this room type
        detected_items = _filter_by_room(detected_items, room_type)
        _done(s, ok=True, detail=f"{len(detected_items)} item(s) with quantities")
        for it in detected_items:
            logger.info("[vision_pipeline]   %-20s qty=%-6s %s",
                        it['label'], it.get('quantity'), it.get('unit', ''))
    except Exception as exc:
        _done(s, ok=False, detail=str(exc))
        logger.error("[vision_pipeline] Quantity estimation failed: %s", exc)

    if not detected_items:
        logger.warning("[vision_pipeline] no detected items — using fallback set")
        detected_items = _FALLBACK_DETECTED_ITEMS

    scope_narrative = (
        classification.get('scope_observations')
        or f"{room_type.replace('_', ' ').title()} remodel based on vision analysis."
    )

    # ── Step 5: Cost engine from detected quantities ──────────────────────────
    s = _step("Step 5 — Pricing engine")
    logger.info("[vision_pipeline] %s ...", s['name'])
    try:
        from services.pricing_engine import calculate_estimate
        pricing = calculate_estimate(
            detected_items, room_type, tier, zip_code, scope_narrative,
        )
        _done(s, ok=True, detail=f"total=${pricing['total_estimate']:,}  lines={len(pricing['estimate_breakdown'])}")
    except Exception as exc:
        _done(s, ok=False, detail=str(exc))
        logger.error("[vision_pipeline] pricing failed: %s", exc)
        pricing = {
            'estimate_breakdown': [],
            '_breakdown_meta': [],
            'subtotal_materials': 0,
            'subtotal_labor': 0,
            'permits': 0,
            'contingency': 0,
            'total_estimate': 0,
            'estimate_range': {'low': 0, 'high': 0},
            'regional_multiplier': 1.0,
            'scope_narrative': scope_narrative,
            'timeline_estimate_weeks': 4,
        }

    yolo_construction_count = len([d for d in yolo_detections if not d.get('is_room_hint')])
    depth_available = bool(depth_measurements.get('depth_map_available'))
    if depth_available and quantity_method == 'pixel_heuristic':
        quantity_method = 'depth_estimated'

    confidence = _compute_confidence(
        room_confidence, detected_items, yolo_construction_count,
        voice_transcript, quantity_method, depth_available,
    )

    result = {
        "room_type":       room_type,
        "room_confidence": room_confidence,
        "condition":       classification.get('condition', 'fair'),
        "condition_notes": classification.get('condition_notes', ''),
        "detected_items":  detected_items,
        "voice_scope_items": [
            {**vi, "source": "voice"}
            for vi in voice_scope_items
        ],
        "estimate_breakdown": pricing['estimate_breakdown'],
        "_breakdown_meta": pricing.get('_breakdown_meta', []),
        "subtotal_materials": pricing['subtotal_materials'],
        "subtotal_labor": pricing['subtotal_labor'],
        "permits": pricing['permits'],
        "contingency": pricing['contingency'],
        "total_estimate": pricing['total_estimate'],
        "estimate_range": pricing['estimate_range'],
        "confidence": confidence,
        "tier": tier,
        "regional_multiplier": pricing['regional_multiplier'],
        "scope_narrative": pricing.get('scope_narrative', scope_narrative),
        "timeline_estimate_weeks": pricing.get('timeline_estimate_weeks', 4),
        "zip_code": zip_code,
        "images_processed": len(images),
        "input_source": input_source,
    }

    # ── Persist to Supabase ───────────────────────────────────────────────────
    s = _step("Supabase persist")
    _persist_result(room_scan_id, project_id, result, tier, voice_transcript)
    _done(s, ok=True)

    # Strip internal metadata before returning to client
    result.pop('_breakdown_meta', None)

    total_ms = (time.monotonic() - pipeline_start) * 1000
    logger.info("=" * 60)
    logger.info("[vision_pipeline] ✓ DONE  job=%s", job_id)
    logger.info("  room         : %s (%.0f%% confidence)", result['room_type'], result['room_confidence'] * 100)
    logger.info("  total        : $%s", f"{result['total_estimate']:,}")
    logger.info("  range        : $%s – $%s",
                f"{result['estimate_range']['low']:,}",
                f"{result['estimate_range']['high']:,}")
    logger.info("  line items   : %d", len(result['estimate_breakdown']))
    logger.info("  source       : %s", result['input_source'])
    logger.info("  elapsed      : %.0fs", total_ms / 1000)
    logger.info("=" * 60)
    return result


def _mark_scan_failed(room_scan_id: str | None) -> None:
    if not room_scan_id:
        return
    try:
        from models.supabase_models import update_room_scan
        update_room_scan(room_scan_id, status='failed')
    except Exception:
        pass
