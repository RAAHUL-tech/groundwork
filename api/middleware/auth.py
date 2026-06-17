from functools import wraps
from flask import request, jsonify, g
import jwt

from config import Config


def _decode_token(token: str) -> dict:
    """
    Decode and verify a Supabase JWT.
    Secret: Project Settings → API → JWT Secret (HS256).
    """
    return jwt.decode(
        token,
        Config.SUPABASE_JWT_SECRET,
        algorithms=['HS256'],
        audience='authenticated',
    )


def require_auth(f):
    """
    Decorator that enforces Supabase JWT authentication.

    Sets g.user_id and g.user_email on success.

    NOT applied to any routes in Phase 1 — wired up, ready to drop on.
    Usage:
        @estimate_bp.route('/estimate', methods=['POST'])
        @require_auth          ← add this line in Phase 2
        def create_estimate():
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        token = auth_header.split(' ', 1)[1]
        try:
            payload = _decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidAudienceError:
            return jsonify({'error': 'Invalid token audience'}), 401
        except jwt.InvalidTokenError as exc:
            return jsonify({'error': f'Invalid token: {exc}'}), 401

        g.user_id = payload['sub']
        g.user_email = payload.get('email', '')
        return f(*args, **kwargs)

    return decorated


def optional_auth(f):
    """
    Like require_auth but doesn't block unauthenticated requests.
    Sets g.user_id = None if no valid token is present.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        g.user_id = None
        g.user_email = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            try:
                payload = _decode_token(auth_header.split(' ', 1)[1])
                g.user_id = payload['sub']
                g.user_email = payload.get('email', '')
            except jwt.InvalidTokenError:
                pass
        return f(*args, **kwargs)

    return decorated
