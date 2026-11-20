"""Entry point of the Chatisfying backend.
Start (development):  python app.py
Start (production):   waitress-serve --threads=8 app:app   (ONE process, see storage.py)
"""
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import config
import storage
from security import ApiError

import admin
import auth
import groups
import invitations
import messages
import users


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000     # reject huge requests
    # Login uses an Authorization header (not cookies), so other websites cannot make the browser
    # send credentials on their own. That is why classic CSRF tokens are not needed here.
    CORS(app, origins=config.ALLOWED_ORIGINS, allow_headers=["Content-Type", "Authorization"])
    storage.ensure_files()

    for module in (auth, users, messages, groups, invitations, admin):
        app.register_blueprint(module.bp)

    @app.errorhandler(ApiError)
    def handle_api_error(err):
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
        return jsonify({"error": "Something went wrong on the server."}), 500

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
