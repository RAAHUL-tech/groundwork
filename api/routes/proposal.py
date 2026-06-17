from flask import Blueprint, request, jsonify
from app import limiter
# from middleware.auth import require_auth  ← enable in Phase 2

proposal_bp = Blueprint('proposal', __name__)


@proposal_bp.post('/proposal')
@limiter.limit('10 per minute')
# @require_auth                             ← enable in Phase 2
def create_proposal():
    """
    STUB — Phase 1.
    Generate a PDF proposal from a completed estimate job.

    Expected body:
    {
        "estimate_job_id": "cel-abc123",
        "contractor": { "name", "company", "license", "phone", "email" },
        "client": { "name", "address" },
        "payment_terms": "50% deposit, 50% on completion",
        "valid_days": 30
    }
    """
    data = request.get_json(silent=True) or {}

    # TODO (Phase 5): enqueue proposal_task, generate PDF via ReportLab,
    #                 upload to S3, persist to proposals table
    return jsonify({
        'stub': True,
        'message': 'POST /proposal — coming in Phase 5',
        'received': {
            'estimate_job_id': data.get('estimate_job_id'),
            'contractor': data.get('contractor', {}),
            'client': data.get('client', {}),
        },
    }), 202
