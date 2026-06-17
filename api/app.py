from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config

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

    app.register_blueprint(estimate_bp)
    app.register_blueprint(proposal_bp)
    app.register_blueprint(rooms_bp)
    app.register_blueprint(upload_bp)

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
