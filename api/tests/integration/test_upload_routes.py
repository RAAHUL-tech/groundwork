"""Integration tests for POST /upload/presign."""
import pytest
from unittest.mock import MagicMock, patch


PRESIGN_URL = '/upload/presign'


def _post_presign(client, body):
    return client.post(PRESIGN_URL, json=body)


# ─── POST /upload/presign ─────────────────────────────────────────────────────

class TestPresignEndpoint:
    """
    The endpoint:
     - generates a presigned S3 PUT URL
     - creates a room_scan record (non-audio)
     - returns {upload_url, s3_key, room_scan_id, expires_in}
    """

    @pytest.fixture(autouse=True)
    def _default_mocks(self):
        """Patch S3 and Supabase for every test in this class."""
        mock_scan = {'id': 'scan-new-uuid', 'project_id': 'dev-project-uuid', 'image_urls': []}

        with patch('routes.upload.generate_presigned_put', return_value='https://s3.test.com/put') as mock_put:
            with patch('routes.upload.create_room_scan', return_value=mock_scan) as mock_create:
                self.mock_put = mock_put
                self.mock_create = mock_create
                yield

    def test_image_upload_returns_200(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        assert resp.status_code == 200

    def test_response_contains_required_fields(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        data = resp.get_json()
        assert 'upload_url' in data
        assert 's3_key' in data
        assert 'room_scan_id' in data
        assert 'expires_in' in data

    def test_upload_url_is_the_presigned_url(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        assert resp.get_json()['upload_url'] == 'https://s3.test.com/put'

    def test_expires_in_is_900(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        assert resp.get_json()['expires_in'] == 900

    def test_s3_key_starts_with_images_folder(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        assert resp.get_json()['s3_key'].startswith('uploads/images/')

    def test_room_scan_created(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        assert resp.status_code == 200
        self.mock_create.assert_called_once()

    def test_room_scan_id_returned(self, client):
        resp = _post_presign(client, {'file_name': 'photo.jpg', 'content_type': 'image/jpeg'})
        assert resp.get_json()['room_scan_id'] == 'scan-new-uuid'

    def test_video_upload_s3_key_in_videos_folder(self, client):
        resp = _post_presign(client, {'file_name': 'walkthrough.mp4', 'content_type': 'video/mp4'})
        assert resp.status_code == 200
        assert resp.get_json()['s3_key'].startswith('uploads/videos/')

    def test_video_creates_room_scan_with_video_url(self, client):
        resp = _post_presign(client, {'file_name': 'video.mp4', 'content_type': 'video/mp4'})
        assert resp.status_code == 200
        create_call = self.mock_create.call_args
        assert create_call[1].get('video_url') is not None or create_call[1].get('image_urls') == []

    def test_audio_upload_does_not_create_room_scan(self, client):
        resp = _post_presign(client, {'file_name': 'note.m4a', 'content_type': 'audio/mp4'})
        assert resp.status_code == 200
        self.mock_create.assert_not_called()

    def test_audio_upload_room_scan_id_is_none(self, client):
        resp = _post_presign(client, {'file_name': 'note.m4a', 'content_type': 'audio/mp4'})
        assert resp.get_json()['room_scan_id'] is None

    def test_audio_s3_key_in_audio_folder(self, client):
        resp = _post_presign(client, {'file_name': 'note.m4a', 'content_type': 'audio/mp4'})
        assert resp.get_json()['s3_key'].startswith('uploads/audio/')

    def test_room_label_forwarded_to_create_room_scan(self, client):
        _post_presign(client, {
            'file_name': 'photo.jpg',
            'content_type': 'image/jpeg',
            'room_label': 'Master Kitchen',
        })
        create_call = self.mock_create.call_args
        assert create_call[1].get('room_label') == 'Master Kitchen'

    def test_default_content_type_when_missing(self, client):
        """content_type has a default of 'image/jpeg' in the route."""
        resp = _post_presign(client, {'file_name': 'photo.jpg'})
        assert resp.status_code == 200
        assert resp.get_json()['s3_key'].startswith('uploads/images/')


class TestPresignReuseRoomScan:
    """Tests for the multi-image flow: room_scan_id is provided to append to existing scan."""

    def test_reuse_existing_scan_appends_image_url(self, client):
        existing_scan = {
            'id': 'scan-existing-uuid',
            'project_id': 'proj-123',
            'image_urls': ['s3://test-bucket/uploads/images/old/photo1.jpg'],
            'video_url': None,
        }
        with patch('routes.upload.generate_presigned_put', return_value='https://s3.test.com/put'):
            with patch('models.supabase_models.get_room_scan', return_value=existing_scan):
                with patch('models.supabase_models.update_room_scan') as mock_update:
                    resp = client.post(PRESIGN_URL, json={
                        'file_name':    'photo2.jpg',
                        'content_type': 'image/jpeg',
                        'room_scan_id': 'scan-existing-uuid',
                    })

        assert resp.status_code == 200
        assert resp.get_json()['room_scan_id'] == 'scan-existing-uuid'
        mock_update.assert_called_once()
        update_kwargs = mock_update.call_args[1]
        assert len(update_kwargs.get('image_urls', [])) == 2

    def test_invalid_room_scan_id_returns_404(self, client):
        with patch('routes.upload.generate_presigned_put', return_value='https://s3.test.com/put'):
            with patch('models.supabase_models.get_room_scan', return_value=None):
                resp = client.post(PRESIGN_URL, json={
                    'file_name':    'photo.jpg',
                    'content_type': 'image/jpeg',
                    'room_scan_id': 'nonexistent-scan-id',
                })

        assert resp.status_code == 404
        assert 'error' in resp.get_json()

    def test_video_reuse_scan_sets_video_url(self, client):
        existing_scan = {
            'id': 'scan-existing-uuid',
            'project_id': 'proj-123',
            'image_urls': [],
            'video_url': None,
        }
        with patch('routes.upload.generate_presigned_put', return_value='https://s3.test.com/put'):
            with patch('models.supabase_models.get_room_scan', return_value=existing_scan):
                with patch('models.supabase_models.update_room_scan') as mock_update:
                    resp = client.post(PRESIGN_URL, json={
                        'file_name':    'walk.mp4',
                        'content_type': 'video/mp4',
                        'room_scan_id': 'scan-existing-uuid',
                    })

        assert resp.status_code == 200
        mock_update.assert_called_once()
        update_kwargs = mock_update.call_args[1]
        assert 'video_url' in update_kwargs
        assert update_kwargs['video_url'].startswith('s3://')
