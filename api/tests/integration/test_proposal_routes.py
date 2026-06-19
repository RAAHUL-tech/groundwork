"""Integration tests for POST /proposal."""
import pytest
from unittest.mock import MagicMock, patch
import datetime


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _post_proposal(client, body):
    return client.post('/proposal', json=body)


def _make_task_result(proposal_id='prop-abc123456789', pdf_url=None, expires_at=None):
    return {
        'proposal_id': proposal_id,
        'pdf_url':     pdf_url or 'https://s3.test.com/proposals/prop-abc.pdf',
        'expires_at':  expires_at or '2026-06-26T00:00:00Z',
    }


# ─── POST /proposal ───────────────────────────────────────────────────────────

class TestCreateProposal:
    def test_missing_estimate_job_id_returns_400(self, client):
        resp = _post_proposal(client, {})
        assert resp.status_code == 400
        assert 'error' in resp.get_json()

    def test_empty_estimate_job_id_returns_400(self, client):
        resp = _post_proposal(client, {'estimate_job_id': '   '})
        assert resp.status_code == 400

    def test_estimate_not_found_returns_404(self, client):
        mock_task = MagicMock()
        mock_task.get.side_effect = ValueError('Estimate not found: fake-id')

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_task):
            resp = _post_proposal(client, {'estimate_job_id': 'fake-id'})

        assert resp.status_code == 404
        assert 'error' in resp.get_json()

    def test_pdf_generation_failure_returns_500(self, client):
        mock_task = MagicMock()
        mock_task.get.side_effect = Exception('ReportLab error')

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_task):
            resp = _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        assert resp.status_code == 500
        assert 'error' in resp.get_json()

    def test_success_returns_200_with_proposal_id(self, client):
        mock_task = MagicMock()
        mock_task.get.return_value = _make_task_result()

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_task):
            resp = _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'proposal_id' in data
        assert data['proposal_id'] == 'prop-abc123456789'

    def test_success_returns_pdf_url(self, client):
        mock_task = MagicMock()
        mock_task.get.return_value = _make_task_result(
            pdf_url='https://s3.test.com/proposals/prop-abc.pdf'
        )

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_task):
            resp = _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'pdf_url' in data
        assert data['pdf_url'].startswith('https://')

    def test_success_returns_expires_at(self, client):
        mock_task = MagicMock()
        mock_task.get.return_value = _make_task_result()

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_task):
            resp = _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        assert 'expires_at' in resp.get_json()

    def test_default_contractor_applied(self, client):
        """Without an explicit contractor, the default (Mike Torres) is used."""
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            mock_task = MagicMock()
            mock_task.get.return_value = _make_task_result()
            return mock_task

        with patch('tasks.proposal_task.generate_proposal.apply', side_effect=capture):
            _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        contractor = captured.get('kwargs', {}).get('contractor', {})
        assert 'Torres' in contractor.get('name', '') or 'Torres' in contractor.get('company', '')

    def test_custom_contractor_overrides_default(self, client, sample_contractor):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            mock_task = MagicMock()
            mock_task.get.return_value = _make_task_result()
            return mock_task

        with patch('tasks.proposal_task.generate_proposal.apply', side_effect=capture):
            _post_proposal(client, {
                'estimate_job_id': 'cel-abc123',
                'contractor': sample_contractor,
            })

        contractor = captured.get('kwargs', {}).get('contractor', {})
        assert contractor.get('name') == 'Jane Smith'

    def test_custom_client_forwarded(self, client, sample_client_info):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            mock_task = MagicMock()
            mock_task.get.return_value = _make_task_result()
            return mock_task

        with patch('tasks.proposal_task.generate_proposal.apply', side_effect=capture):
            _post_proposal(client, {
                'estimate_job_id': 'cel-abc123',
                'client': sample_client_info,
            })

        client_data = captured.get('kwargs', {}).get('client', {})
        assert client_data.get('name') == 'Bob Homeowner'

    def test_custom_payment_terms(self, client):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            mock_task = MagicMock()
            mock_task.get.return_value = _make_task_result()
            return mock_task

        with patch('tasks.proposal_task.generate_proposal.apply', side_effect=capture):
            _post_proposal(client, {
                'estimate_job_id': 'cel-abc123',
                'payment_terms':   'Net 30',
                'valid_days':      45,
            })

        kwargs = captured.get('kwargs', {})
        assert kwargs.get('payment_terms') == 'Net 30'
        assert kwargs.get('valid_days') == 45

    def test_runs_synchronously_with_30s_timeout(self, client):
        """generate_proposal.apply().get(timeout=30) must be called, not .delay()."""
        mock_apply = MagicMock()
        mock_apply.return_value.get.return_value = _make_task_result()

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_apply.return_value):
            _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        mock_apply.return_value.get.assert_called_once_with(timeout=30)

    def test_pdf_url_none_still_returns_200(self, client):
        """S3 unavailable → pdf_url is None but we still get 200 with proposal_id."""
        mock_task = MagicMock()
        mock_task.get.return_value = {
            'proposal_id': 'prop-nourl123456',
            'pdf_url':     None,
            'expires_at':  None,
        }

        with patch('tasks.proposal_task.generate_proposal.apply', return_value=mock_task):
            resp = _post_proposal(client, {'estimate_job_id': 'cel-abc123'})

        assert resp.status_code == 200
        assert resp.get_json()['proposal_id'] == 'prop-nourl123456'
        assert resp.get_json()['pdf_url'] is None
