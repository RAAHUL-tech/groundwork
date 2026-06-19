"""
Upload routes — presigned S3 PUT URL only.

Flow:
  1. POST /upload/presign  → create pending room_scan, return presigned PUT URL
  2. Mobile PUT <upload_url> directly to S3 (bypasses Flask)
  3. Mobile POST /estimate  → verify S3 object, enqueue vision pipeline
"""
from flask import Blueprint, request, jsonify, g
from app import limiter
from middleware.auth import optional_auth

from services.s3_storage import build_upload_key, generate_presigned_put, s3_uri, is_image, is_audio
from models.supabase_models import create_room_scan

upload_bp = Blueprint('upload', __name__)

PRESIGN_TTL = 900  # seconds presigned URL is valid


@upload_bp.post('/upload/presign')
@limiter.limit('30 per minute')
@optional_auth
def presign():
    """
    Generate a presigned S3 PUT URL and create a pending room_scan record.

    Request:
    {
        "file_name":    "kitchen.jpg",
        "content_type": "image/jpeg",
        "project_id":   "<uuid>",       // optional
        "room_label":   "Kitchen",      // optional
        "room_scan_id": "<uuid>"        // optional — reuse existing scan (multi-image)
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

    file_name    = data.get('file_name', 'upload.jpg')
    content_type = data.get('content_type', 'image/jpeg')
    from config import Config
    project_id   = data.get('project_id') or Config.DEV_PROJECT_ID
    room_label   = data.get('room_label') or None
    room_scan_id = data.get('room_scan_id') or None

    if not content_type:
        return jsonify({'error': 'content_type is required'}), 400

    s3_key     = build_upload_key(content_type, file_name)
    upload_url = generate_presigned_put(s3_key, content_type, PRESIGN_TTL)

    # Audio uploads are not associated with a room_scan — the s3_key is passed
    # directly to POST /estimate as s3_audio_key and handled by the Celery worker.
    if is_audio(content_type):
        return jsonify({
            'upload_url':   upload_url,
            's3_key':       s3_key,
            'room_scan_id': room_scan_id or None,
            'expires_in':   PRESIGN_TTL,
        }), 200

    if room_scan_id:
        # Multi-image flow: append to existing scan instead of creating orphans
        from models.supabase_models import get_room_scan, update_room_scan
        scan = get_room_scan(room_scan_id)
        if not scan:
            return jsonify({'error': f'room_scan not found: {room_scan_id}'}), 404
        updates: dict = {}
        if is_image(content_type):
            urls = list(scan.get('image_urls') or [])
            urls.append(s3_uri(s3_key))
            updates['image_urls'] = urls
        else:
            updates['video_url'] = s3_uri(s3_key)
        if updates:
            update_room_scan(room_scan_id, **updates)
        scan_id = room_scan_id
    else:
        scan = create_room_scan(
            project_id=project_id,
            room_label=room_label,
            image_urls=[s3_uri(s3_key)] if is_image(content_type) else [],
            video_url=s3_uri(s3_key) if not is_image(content_type) else None,
            status='pending',
        )
        scan_id = scan['id']

    return jsonify({
        'upload_url':   upload_url,
        's3_key':       s3_key,
        'room_scan_id': scan_id,
        'expires_in':   PRESIGN_TTL,
    }), 200
