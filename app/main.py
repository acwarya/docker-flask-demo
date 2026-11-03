import json
import logging
import os
import time

import redis
from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

VERSION = os.getenv("APP_VERSION", "dev")


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line (easy to ship to Loki/ELK/CloudWatch)."""

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def create_app(redis_client=None):
    configure_logging()
    log = logging.getLogger("app")
    app = Flask(__name__)

    if redis_client is None:
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
            socket_connect_timeout=2,
        )
    app.redis = redis_client

    # Per-app registry so tests can create many apps without duplicate metrics.
    registry = CollectorRegistry()
    req_count = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
        registry=registry,
    )
    req_latency = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["endpoint"],
        registry=registry,
    )

    @app.before_request
    def start_timer():
        g.start = time.perf_counter()

    @app.after_request
    def record(response):
        # Use the route template (not the raw path) to keep label cardinality low.
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed = time.perf_counter() - g.get("start", time.perf_counter())
        req_count.labels(request.method, endpoint, response.status_code).inc()
        req_latency.labels(endpoint).observe(elapsed)
        log.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                }
            },
        )
        return response

    @app.get("/")
    def index():
        hits = app.redis.incr("hits")
        return jsonify(message="Hello from Docker!", hits=hits, version=VERSION)

    @app.get("/health")
    def health():
        """Liveness: the process is up."""
        return jsonify(status="ok")

    @app.get("/ready")
    def ready():
        """Readiness: dependencies (Redis) are reachable."""
        try:
            app.redis.ping()
        except redis.RedisError:
            return jsonify(status="redis unavailable"), 503
        return jsonify(status="ready")

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

    @app.get("/todos")
    def list_todos():
        return jsonify(todos=app.redis.lrange("todos", 0, -1))

    @app.post("/todos")
    def add_todo():
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify(error="'text' is required"), 400
        app.redis.rpush("todos", text)
        return jsonify(added=text), 201

    return app
