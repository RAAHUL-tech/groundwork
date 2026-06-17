import logging
from celery_worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='tasks.generate_proposal')
def generate_proposal(self, estimate_job_id: str, contractor: dict, client: dict,
                      payment_terms: str, valid_days: int) -> dict:
    """
    STUB — Phase 5.
    Generate PDF proposal and upload to S3.

    Real steps:
      1. Fetch completed estimate from Redis by estimate_job_id
      2. Build ReportLab PDF with contractor letterhead
      3. Upload PDF to S3
      4. Persist proposal record to Supabase
      5. Return { proposal_id, pdf_url, expires_at }
    """
    job_id = self.request.id
    logger.info(f"[generate_proposal] STUB  job={job_id}  estimate={estimate_job_id}")
    return {
        'stub': True,
        'proposal_id': f'stub-{job_id}',
        'pdf_url': None,
        'message': 'PDF generation coming in Phase 5',
    }
