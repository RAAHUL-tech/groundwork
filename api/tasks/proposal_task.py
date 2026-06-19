import uuid
import logging
import datetime

from celery_worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='tasks.generate_proposal')
def generate_proposal(
    self,
    estimate_job_id: str,
    contractor: dict,
    client: dict,
    payment_terms: str,
    valid_days: int,
) -> dict:
    """
    Generate a PDF proposal from a completed estimate.

    Steps:
      1. Fetch estimate result from Celery/Redis by job_id
      2. Build ReportLab PDF
      3. Upload PDF to S3 at proposals/<uuid>.pdf
      4. Generate presigned GET URL (7-day TTL)
      5. Persist proposal record to Supabase
      6. Return { proposal_id, pdf_url, expires_at }
    """
    job_id = self.request.id
    logger.info("[generate_proposal] start  job=%s  estimate=%s", job_id, estimate_job_id)

    # ── 1. Fetch estimate ──────────────────────────────────────────────────────
    estimate = _fetch_estimate(estimate_job_id)
    if not estimate:
        raise ValueError(f"Estimate not found or not yet complete: {estimate_job_id}")

    # ── 2. Build PDF ───────────────────────────────────────────────────────────
    from services.pdf_generator import build_proposal_pdf
    proposal_id = f'prop-{uuid.uuid4().hex[:12]}'
    pdf_bytes = build_proposal_pdf(
        estimate=estimate,
        contractor=contractor,
        client=client,
        payment_terms=payment_terms,
        valid_days=valid_days,
        proposal_id=proposal_id,
    )
    logger.info("[generate_proposal] PDF built  size=%d bytes", len(pdf_bytes))

    # ── 3. Upload PDF to S3 ────────────────────────────────────────────────────
    s3_key = f'proposals/{proposal_id}.pdf'
    try:
        from services.s3_storage import upload_bytes, generate_presigned_get
        upload_bytes(s3_key, pdf_bytes, content_type='application/pdf')
        pdf_url = generate_presigned_get(s3_key, expires_in=604800)  # 7 days
        expires_at = (
            datetime.datetime.utcnow() + datetime.timedelta(days=7)
        ).strftime('%Y-%m-%dT%H:%M:%SZ')
        logger.info("[generate_proposal] PDF uploaded  key=%s", s3_key)
    except Exception as exc:
        logger.warning("[generate_proposal] S3 unavailable (%s) — returning unsigned URL", exc)
        pdf_url = None
        expires_at = None

    # ── 4. Persist to Supabase ─────────────────────────────────────────────────
    estimate_db_id = estimate.get('_estimate_db_id')  # set by vision_pipeline._persist_result
    project_id     = estimate.get('_project_id')
    _persist_proposal(
        proposal_id=proposal_id,
        estimate_job_id=estimate_job_id,
        estimate_db_id=estimate_db_id,
        project_id=project_id,
        pdf_url=pdf_url,
        contractor=contractor,
        client=client,
        payment_terms=payment_terms,
        valid_days=valid_days,
    )

    return {
        'proposal_id': proposal_id,
        'pdf_url':     pdf_url,
        'expires_at':  expires_at,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_estimate(estimate_job_id: str) -> dict | None:
    """Fetch estimate result from Celery backend (Redis)."""
    try:
        result = celery_app.AsyncResult(estimate_job_id)
        if result.state == 'SUCCESS' and result.result:
            return result.result
        logger.warning("[generate_proposal] estimate state=%s", result.state)
        return None
    except Exception as exc:
        logger.error("[generate_proposal] failed to fetch estimate: %s", exc)
        return None


def _persist_proposal(
    proposal_id: str,
    estimate_job_id: str,
    estimate_db_id: str | None,
    project_id: str | None,
    pdf_url: str | None,
    contractor: dict,
    client: dict,
    payment_terms: str,
    valid_days: int,
) -> None:
    if not estimate_db_id or not project_id:
        logger.warning(
            "[generate_proposal] skipping Supabase persist — estimate_db_id=%s project_id=%s "
            "(estimate may not have been persisted yet or job is from a previous session)",
            estimate_db_id, project_id,
        )
        return
    try:
        from models.supabase_models import create_proposal
        valid_until = (
            datetime.date.today() + datetime.timedelta(days=valid_days)
        ).isoformat()
        create_proposal(
            project_id=project_id,
            estimate_id=estimate_db_id,
            pdf_url=pdf_url,
            contractor_snapshot=contractor,
            client_snapshot=client,
            payment_terms=payment_terms,
            valid_until=valid_until,
            status='draft',
        )
        logger.info("[generate_proposal] proposal persisted  id=%s", proposal_id)
    except Exception as exc:
        logger.warning("[generate_proposal] Supabase persist failed: %s", exc)
