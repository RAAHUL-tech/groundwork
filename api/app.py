import logging
import time

from flask import Flask, jsonify, g, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# Shared limiter instance — imported by routes that need per-endpoint limits
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=Config.REDIS_URL,
    default_limits=['500 per day', '100 per hour'],
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Allow Expo dev server and production app origins
    CORS(app, origins=[
        'http://localhost:8081',
        'http://localhost:19006',
        'exp://localhost:8081',
        'https://*.supabase.co',
    ])

    # ── Rate limiting (Redis-backed) ──────────────────────────────────────────
    limiter.init_app(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from routes.estimate import estimate_bp
    from routes.proposal import proposal_bp
    from routes.rooms import rooms_bp
    from routes.upload import upload_bp
    from routes.transcribe import transcribe_bp

    app.register_blueprint(estimate_bp)
    app.register_blueprint(proposal_bp)
    app.register_blueprint(rooms_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(transcribe_bp)

    # ── Request / response logging ────────────────────────────────────────────
    @app.before_request
    def _log_request():
        g._req_start = time.monotonic()
        body_preview = ''
        if request.is_json:
            raw = request.get_data(as_text=True)
            # Mask base64 blobs — they're huge and useless in logs
            import re
            raw = re.sub(r'"[A-Za-z0-9+/]{60,}={0,2}"', '"<base64>"', raw)
            body_preview = raw[:300] + ('…' if len(raw) > 300 else '')
        logger.info('→ %s %s  body=%s', request.method, request.path, body_preview or '(none)')

    @app.after_request
    def _log_response(response):
        ms = (time.monotonic() - g.get('_req_start', time.monotonic())) * 1000
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(level, '← %s %s  status=%d  %.0fms',
                   request.method, request.path, response.status_code, ms)
        return response

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get('/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'groundwork-api'}), 200

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({'error': 'Rate limit exceeded. Max 10 requests/minute.'}), 429

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error'}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=Config.DEBUG)
