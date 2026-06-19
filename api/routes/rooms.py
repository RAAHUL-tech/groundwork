"""
Multi-room aggregation routes.

POST /rooms        — link a completed estimate to a project; return aggregate summary
GET  /projects     — list all projects (for the mobile project picker)
GET  /projects/:id — get a single project with full room aggregate
"""
import logging

from flask import Blueprint, request, jsonify
from app import limiter

logger = logging.getLogger(__name__)

rooms_bp = Blueprint('rooms', __name__)


@rooms_bp.post('/rooms')
@limiter.limit('30 per minute')
def add_room():
    """
    Link a completed room scan to an existing project.

    Body:
    {
        "project_id":      "<uuid>",
        "estimate_job_id": "<celery-task-id>",
        "room_label":      "Master Bathroom"   // optional override
    }

    Response 200:
    {
        "id": ..., "name": ..., "rooms": [...],
        "aggregate": { "room_count", "subtotal", "mobilization", "grand_total" }
    }
    """
    data = request.get_json(silent=True) or {}

    project_id          = (data.get('project_id') or '').strip()
    estimate_job_id     = (data.get('estimate_job_id') or '').strip()
    room_label_override = (data.get('room_label') or '').strip()

    if not project_id:
        return jsonify({'error': 'project_id is required'}), 400
    if not estimate_job_id:
        return jsonify({'error': 'estimate_job_id is required'}), 400

    # ── Fetch estimate result from Redis via Celery ───────────────────────────
    try:
        from celery_worker import celery_app
        task = celery_app.AsyncResult(estimate_job_id)
    except Exception as exc:
        logger.error("[rooms] could not connect to Celery: %s", exc)
        return jsonify({'error': 'Could not reach task queue'}), 503

    if task.state != 'SUCCESS':
        return jsonify({
            'error': (
                f'Estimate not ready (state: {task.state}). '
                'Wait for the analysis to complete before adding to a project.'
            )
        }), 422

    result         = task.result or {}
    room_scan_id   = result.get('_room_scan_id')
    estimate_db_id = result.get('_estimate_db_id')
    total_estimate = float(result.get('total_estimate') or 0)
    room_type      = result.get('room_type', 'room')

    room_label = room_label_override or room_type.replace('_', ' ').title()

    logger.info(
        "[rooms] linking  project=%s  room_scan=%s  estimate=%s  label=%s  total=%.0f",
        project_id, room_scan_id, estimate_db_id, room_label, total_estimate,
    )

    # ── Persist the link and return aggregate ─────────────────────────────────
    try:
        from models.supabase_models import add_room_to_project
        aggregate = add_room_to_project(
            project_id=project_id,
            room_scan_id=room_scan_id,
            estimate_id=estimate_db_id,
            room_label=room_label,
            total_estimate=total_estimate,
        )
    except Exception as exc:
        logger.error("[rooms] DB error: %s", exc)
        return jsonify({'error': f'Database error: {exc}'}), 500

    if not aggregate:
        return jsonify({'error': 'Project not found'}), 404

    return jsonify(aggregate), 200


@rooms_bp.get('/projects')
@limiter.limit('60 per minute')
def list_projects():
    """
    Return all projects for the mobile project-picker.
    Phase 1: no auth filter. Phase 2 will scope by user_id from JWT.
    """
    try:
        from models.supabase_models import list_projects_all
        projects = list_projects_all()
        return jsonify(projects), 200
    except Exception as exc:
        logger.warning("[projects] list failed: %s", exc)
        return jsonify([]), 200


@rooms_bp.get('/projects/<project_id>')
@limiter.limit('60 per minute')
def get_project(project_id: str):
    """Return a single project with its room list and aggregate cost summary."""
    try:
        from models.supabase_models import get_project_aggregate
        aggregate = get_project_aggregate(project_id)
        if not aggregate:
            return jsonify({'error': 'Project not found'}), 404
        return jsonify(aggregate), 200
    except Exception as exc:
        logger.error("[projects] get failed: %s", exc)
        return jsonify({'error': str(exc)}), 500
