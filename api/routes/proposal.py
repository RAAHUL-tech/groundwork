import logging
from flask import Blueprint, request, jsonify
from app import limiter

logger = logging.getLogger(__name__)
proposal_bp = Blueprint('proposal', __name__)

# Default contractor for the prototype — overridden by request body
_DEFAULT_CONTRACTOR = {
    'name':    'Mike Torres',
    'company': 'Torres Construction LLC',
    'license': 'CA-GC-889234',
    'phone':   '714-555-0192',
    'email':   'mike@torresconstruction.com',
}

_DEFAULT_CLIENT = {
    'name':    'Client',
    'address': 'XXX Street, City, State ZIP',
    'phone':   'xxx-xxx-xxxx',
    'email':   'xxx@client.com',
}


@proposal_bp.post('/proposal')
@limiter.limit('10 per minute')
def create_proposal():
    """
    Generate a PDF proposal from a completed estimate.

    Body:
    {
        "estimate_job_id": "cel-abc123",
        "contractor": { "name", "company", "license", "phone", "email" },
        "client":     { "name", "address", "phone", "email" },
        "payment_terms": "50% deposit, 50% on completion",
        "valid_days": 30
    }

    Response 200:
    { "proposal_id": "prop-...", "pdf_url": "https://...", "expires_at": "..." }
    """
    data = request.get_json(silent=True) or {}

    estimate_job_id = data.get('estimate_job_id', '').strip()
    if not estimate_job_id:
        return jsonify({'error': 'estimate_job_id is required'}), 400

    contractor   = {**_DEFAULT_CONTRACTOR, **(data.get('contractor') or {})}
    client       = {**_DEFAULT_CLIENT,     **(data.get('client') or {})}
    payment_terms = data.get('payment_terms') or '50% deposit due at signing, 50% on completion'
    valid_days    = int(data.get('valid_days') or 30)

    logger.info("[proposal] POST /proposal  estimate_job_id=%s  client=%s",
                estimate_job_id, client.get('name'))

    # Run synchronously — ReportLab PDF builds in < 1 s
    from tasks.proposal_task import generate_proposal
    try:
        result = generate_proposal.apply(
            kwargs=dict(
                estimate_job_id=estimate_job_id,
                contractor=contractor,
                client=client,
                payment_terms=payment_terms,
                valid_days=valid_days,
            )
        ).get(timeout=30)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.exception("[proposal] generation failed: %s", exc)
        return jsonify({'error': 'PDF generation failed. Try again.'}), 500

    return jsonify(result), 200
