"""Integration tests for rooms / projects routes."""
import pytest
from unittest.mock import MagicMock, patch


# ─── POST /rooms ─────────────────────────────────────────────────────────────

class TestAddRoom:
    def _mock_complete_task(self, sample_estimate):
        task = MagicMock()
        task.state = 'SUCCESS'
        task.result = sample_estimate
        return task

    def test_missing_project_id_returns_400(self, client):
        resp = client.post('/rooms', json={'estimate_job_id': 'cel-abc'})
        assert resp.status_code == 400
        assert 'project_id' in resp.get_json()['error']

    def test_empty_project_id_returns_400(self, client):
        resp = client.post('/rooms', json={'project_id': '', 'estimate_job_id': 'cel-abc'})
        assert resp.status_code == 400

    def test_missing_estimate_job_id_returns_400(self, client):
        resp = client.post('/rooms', json={'project_id': 'proj-123'})
        assert resp.status_code == 400
        assert 'estimate_job_id' in resp.get_json()['error']

    def test_estimate_not_complete_returns_422(self, client):
        pending_task = MagicMock()
        pending_task.state = 'PENDING'

        with patch('celery_worker.celery_app.AsyncResult', return_value=pending_task):
            resp = client.post('/rooms', json={
                'project_id': 'proj-123',
                'estimate_job_id': 'cel-not-done',
            })

        assert resp.status_code == 422
        assert 'not ready' in resp.get_json()['error'].lower()

    def test_celery_failure_state_returns_422(self, client):
        failed_task = MagicMock()
        failed_task.state = 'FAILURE'

        with patch('celery_worker.celery_app.AsyncResult', return_value=failed_task):
            resp = client.post('/rooms', json={
                'project_id': 'proj-123',
                'estimate_job_id': 'cel-failed',
            })

        assert resp.status_code == 422

    def test_celery_connection_failure_returns_503(self, client):
        with patch('celery_worker.celery_app.AsyncResult', side_effect=Exception('Redis down')):
            resp = client.post('/rooms', json={
                'project_id': 'proj-123',
                'estimate_job_id': 'cel-abc',
            })

        assert resp.status_code == 503

    def test_db_error_returns_500(self, client, sample_estimate):
        task = self._mock_complete_task(sample_estimate)

        with patch('celery_worker.celery_app.AsyncResult', return_value=task):
            with patch('models.supabase_models.add_room_to_project', side_effect=Exception('DB timeout')):
                resp = client.post('/rooms', json={
                    'project_id':      'proj-123',
                    'estimate_job_id': 'cel-abc',
                })

        assert resp.status_code == 500
        assert 'error' in resp.get_json()

    def test_success_returns_200_with_aggregate(self, client, sample_estimate, sample_project_aggregate):
        task = self._mock_complete_task(sample_estimate)

        with patch('celery_worker.celery_app.AsyncResult', return_value=task):
            with patch('models.supabase_models.add_room_to_project', return_value=sample_project_aggregate):
                resp = client.post('/rooms', json={
                    'project_id':      'proj-uuid-1234',
                    'estimate_job_id': 'cel-abc',
                })

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'aggregate' in data
        assert data['aggregate']['room_count'] == 1
        assert data['aggregate']['grand_total'] == 10442

    def test_room_label_defaults_to_room_type(self, client, sample_estimate, sample_project_aggregate):
        task = self._mock_complete_task(sample_estimate)
        captured_label = {}

        def capture_add(**kwargs):
            captured_label.update(kwargs)
            return sample_project_aggregate

        with patch('celery_worker.celery_app.AsyncResult', return_value=task):
            with patch('models.supabase_models.add_room_to_project', side_effect=capture_add):
                client.post('/rooms', json={
                    'project_id':      'proj-uuid-1234',
                    'estimate_job_id': 'cel-abc',
                })

        assert captured_label.get('room_label') == 'Kitchen'

    def test_room_label_override(self, client, sample_estimate, sample_project_aggregate):
        task = self._mock_complete_task(sample_estimate)
        captured_label = {}

        def capture_add(**kwargs):
            captured_label.update(kwargs)
            return sample_project_aggregate

        with patch('celery_worker.celery_app.AsyncResult', return_value=task):
            with patch('models.supabase_models.add_room_to_project', side_effect=capture_add):
                client.post('/rooms', json={
                    'project_id':      'proj-uuid-1234',
                    'estimate_job_id': 'cel-abc',
                    'room_label':      'Master Bathroom',
                })

        assert captured_label.get('room_label') == 'Master Bathroom'

    def test_total_estimate_forwarded_from_result(self, client, sample_estimate, sample_project_aggregate):
        task = self._mock_complete_task(sample_estimate)
        captured = {}

        def capture_add(**kwargs):
            captured.update(kwargs)
            return sample_project_aggregate

        with patch('celery_worker.celery_app.AsyncResult', return_value=task):
            with patch('models.supabase_models.add_room_to_project', side_effect=capture_add):
                client.post('/rooms', json={
                    'project_id':      'proj-uuid-1234',
                    'estimate_job_id': 'cel-abc',
                })

        assert captured.get('total_estimate') == pytest.approx(10442.0)

    def test_project_not_found_returns_404(self, client, sample_estimate):
        task = self._mock_complete_task(sample_estimate)

        with patch('celery_worker.celery_app.AsyncResult', return_value=task):
            with patch('models.supabase_models.add_room_to_project', return_value=None):
                resp = client.post('/rooms', json={
                    'project_id':      'nonexistent-proj',
                    'estimate_job_id': 'cel-abc',
                })

        assert resp.status_code == 404


