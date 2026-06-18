"""
Estimate routes.

Flow (mobile):
  POST /upload/presign  → presigned S3 PUT URL + room_scan_id
  PUT  <upload_url>     → mobile uploads directly to S3
  POST /estimate        → verify S3 object, enqueue pipeline, return job_id
  GET  /estimate/status/<job_id>  → poll until complete
"""
from flask import Blueprint, request, jsonify, g
from app import limiter
from middleware.auth import optional_auth

estimate_bp = Blueprint('estimate', __name__)

# Content-types that go through the image path (not video)
_IMAGE_PREFIXES = ('uploads/images/', 'uploads/preprocessed/')


def _is_video_key(key: str) -> bool:
    return key.startswith('uploads/videos/')


@estimate_bp.post('/estimate')
@limiter.limit('10 per minute')
@optional_auth
def create_estimate():
    """
    Enqueue a vision analysis job and return immediately with a job_id.

    Preferred request body (mobile upload flow):
    {
        "s3_key":          "uploads/images/<uuid>/photo.jpg",  // single upload
        "s3_keys":         ["uploads/images/..."],             // multi-image (library)
        "room_scan_id":    "<uuid>",                           // created during presign
        "tier":            "standard",
        "zip_code":        "90210",
        "voice_transcript": "Replace the kitchen cabinets...",
        "room_hints":      ["kitchen"]
    }

    Legacy / testing request body:
    {
        "images": ["<base64>", ...]  // base64 images (no S3)
    }

    Response 202:
    {
        "job_id": "cel-abc123",
        "status": "processing",
        "poll_url": "/estimate/status/cel-abc123",
        "estimated_wait_seconds": 12
    }
    """
    data = request.get_json(silent=True) or {}
    user_id = g.user_id  # None when unauthenticated (optional_auth)

    # ── Resolve S3 keys ───────────────────────────────────────────────────────

    # Single-key path (camera photo or video)
    single_key: str | None = data.get('s3_key') or None
    # Multi-key path (library picker — multiple images sent together)
    multi_keys: list[str] = data.get('s3_keys') or []

    # Combine into one flat list
    all_keys = ([single_key] if single_key else []) + multi_keys

    s3_image_keys = [k for k in all_keys if not _is_video_key(k)]
    s3_video_key  = next((k for k in all_keys if _is_video_key(k)), None)

    room_scan_id = data.get('room_scan_id') or None
    project_id   = data.get('project_id') or None
    tier         = data.get('tier', 'standard')
    zip_code     = data.get('zip_code', '90210')
    voice_transcript = data.get('voice_transcript')

    # Inherit project_id from room_scan when mobile only sent it at presign time
    if room_scan_id and not project_id:
        try:
            from models.supabase_models import get_room_scan
            scan = get_room_scan(room_scan_id)
            if scan:
                project_id = scan.get('project_id') or None
        except Exception:
            pass

    # ── Verify S3 objects exist (best-effort, don't block on failure) ─────────
    if all_keys:
        try:
            from services.s3_storage import object_exists
            for key in all_keys:
                if not object_exists(key):
                    return jsonify({
                        'error': f'S3 object not found: {key}. '
                                 'Ensure the file was uploaded before calling /estimate.'
                    }), 422
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "[estimate] S3 existence check failed (proceeding anyway): %s", exc
            )

    # ── Mark room_scan as processing ──────────────────────────────────────────
    # We enqueue first to get the task ID, then update the room_scan record.
    # (Room scan was created during /upload/presign.)

    from tasks.vision_pipeline import run_vision_pipeline

    task = run_vision_pipeline.delay(
        images=data.get('images', []),
        voice_transcript=voice_transcript,
        room_hints=data.get('room_hints', []),
        tier=tier,
        zip_code=zip_code,
        project_id=project_id,
        s3_image_keys=s3_image_keys,
        s3_video_key=s3_video_key,
        room_scan_id=room_scan_id,
        user_id=user_id,
        ar_measurements=data.get('ar_measurements'),
    )

    # Update room_scan with the Celery job ID so we can link DB record to result
    if room_scan_id:
        try:
            from models.supabase_models import update_room_scan
            scan_updates: dict = {
                'status': 'processing',
                'celery_job_id': task.id,
            }
            if voice_transcript:
                scan_updates['voice_transcript'] = voice_transcript
            if s3_image_keys:
                from services.s3_storage import s3_uri
                from models.supabase_models import get_room_scan
                scan = get_room_scan(room_scan_id)
                existing = (scan or {}).get('image_urls') or []
                new_urls = [s3_uri(k) for k in s3_image_keys]
                scan_updates['image_urls'] = list(dict.fromkeys(existing + new_urls))
            update_room_scan(room_scan_id, **scan_updates)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "[estimate] could not update room_scan status: %s", exc
            )

    return jsonify({
        'job_id':                  task.id,
        'status':                  'processing',
        'poll_url':                f'/estimate/status/{task.id}',
        'estimated_wait_seconds':  12,
    }), 202


@estimate_bp.get('/estimate/status/<job_id>')
def get_estimate_status(job_id: str):
    """
    Poll for Celery task result.
    States: processing | complete | failed
    """
    from celery_worker import celery_app

    task = celery_app.AsyncResult(job_id)

    if task.state in ('PENDING', 'STARTED'):
        return jsonify({'job_id': job_id, 'status': 'processing'}), 200

    if task.state == 'SUCCESS':
        return jsonify({
            'job_id':  job_id,
            'status':  'complete',
            'result':  task.result,
        }), 200

    if task.state == 'FAILURE':
        return jsonify({
            'job_id':  job_id,
            'status':  'failed',
            'error':   str(task.result),
        }), 200

    # RETRY or other transient states
    return jsonify({'job_id': job_id, 'status': task.state.lower()}), 200
