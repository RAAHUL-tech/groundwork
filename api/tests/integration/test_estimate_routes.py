"""Integration tests for estimate routes (POST /estimate, GET /estimate/status/:id, GET /estimates/recent)."""
import pytest
from unittest.mock import MagicMock, patch


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _post_estimate(client, body, headers=None):
    return client.post('/estimate', json=body, headers=headers or {})


def _get_status(client, job_id):
    return client.get(f'/estimate/status/{job_id}')


# ─── Health check (sanity) ────────────────────────────────────────────────────

def test_health_check(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json() == {'status': 'ok', 'service': 'groundwork-api'}


# ─── POST /estimate ───────────────────────────────────────────────────────────

class TestCreateEstimate:
    def _mock_task(self):
        task = MagicMock()
        task.id = 'cel-test-job-id'
        return task

    def test_base64_images_returns_202_with_job_id(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task):
            resp = _post_estimate(client, {'images': ['base64data']})
        assert resp.status_code == 202
        data = resp.get_json()
        assert data['job_id'] == 'cel-test-job-id'
        assert data['status'] == 'processing'
        assert 'poll_url' in data
        assert 'estimated_wait_seconds' in data

    def test_poll_url_points_to_status_endpoint(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task):
            resp = _post_estimate(client, {'images': ['base64data']})
        data = resp.get_json()
        assert data['poll_url'] == f'/estimate/status/{task.id}'

    def test_s3_key_path_returns_202(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task):
            with patch('services.s3_storage.object_exists', return_value=True):
                resp = _post_estimate(client, {
                    's3_key': 'uploads/images/abc/photo.jpg',
                    'room_scan_id': None,
                })
        assert resp.status_code == 202

    def test_s3_keys_multi_image_returns_202(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task):
            with patch('services.s3_storage.object_exists', return_value=True):
                resp = _post_estimate(client, {
                    's3_keys': [
                        'uploads/images/abc/photo1.jpg',
                        'uploads/images/abc/photo2.jpg',
                    ]
                })
        assert resp.status_code == 202

    def test_s3_object_not_found_returns_422(self, client):
        with patch('services.s3_storage.object_exists', return_value=False):
            resp = _post_estimate(client, {
                's3_key': 'uploads/images/abc/missing.jpg',
            })
        assert resp.status_code == 422
        assert 'error' in resp.get_json()

    def test_s3_check_failure_proceeds_anyway(self, client):
        """S3 existence check failure should not block the estimate — it's best-effort."""
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task):
            with patch('services.s3_storage.object_exists', side_effect=Exception('boto3 down')):
                resp = _post_estimate(client, {
                    's3_key': 'uploads/images/abc/photo.jpg',
                })
        assert resp.status_code == 202

    def test_empty_body_uses_default_tier_and_zip(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task) as mock_delay:
            _post_estimate(client, {})
        call_kwargs = mock_delay.call_args[1]
        assert call_kwargs['tier'] == 'standard'
        assert call_kwargs['zip_code'] == '90210'

    def test_custom_tier_and_zip_forwarded(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task) as mock_delay:
            _post_estimate(client, {'tier': 'premium', 'zip_code': '10001'})
        call_kwargs = mock_delay.call_args[1]
        assert call_kwargs['tier'] == 'premium'
        assert call_kwargs['zip_code'] == '10001'

    def test_voice_transcript_forwarded(self, client):
        task = self._mock_task()
        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task) as mock_delay:
            _post_estimate(client, {'voice_transcript': 'Replace the cabinets'})
        call_kwargs = mock_delay.call_args[1]
        assert call_kwargs['voice_transcript'] == 'Replace the cabinets'

    def test_room_scan_updated_with_celery_job_id(self, client):
        task = self._mock_task()
        scan_id = 'scan-uuid-abcd'
        mock_scan = {'id': scan_id, 'project_id': None, 'image_urls': []}

        with patch('tasks.vision_pipeline.run_vision_pipeline.delay', return_value=task):
            with patch('models.supabase_models.get_room_scan', return_value=mock_scan):
                with patch('models.supabase_models.update_room_scan') as mock_update:
                    resp = _post_estimate(client, {
                        'room_scan_id': scan_id,
                        'images': ['base64data'],
                    })

        assert resp.status_code == 202
        mock_update.assert_called_once()
        update_kwargs = mock_update.call_args[1]
        assert update_kwargs.get('celery_job_id') == task.id
        assert update_kwargs.get('status') == 'processing'


