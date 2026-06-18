"""
Centralized logging configuration for Flask app and Celery worker.

Format: timestamp | LEVEL | module | message
All groundwork loggers go to stdout at INFO+.
Noisy third-party loggers are quieted to WARNING.
"""
import logging
import sys


def configure_logging(level: str = 'INFO') -> None:
    fmt = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
        datefmt='%H:%M:%S',
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        root.addHandler(handler)
    else:
        # Replace existing handlers so the format is applied
        root.handlers = [handler]

    # Quiet noisy third-party loggers
    for noisy in ('boto3', 'botocore', 'urllib3', 's3transfer',
                   'httpcore', 'httpx', 'celery.utils.functional',
                   'anthropic._base_client'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
