"""
Application factory — creates and configures the Flask app.
This is the main entry point for the multi-agent orchestration system.
"""
from __future__ import annotations
import os
import logging

from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import google.genai as genai

from core.logging_config import configure_logging
from core.memory import MemoryManager
from api.routes import api_bp, set_memory
from monitoring.metrics import metrics_endpoint

load_dotenv()
configure_logging(os.getenv("LOG_LEVEL", "INFO"))

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Flask application factory."""
    app = Flask(__name__, static_folder="ui", static_url_path="")

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── Gemini ───────────────────────────────────────────────────────────────
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY is not set — LLM calls will fail")
    else:
        # The google.genai client is initialized per-agent; just validate the key exists
        logger.info("Gemini configured with model: %s", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    # ── Memory ───────────────────────────────────────────────────────────────
    redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    memory = MemoryManager(redis_url)
    set_memory(memory)

    # ── Register blueprints ──────────────────────────────────────────────────
    app.register_blueprint(api_bp)

    # ── Metrics endpoint ─────────────────────────────────────────────────────
    app.add_url_rule("/metrics", "metrics", metrics_endpoint)

    # ── UI route ─────────────────────────────────────────────────────────────
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_ui(path):
        """Serve the frontend dashboard."""
        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import jsonify
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import jsonify
        logger.error("Internal server error: %s", e)
        return jsonify({"error": "Internal server error"}), 500

    logger.info("Multi-Agent Orchestration System started on port %s", os.getenv("PORT", "5000"))
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
