"""Unit tests for services/s3_storage.py."""
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError

import services.s3_storage as s3


# ─── Key helpers ──────────────────────────────────────────────────────────────

class TestBuildUploadKey:
    def test_image_goes_to_images_folder(self):
        key = s3.build_upload_key('image/jpeg', 'photo.jpg')
        assert key.startswith('uploads/images/')

    def test_png_is_also_image(self):
        key = s3.build_upload_key('image/png', 'photo.png')
        assert key.startswith('uploads/images/')

    def test_webp_is_image(self):
        key = s3.build_upload_key('image/webp', 'photo.webp')
        assert key.startswith('uploads/images/')

    def test_heic_is_image(self):
        key = s3.build_upload_key('image/heic', 'photo.heic')
        assert key.startswith('uploads/images/')

    def test_audio_goes_to_audio_folder(self):
        key = s3.build_upload_key('audio/mp4', 'note.m4a')
        assert key.startswith('uploads/audio/')

    def test_audio_mpeg_goes_to_audio_folder(self):
        key = s3.build_upload_key('audio/mpeg', 'note.mp3')
        assert key.startswith('uploads/audio/')

    def test_video_goes_to_videos_folder(self):
        key = s3.build_upload_key('video/mp4', 'walkthrough.mp4')
        assert key.startswith('uploads/videos/')

    def test_unknown_content_type_goes_to_videos_folder(self):
        key = s3.build_upload_key('application/octet-stream', 'file.bin')
        assert key.startswith('uploads/videos/')

    def test_key_contains_original_filename(self):
        key = s3.build_upload_key('image/jpeg', 'kitchen.jpg')
        assert key.endswith('kitchen.jpg')

    def test_spaces_replaced_with_underscores(self):
        key = s3.build_upload_key('image/jpeg', 'my photo.jpg')
        assert ' ' not in key
        assert 'my_photo.jpg' in key

    def test_keys_are_unique(self):
        key1 = s3.build_upload_key('image/jpeg', 'photo.jpg')
        key2 = s3.build_upload_key('image/jpeg', 'photo.jpg')
        assert key1 != key2

    def test_key_has_uuid_segment(self):
        key = s3.build_upload_key('image/jpeg', 'photo.jpg')
        parts = key.split('/')
        # uploads / images / <uuid> / filename
        assert len(parts) == 4
        assert len(parts[2]) == 32  # uuid4().hex is 32 chars


class TestIsImageAndIsAudio:
    @pytest.mark.parametrize('ct', [
        'image/jpeg', 'image/jpg', 'image/png', 'image/webp',
        'image/heic', 'image/heif', 'image/tiff',
    ])
    def test_is_image_true(self, ct):
        assert s3.is_image(ct) is True

    @pytest.mark.parametrize('ct', ['audio/mp4', 'video/mp4', 'application/json', 'text/plain'])
    def test_is_image_false(self, ct):
        assert s3.is_image(ct) is False

    @pytest.mark.parametrize('ct', ['audio/mp4', 'audio/m4a', 'audio/mpeg', 'audio/wav'])
    def test_is_audio_true(self, ct):
        assert s3.is_audio(ct) is True

    @pytest.mark.parametrize('ct', ['image/jpeg', 'video/mp4', 'application/pdf'])
    def test_is_audio_false(self, ct):
        assert s3.is_audio(ct) is False


class TestPreprocessedKey:
    def test_transforms_images_to_preprocessed(self):
        key = 'uploads/images/abc123/photo.jpg'
        assert s3.preprocessed_key(key) == 'uploads/preprocessed/abc123/photo.jpg'

    def test_preserves_uuid_and_filename(self):
        key = 'uploads/images/deadbeef/room.jpeg'
        result = s3.preprocessed_key(key)
        assert 'deadbeef' in result
        assert 'room.jpeg' in result


class TestUriHelpers:
    def test_s3_uri(self):
        result = s3.s3_uri('uploads/images/abc/photo.jpg')
        assert result == 's3://test-bucket/uploads/images/abc/photo.jpg'

    def test_public_url(self):
        result = s3.public_url('uploads/images/abc/photo.jpg')
        assert result == 'https://test-bucket.s3.us-east-1.amazonaws.com/uploads/images/abc/photo.jpg'


