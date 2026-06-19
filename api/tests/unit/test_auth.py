"""Unit tests for middleware/auth.py."""
import pytest
from unittest.mock import patch
import jwt

from flask import Flask, g, jsonify
from middleware.auth import require_auth, optional_auth


# ─── Minimal Flask app that uses the decorators ───────────────────────────────

@pytest.fixture(scope='module')
def auth_app():
    app = Flask(__name__)
    app.config['TESTING'] = True

    @app.get('/protected')
    @require_auth
    def protected():
        return jsonify({'user_id': g.user_id, 'email': g.user_email})

    @app.get('/optional')
    @optional_auth
    def optional_endpoint():
        return jsonify({'user_id': g.user_id, 'email': g.user_email})

    return app


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


VALID_PAYLOAD = {
    'sub': 'user-uuid-123',
    'email': 'test@example.com',
    'aud': 'authenticated',
}


# ─── require_auth ─────────────────────────────────────────────────────────────

class TestRequireAuth:
    def test_missing_authorization_header_returns_401(self, auth_client):
        resp = auth_client.get('/protected')
        assert resp.status_code == 401
        assert 'error' in resp.get_json()

    def test_non_bearer_scheme_returns_401(self, auth_client):
        resp = auth_client.get('/protected', headers={'Authorization': 'Basic abc123'})
        assert resp.status_code == 401

    def test_valid_token_returns_200_and_sets_user_id(self, auth_client):
        with patch('middleware.auth._decode_token', return_value=VALID_PAYLOAD):
            resp = auth_client.get('/protected', headers={'Authorization': 'Bearer valid-token'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['user_id'] == 'user-uuid-123'
        assert data['email'] == 'test@example.com'

    def test_expired_token_returns_401(self, auth_client):
        with patch('middleware.auth._decode_token', side_effect=jwt.ExpiredSignatureError):
            resp = auth_client.get('/protected', headers={'Authorization': 'Bearer expired'})
        assert resp.status_code == 401
        assert 'expired' in resp.get_json()['error'].lower()

    def test_invalid_audience_returns_401(self, auth_client):
        with patch('middleware.auth._decode_token', side_effect=jwt.InvalidAudienceError):
            resp = auth_client.get('/protected', headers={'Authorization': 'Bearer bad-aud'})
        assert resp.status_code == 401
        assert 'audience' in resp.get_json()['error'].lower()

    def test_generic_jwt_error_returns_401(self, auth_client):
        with patch('middleware.auth._decode_token', side_effect=jwt.InvalidTokenError('bad sig')):
            resp = auth_client.get('/protected', headers={'Authorization': 'Bearer tampered'})
        assert resp.status_code == 401

    def test_bearer_with_extra_spaces_rejected(self, auth_client):
        resp = auth_client.get('/protected', headers={'Authorization': '  Bearer  token'})
        assert resp.status_code == 401


# ─── optional_auth ────────────────────────────────────────────────────────────

class TestOptionalAuth:
    def test_no_header_succeeds_with_null_user(self, auth_client):
        resp = auth_client.get('/optional')
        assert resp.status_code == 200
        assert resp.get_json()['user_id'] is None

    def test_valid_token_sets_user_id(self, auth_client):
        with patch('middleware.auth._decode_token', return_value=VALID_PAYLOAD):
            resp = auth_client.get('/optional', headers={'Authorization': 'Bearer valid'})
        assert resp.status_code == 200
        assert resp.get_json()['user_id'] == 'user-uuid-123'

    def test_invalid_token_does_not_block_request(self, auth_client):
        with patch('middleware.auth._decode_token', side_effect=jwt.InvalidTokenError):
            resp = auth_client.get('/optional', headers={'Authorization': 'Bearer bad'})
        assert resp.status_code == 200
        assert resp.get_json()['user_id'] is None

    def test_expired_token_does_not_block_request(self, auth_client):
        with patch('middleware.auth._decode_token', side_effect=jwt.ExpiredSignatureError):
            resp = auth_client.get('/optional', headers={'Authorization': 'Bearer expired'})
        assert resp.status_code == 200
        assert resp.get_json()['user_id'] is None

    def test_non_bearer_scheme_proceeds_as_unauthenticated(self, auth_client):
        resp = auth_client.get('/optional', headers={'Authorization': 'Basic abc'})
        assert resp.status_code == 200
        assert resp.get_json()['user_id'] is None
