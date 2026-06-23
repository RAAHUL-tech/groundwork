import os
import sys

# Ensure the api/ root is always on sys.path regardless of how the worker is launched.
# Forked Celery workers can inherit a stripped sys.path that drops CWD ('').
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from celery import Celery
from config import Config
from logging_config import configure_logging

configure_logging()

celery_app = Celery(
    'groundwork',
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
    include=[
        'tasks.vision_pipeline',
        'tasks.proposal_task',
    ],
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    result_expires=Config.ESTIMATE_CACHE_TTL,
    worker_prefetch_multiplier=1,   # one task at a time per worker slot
    task_acks_late=True,            # ack only after task succeeds
)
