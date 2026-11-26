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

import accounts
import admin
import ai
import auth
import chat_service
import db
import diag
import economy
import extras
import games
import groups
import invitations
import matches
import messages
import moderation
import notes
import notify
import offers
import perms
import plans
import planner
import fun
import i18n
import pc
import prank
import settings
import social
import uploads
import users

# Render sets RENDER_GIT_COMMIT automatically. It shows which commit is really running.
BUILD = (os.environ.get("RENDER_GIT_COMMIT") or "local")[:7]


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000     # reject huge requests
    # Login uses an Authorization header (not cookies), so other websites cannot make the browser
    # send credentials on their own. That is why classic CSRF tokens are not needed here.
    CORS(app, origins=config.ALLOWED_ORIGINS, allow_headers=["Content-Type", "Authorization"], max_age=600)
    if config.PROXY_HOPS > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.PROXY_HOPS)
    storage.ensure_files()
    db.init()
    # Version 3 start-up steps. All of them are safe to run again and again (they only fill in what is missing).
    perms.ensure_defaults()
    perms.grant_new_defaults()
    perms.migrate_users()
    chat_service.migrate_legacy()
    notify.init_read_state()
    economy.seed_missions()
    extras.seed_release()
    i18n.seed()

    for module in (auth, users, accounts, messages, groups, invitations, admin, moderation, settings, uploads, notify, economy,
                   offers, notes, planner, social, games, matches, extras, ai, diag, plans, prank, pc, fun, i18n):
        app.register_blueprint(module.bp)

    # DEBUG ONLY: logs every request (method + path, never headers, bodies or query strings).
    @app.before_request
    def log_request():
        print(f"[REQUEST] {request.method} {request.path}", flush=True)

    # Headers for every answer. The API only sends JSON, so nothing may ever be treated as a web page or be cached
    # (private data!), and no address of the app may leak to other sites.
    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return resp

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        print(f"[ERROR] {request.path} -> {err.status} {err.message}", flush=True)
        body = {"error": err.message}
        if err.code:
            body["code"] = err.code
        return jsonify(body), err.status

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

    # Proves WHICH code is running (useful after a deploy). It shows nothing about settings or routes.
    @app.get("/debug")
    def debug():
        return jsonify({"status": "Chatisfying Backend OK", "build": BUILD})

    return app


app = create_app()
print(f"[CHATISFYING] Backend started (build {BUILD}, SMTP configured: {bool(config.SMTP_HOST)})", flush=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
