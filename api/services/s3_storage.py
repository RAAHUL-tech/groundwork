"""
S3 operations: presigned PUT URLs, download, upload, key helpers.
Uses the service role credentials from config.
"""
import uuid
import mimetypes
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import Config

# Content-types we treat as images (eligible for Pillow preprocessing)
IMAGE_CONTENT_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png', 'image/webp',
    'image/heic', 'image/heif', 'image/tiff',
}


def _client():
    # endpoint_url pins the presigned URL to the exact regional endpoint,
    # preventing S3's 307 redirect (which breaks presigned signatures).
    return boto3.client(
        's3',
        aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
        region_name=Config.S3_REGION,
        endpoint_url=f'https://s3.{Config.S3_REGION}.amazonaws.com',
    )


# ─── Key helpers ──────────────────────────────────────────────────────────────

def build_upload_key(content_type: str, original_filename: str) -> str:
    """
    Return a unique S3 key for an upload.
    Images → uploads/images/<uuid>/<filename>
    Audio  → uploads/audio/<uuid>/<filename>
    Videos → uploads/videos/<uuid>/<filename>
    """
    if content_type in IMAGE_CONTENT_TYPES:
        folder = 'images'
    elif content_type.startswith('audio/'):
        folder = 'audio'
    else:
        folder = 'videos'
    safe_name = original_filename.replace(' ', '_')
    return f"uploads/{folder}/{uuid.uuid4().hex}/{safe_name}"


def is_audio(content_type: str) -> bool:
    return content_type.startswith('audio/')


def preprocessed_key(original_key: str) -> str:
    """Return the S3 key for the preprocessed (resized, EXIF-stripped) version."""
    parts = original_key.split('/', 3)          # ['uploads','images','<uid>','name.jpg']
    parts[1] = 'preprocessed'
    return '/'.join(parts)


def s3_uri(key: str) -> str:
    return f"s3://{Config.S3_BUCKET}/{key}"


def public_url(key: str) -> str:
    return f"https://{Config.S3_BUCKET}.s3.{Config.S3_REGION}.amazonaws.com/{key}"


# ─── Presigned URL ────────────────────────────────────────────────────────────

def generate_presigned_put(
    s3_key: str,
    content_type: str,
    expires_in: int = 900,
) -> str:
    """
    Return a presigned S3 PUT URL.
    The mobile client sends:
        PUT <url>
        Content-Type: <content_type>
        Body: <raw file bytes>
    """
    # ContentType is intentionally excluded from signed params.
    # Including it makes S3 enforce an exact header match, causing 403
    # when mobile clients send a slightly different value.
    url = _client().generate_presigned_url(
        'put_object',
        Params={
            'Bucket': Config.S3_BUCKET,
            'Key': s3_key,
        },
        ExpiresIn=expires_in,
    )
    return url


# ─── Download ─────────────────────────────────────────────────────────────────

def download_bytes(s3_key: str) -> bytes:
    """Download an S3 object and return its raw bytes."""
    response = _client().get_object(Bucket=Config.S3_BUCKET, Key=s3_key)
    return response['Body'].read()


def object_exists(s3_key: str) -> bool:
    """Return True if the key exists in S3 (used to verify mobile upload completed)."""
    try:
        _client().head_object(Bucket=Config.S3_BUCKET, Key=s3_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
            return False
        raise


# ─── Upload ───────────────────────────────────────────────────────────────────

def upload_bytes(s3_key: str, data: bytes, content_type: str = 'image/jpeg') -> str:
    """Upload raw bytes to S3. Returns the S3 key."""
    _client().put_object(
        Bucket=Config.S3_BUCKET,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
    )
    return s3_key


def generate_presigned_get(s3_key: str, expires_in: int = 604800) -> str:
    """Return a presigned S3 GET URL. Default expiry: 7 days."""
    return _client().generate_presigned_url(
        'get_object',
        Params={'Bucket': Config.S3_BUCKET, 'Key': s3_key},
        ExpiresIn=expires_in,
    )


def is_image(content_type: str) -> bool:
    return content_type in IMAGE_CONTENT_TYPES
