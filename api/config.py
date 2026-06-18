import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
    DEBUG = FLASK_ENV == 'development'

    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Celery (same Redis instance for both broker and result backend)
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_CONCURRENCY = int(os.getenv('CELERY_CONCURRENCY', '4'))

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
    SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET', '')

    # AI APIs
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    ROBOFLOW_API_KEY = os.getenv('ROBOFLOW_API_KEY', '')
    ROBOFLOW_MODEL_ID = os.getenv('ROBOFLOW_MODEL_ID', 'construction-objects/3')

    # Pricing
    SERPAPI_KEY = os.getenv('SERPAPI_KEY', '')

    # AWS S3
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    S3_BUCKET = os.getenv('S3_BUCKET', 'groundwork-uploads')
    S3_REGION = os.getenv('S3_REGION', 'us-east-2')

    # Cache TTLs (seconds)
    ESTIMATE_CACHE_TTL = int(os.getenv('ESTIMATE_CACHE_TTL_SECONDS', '86400'))
    SERPAPI_CACHE_TTL = int(os.getenv('SERPAPI_CACHE_TTL_SECONDS', '21600'))

    # Dev / testing fallback — hardcoded Supabase project used when no
    # project_id is supplied by the client (testing without auth).
    DEV_PROJECT_ID = os.getenv('DEV_PROJECT_ID', 'bcc766c8-36dc-4810-b333-457bde439440')
