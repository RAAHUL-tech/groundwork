from flask import Blueprint, request, jsonify
from app import limiter
# from middleware.auth import require_auth  ← enable in Phase 2

rooms_bp = Blueprint('rooms', __name__)


@rooms_bp.post('/rooms')
@limiter.limit('20 per minute')
# @require_auth                             ← enable in Phase 2
def add_room():
    """
    STUB — Phase 1.
    Add a completed room scan to an existing project for multi-room aggregation.

    Expected body:
    {
        "project_id": "uuid",
        "room_label": "Master Bathroom",
        "estimate_job_id": "cel-def456"
    }
    """
    data = request.get_json(silent=True) or {}

    # TODO (Phase 5): link room_scan to project, recalculate project total_estimate
    return jsonify({
        'stub': True,
        'message': 'POST /rooms — coming in Phase 5',
        'received': {
            'project_id': data.get('project_id'),
            'room_label': data.get('room_label'),
            'estimate_job_id': data.get('estimate_job_id'),
        },
    }), 202
