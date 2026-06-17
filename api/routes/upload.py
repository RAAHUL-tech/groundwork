"""
Upload routes — presigned S3 PUT + confirm.

Mobile upload flow:
  1. POST /upload/presign  → creates room_scan row, returns presigned PUT URL
  2. Mobile PUT <upload_url> with raw file bytes directly to S3
  3. POST /upload/confirm  → verifies S3 object exists, enqueues vision pipeline
  4. Mobile polls GET /estimate/status/<job_id>
"""
from flask import Blueprint, request, jsonify
from app import limiter
# from middleware.auth import require_auth  ← enable in Phase 2 auth enforcement

from services.s3_storage import (
    build_upload_key,
    generate_presigned_put,
    object_exists,
    s3_uri,
    is_image,
)
from models.supabase_models import create_room_scan, update_room_scan, get_room_scan

upload_bp = Blueprint('upload', __name__)

PRESIGN_TTL = 900   # seconds the presigned URL stays valid


@upload_bp.post('/upload/presign')
@limiter.limit('30 per minute')
# @require_auth
def presign():
    """
    Return a presigned S3 PUT URL and create a pending room_scan record.

    Request body:
    {
        "file_name":    "kitchen.jpg",
        "content_type": "image/jpeg",
        "project_id":   "<uuid>",      // optional
        "room_label":   "Kitchen"      // optional
    }

    Response 200:
    {
        "upload_url":   "https://s3.amazonaws.com/...",
        "s3_key":       "uploads/images/<uuid>/kitchen.jpg",
        "room_scan_id": "<uuid>",
        "expires_in":   900
    }
    """
    data = request.get_json(silent=True) or {}

    file_name = data.get('file_name', 'upload.jpg')
    content_type = data.get('content_type', 'image/jpeg')
    project_id = data.get('project_id')
    room_label = data.get('room_label')

    if not content_type:
        return jsonify({'error': 'content_type is required'}), 400

    # Build unique S3 key and generate presigned URL
    s3_key = build_upload_key(content_type, file_name)
    upload_url = generate_presigned_put(s3_key, content_type, PRESIGN_TTL)

    # Always create a room_scan — project_id is optional (null until user assigns one)
    scan = create_room_scan(
        project_id=project_id or None,
        room_label=room_label,
        image_urls=[s3_uri(s3_key)] if is_image(content_type) else [],
        video_url=s3_uri(s3_key) if not is_image(content_type) else None,
        status='pending',
    )
    room_scan_id = scan['id']

    return jsonify({
        'upload_url':   upload_url,
        's3_key':       s3_key,
        'room_scan_id': room_scan_id,
        'expires_in':   PRESIGN_TTL,
    }), 200


@upload_bp.post('/upload/confirm')
@limiter.limit('20 per minute')
# @require_auth
def confirm():
    """
    Called by the mobile client after the S3 PUT completes.
    Verifies the file exists, updates room_scan, and kicks off the vision pipeline.

    Request body (single key):
    {
        "room_scan_id":      "<uuid>",
        "s3_key":            "uploads/images/...",
        "tier":              "standard",
        "zip_code":          "90210",
        "voice_transcript":  "...",
        "room_hints":        ["kitchen"]
    }

    Request body (multi-image library upload):
    {
        "room_scan_id": "<uuid>",
        "s3_keys":      ["uploads/images/a/1.jpg", "uploads/images/b/2.jpg"],
        "tier":         "standard"
    }

    Response 202:
    {
        "job_id":                  "<celery-uuid>",
        "status":                  "processing",
        "poll_url":                "/estimate/status/<job_id>",
        "estimated_wait_seconds":  15
    }
    """
    data = request.get_json(silent=True) or {}

    room_scan_id   = data.get('room_scan_id')
    s3_key         = data.get('s3_key')           # single key (camera capture)
    s3_keys_multi  = data.get('s3_keys', [])      # multiple keys (library upload)

    # Merge: normalise to one list of keys
    all_keys: list[str] = s3_keys_multi if s3_keys_multi else ([s3_key] if s3_key else [])

    if not all_keys:
        return jsonify({'error': 's3_key or s3_keys is required'}), 400

    # Verify every file was actually uploaded (stop early on first missing)
    for key in all_keys:
        if not object_exists(key):
            return jsonify({
                'error': 'File not found in S3. Complete the upload before confirming.',
                's3_key': key,
            }), 409

    tier             = data.get('tier', 'standard')
    zip_code         = data.get('zip_code', '90210')
    voice_transcript = data.get('voice_transcript')
    room_hints       = data.get('room_hints', [])

    # Split keys by media type
    s3_image_keys = [k for k in all_keys if not k.startswith('uploads/videos/')]
    s3_video_key  = next((k for k in all_keys if k.startswith('uploads/videos/')), None)

    # Fetch project_id from room_scan if we have one
    project_id = None
    if room_scan_id:
        scan = get_room_scan(room_scan_id)
        if scan:
            project_id = scan.get('project_id')

    from tasks.vision_pipeline import run_vision_pipeline

    task = run_vision_pipeline.delay(
        images=[],
        s3_image_keys=s3_image_keys,
        s3_video_key=s3_video_key,
        video_url=(s3_uri(s3_video_key) if s3_video_key else None),
        voice_transcript=voice_transcript,
        room_hints=room_hints,
        tier=tier,
        zip_code=zip_code,
        project_id=project_id,
        room_scan_id=room_scan_id,
    )

    # Update room_scan with job ID and status
    if room_scan_id:
        update_room_scan(
            room_scan_id,
            celery_job_id=task.id,
            status='processing',
        )

    return jsonify({
        'job_id': task.id,
        'status': 'processing',
        'poll_url': f'/estimate/status/{task.id}',
        'estimated_wait_seconds': 15,
    }), 202