# ─── GET /estimate/status/<job_id> ───────────────────────────────────────────

class TestGetEstimateStatus:
    def _mock_result(self, state, result=None):
        mock = MagicMock()
        mock.state = state
        mock.result = result
        return mock

    def test_pending_returns_processing(self, client):
        with patch('celery_worker.celery_app.AsyncResult', return_value=self._mock_result('PENDING')):
            resp = _get_status(client, 'cel-abc123')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'processing'

    def test_started_returns_processing(self, client):
        with patch('celery_worker.celery_app.AsyncResult', return_value=self._mock_result('STARTED')):
            resp = _get_status(client, 'cel-abc123')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'processing'

    def test_success_returns_complete_with_result(self, client, sample_estimate):
        with patch('celery_worker.celery_app.AsyncResult',
                   return_value=self._mock_result('SUCCESS', sample_estimate)):
            resp = _get_status(client, 'cel-abc123')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'complete'
        assert data['result']['room_type'] == 'kitchen'
        assert data['result']['total_estimate'] == 10442

    def test_failure_returns_failed_with_error(self, client):
        with patch('celery_worker.celery_app.AsyncResult',
                   return_value=self._mock_result('FAILURE', Exception('Vision API timeout'))):
            resp = _get_status(client, 'cel-abc123')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'failed'
        assert 'error' in data

    def test_retry_state_lowercased(self, client):
        with patch('celery_worker.celery_app.AsyncResult',
                   return_value=self._mock_result('RETRY')):
            resp = _get_status(client, 'cel-abc123')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'retry'

    def test_job_id_echoed_in_response(self, client):
        with patch('celery_worker.celery_app.AsyncResult',
                   return_value=self._mock_result('PENDING')):
            resp = _get_status(client, 'cel-my-job-id')
        assert resp.get_json()['job_id'] == 'cel-my-job-id'


# ─── GET /estimates/recent ────────────────────────────────────────────────────

class TestListRecentEstimates:
    def _fake_estimates(self, n):
        return [
            {'id': f'est-{i}', 'room_type': 'kitchen', 'total_estimate': 10000 + i * 100}
            for i in range(n)
        ]

    def test_returns_200_with_list(self, client):
        with patch('models.supabase_models.list_recent_estimates', return_value=self._fake_estimates(5)):
            resp = client.get('/estimates/recent')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)
        assert len(resp.get_json()) == 5

    def test_default_limit_is_10(self, client):
        with patch('models.supabase_models.list_recent_estimates') as mock_fn:
            mock_fn.return_value = self._fake_estimates(10)
            client.get('/estimates/recent')
        mock_fn.assert_called_once_with(limit=10)

    def test_custom_limit(self, client):
        with patch('models.supabase_models.list_recent_estimates') as mock_fn:
            mock_fn.return_value = self._fake_estimates(3)
            resp = client.get('/estimates/recent?limit=3')
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(limit=3)

    def test_limit_capped_at_50(self, client):
        with patch('models.supabase_models.list_recent_estimates') as mock_fn:
            mock_fn.return_value = self._fake_estimates(50)
            client.get('/estimates/recent?limit=999')
        mock_fn.assert_called_once_with(limit=50)

    def test_db_error_returns_empty_list(self, client):
        with patch('models.supabase_models.list_recent_estimates', side_effect=Exception('DB down')):
            resp = client.get('/estimates/recent')
        assert resp.status_code == 200
        assert resp.get_json() == []