# ─── S3 operations (boto3 mocked) ────────────────────────────────────────────

@pytest.fixture
def mock_boto_client():
    """Patch boto3 client used inside _client()."""
    mock = MagicMock()
    with patch('boto3.client', return_value=mock):
        yield mock


class TestGeneratePresignedPut:
    def test_calls_generate_presigned_url(self, mock_boto_client):
        mock_boto_client.generate_presigned_url.return_value = 'https://s3.example.com/put'
        url = s3.generate_presigned_put('uploads/images/x/f.jpg', 'image/jpeg')
        assert url == 'https://s3.example.com/put'
        mock_boto_client.generate_presigned_url.assert_called_once_with(
            'put_object',
            Params={'Bucket': 'test-bucket', 'Key': 'uploads/images/x/f.jpg'},
            ExpiresIn=900,
        )

    def test_custom_expiry_passed_through(self, mock_boto_client):
        mock_boto_client.generate_presigned_url.return_value = 'https://s3.example.com/put'
        s3.generate_presigned_put('key', 'image/jpeg', expires_in=300)
        _, kwargs = mock_boto_client.generate_presigned_url.call_args
        assert kwargs['ExpiresIn'] == 300


class TestGeneratePresignedGet:
    def test_default_7day_expiry(self, mock_boto_client):
        mock_boto_client.generate_presigned_url.return_value = 'https://s3.example.com/get'
        url = s3.generate_presigned_get('proposals/prop-123.pdf')
        assert url == 'https://s3.example.com/get'
        _, kwargs = mock_boto_client.generate_presigned_url.call_args
        assert kwargs['ExpiresIn'] == 604800

    def test_custom_expiry(self, mock_boto_client):
        mock_boto_client.generate_presigned_url.return_value = 'https://s3.example.com/get'
        s3.generate_presigned_get('key', expires_in=3600)
        _, kwargs = mock_boto_client.generate_presigned_url.call_args
        assert kwargs['ExpiresIn'] == 3600


class TestObjectExists:
    def test_returns_true_when_object_found(self, mock_boto_client):
        mock_boto_client.head_object.return_value = {}
        assert s3.object_exists('uploads/images/x/f.jpg') is True

    def test_returns_false_on_404(self, mock_boto_client):
        mock_boto_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject'
        )
        assert s3.object_exists('uploads/images/x/missing.jpg') is False

    def test_returns_false_on_no_such_key(self, mock_boto_client):
        mock_boto_client.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Not Found'}}, 'HeadObject'
        )
        assert s3.object_exists('uploads/images/x/missing.jpg') is False

    def test_reraises_on_other_client_errors(self, mock_boto_client):
        mock_boto_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '403', 'Message': 'Forbidden'}}, 'HeadObject'
        )
        with pytest.raises(ClientError):
            s3.object_exists('uploads/images/x/f.jpg')


class TestDownloadBytes:
    def test_returns_body_bytes(self, mock_boto_client):
        mock_boto_client.get_object.return_value = {'Body': MagicMock(read=lambda: b'image-data')}
        result = s3.download_bytes('uploads/images/x/photo.jpg')
        assert result == b'image-data'

    def test_passes_correct_bucket_and_key(self, mock_boto_client):
        mock_boto_client.get_object.return_value = {'Body': MagicMock(read=lambda: b'')}
        s3.download_bytes('uploads/images/x/photo.jpg')
        mock_boto_client.get_object.assert_called_once_with(
            Bucket='test-bucket', Key='uploads/images/x/photo.jpg'
        )


class TestUploadBytes:
    def test_calls_put_object_and_returns_key(self, mock_boto_client):
        key = s3.upload_bytes('proposals/prop-123.pdf', b'%PDF-', 'application/pdf')
        assert key == 'proposals/prop-123.pdf'
        mock_boto_client.put_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='proposals/prop-123.pdf',
            Body=b'%PDF-',
            ContentType='application/pdf',
        )

    def test_default_content_type_is_jpeg(self, mock_boto_client):
        s3.upload_bytes('uploads/images/x/photo.jpg', b'data')
        _, kwargs = mock_boto_client.put_object.call_args
        assert kwargs['ContentType'] == 'image/jpeg'
