from flask import Blueprint, request, jsonify
from app import limiter
# from middleware.auth import require_auth  ← enable in Phase 2

estimate_bp = Blueprint('estimate', __name__)


@estimate_bp.post('/estimate')
@limiter.limit('10 per minute')
# @require_auth                             ← enable in Phase 2
def create_estimate():
    """
    Enqueue a vision analysis job and return immediately with a job_id.
    The client polls GET /estimate/status/<job_id> until status == 'complete'.
    """
    data = request.get_json(silent=True) or {}

    from tasks.vision_pipeline import run_vision_pipeline

    task = run_vision_pipeline.delay(
        images=data.get('images', []),
        video_url=data.get('video_url'),
        voice_transcript=data.get('voice_transcript'),
        room_hints=data.get('room_hints', []),
        tier=data.get('tier', 'standard'),
        zip_code=data.get('zip_code', '90210'),
        project_id=data.get('project_id'),
    )

    return jsonify({
        'job_id': task.id,
        'status': 'processing',
        'poll_url': f'/estimate/status/{task.id}',
        'estimated_wait_seconds': 12,
    }), 202


@estimate_bp.get('/estimate/status/<job_id>')
def get_estimate_status(job_id: str):
    """
    Poll for Celery task result.
    States: processing | complete | failed
    """
    from celery_worker import celery_app

    task = celery_app.AsyncResult(job_id)

    if task.state == 'PENDING':
        # Task queued but not yet picked up by a worker
        return jsonify({'job_id': job_id, 'status': 'processing'}), 200

    if task.state == 'STARTED':
        return jsonify({'job_id': job_id, 'status': 'processing'}), 200

    if task.state == 'SUCCESS':
        return jsonify({
            'job_id': job_id,
            'status': 'complete',
            'result': task.result,
        }), 200

    if task.state == 'FAILURE':
        return jsonify({
            'job_id': job_id,
            'status': 'failed',
            'error': str(task.result),
        }), 200

    # RETRY or other transient states
    return jsonify({'job_id': job_id, 'status': task.state.lower()}), 200
