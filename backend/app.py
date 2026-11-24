"""Entry point of the Chatisfying backend.
Start (development):  python app.py
Start (production):   waitress-serve --listen=0.0.0.0:$PORT --threads=8 app:app   (ONE process, see storage.py)
"""
import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import config
import storage
from security import ApiError

import admin
import auth
import chat_service
import db
import groups
import invitations
import messages
import moderation
import settings
import uploads
import users

# Render sets RENDER_GIT_COMMIT automatically. It shows which commit is really running.
BUILD = (os.environ.get("RENDER_GIT_COMMIT") or "local")[:7]


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000     # reject huge requests
    # Login uses an Authorization header (not cookies), so other websites cannot make the browser
    # send credentials on their own. That is why classic CSRF tokens are not needed here.
    CORS(app, origins=config.ALLOWED_ORIGINS, allow_headers=["Content-Type", "Authorization"])
    storage.ensure_files()
    db.init()
    chat_service.migrate_legacy()

    for module in (auth, users, messages, groups, invitations, admin, moderation, settings, uploads):
        app.register_blueprint(module.bp)

    # DEBUG ONLY: logs every request (method + path, never headers, bodies or query strings).
    @app.before_request
    def log_request():
        print(f"[REQUEST] {request.method} {request.path}", flush=True)

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        print(f"[ERROR] {request.path} -> {err.status} {err.message}", flush=True)
        return jsonify({"error": err.message}), err.status

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(405)
    def not_allowed(_):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": "Request is too large."}), 413

    @app.errorhandler(Exception)
    def unexpected(err):
        if isinstance(err, HTTPException):
            return jsonify({"error": err.description}), err.code
        app.logger.exception(err)
        print(f"[ERROR] Unexpected {type(err).__name__} on {request.path}", flush=True)
        return jsonify({"error": "Something went wrong on the server."}), 500

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # DEBUG ONLY: proves WHICH code is running. Remove before real production use.
    @app.get("/debug")
    def debug():
        print("[DEBUG] /debug called", flush=True)
        return jsonify({
            "status": "Chatisfying Backend Debug OK",
            "build": BUILD,
            "smtp_configured": bool(config.SMTP_HOST),
            "routes": sorted(r.rule for r in app.url_map.iter_rules() if r.rule.startswith(("/api/auth", "/debug", "/api/health"))),
        })

    return app


app = create_app()
print(f"[CHATISFYING] Backend started (build {BUILD}, SMTP configured: {bool(config.SMTP_HOST)})", flush=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