# ─── GET /projects ────────────────────────────────────────────────────────────

class TestListProjects:
    def test_returns_200_with_list(self, client, sample_project):
        with patch('models.supabase_models.list_projects_all', return_value=[sample_project]):
            resp = client.get('/projects')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['id'] == 'proj-uuid-1234'

    def test_empty_list_when_no_projects(self, client):
        with patch('models.supabase_models.list_projects_all', return_value=[]):
            resp = client.get('/projects')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_db_error_returns_empty_list(self, client):
        with patch('models.supabase_models.list_projects_all', side_effect=Exception('DB timeout')):
            resp = client.get('/projects')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_response_includes_expected_fields(self, client, sample_project):
        with patch('models.supabase_models.list_projects_all', return_value=[sample_project]):
            resp = client.get('/projects')
        project = resp.get_json()[0]
        assert 'id' in project
        assert 'name' in project
        assert 'client_name' in project
        assert 'status' in project


# ─── GET /projects/<project_id> ───────────────────────────────────────────────

class TestGetProject:
    def test_returns_200_with_aggregate(self, client, sample_project_aggregate):
        with patch('models.supabase_models.get_project_aggregate', return_value=sample_project_aggregate):
            resp = client.get('/projects/proj-uuid-1234')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['id'] == 'proj-uuid-1234'
        assert 'aggregate' in data
        assert 'rooms' in data

    def test_not_found_returns_404(self, client):
        with patch('models.supabase_models.get_project_aggregate', return_value=None):
            resp = client.get('/projects/nonexistent-id')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()

    def test_db_error_returns_500(self, client):
        with patch('models.supabase_models.get_project_aggregate', side_effect=Exception('DB error')):
            resp = client.get('/projects/proj-uuid-1234')
        assert resp.status_code == 500

    def test_aggregate_mobilization_zero_for_single_room(self, client, sample_project_aggregate):
        sample_project_aggregate['aggregate']['mobilization'] = 0
        with patch('models.supabase_models.get_project_aggregate', return_value=sample_project_aggregate):
            resp = client.get('/projects/proj-uuid-1234')
        assert resp.get_json()['aggregate']['mobilization'] == 0

    def test_aggregate_mobilization_500_for_multiple_rooms(self, client, sample_project_aggregate):
        sample_project_aggregate['rooms'].append(
            {'id': 'pr-2', 'room_label': 'Bathroom', 'total_estimate': 5000.0,
             'room_scan_id': 'scan-2', 'estimate_id': 'est-2', 'added_at': '2026-06-02T10:00:00Z'}
        )
        sample_project_aggregate['aggregate'] = {
            'room_count': 2,
            'subtotal':   15442,
            'mobilization': 500,
            'grand_total':  15942,
        }
        with patch('models.supabase_models.get_project_aggregate', return_value=sample_project_aggregate):
            resp = client.get('/projects/proj-uuid-1234')
        assert resp.get_json()['aggregate']['mobilization'] == 500
        assert resp.get_json()['aggregate']['grand_total'] == 15942
