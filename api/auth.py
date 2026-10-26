"""
JWT authentication and API key middleware.
"""
from __future__ import annotations
import os
import functools
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from flask import request, jsonify, g

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Simple API key store (in production, use a database)
VALID_API_KEYS = set(filter(None, os.getenv("API_KEYS", "dev-key-12345,test-key-67890").split(",")))


def create_token(user_id: str, role: str = "user") -> str:
    """Create a JWT token."""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("Expired JWT token")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid JWT token: %s", e)
        return None


def require_auth(f):
    """Decorator: requires valid JWT Bearer token or API key in X-API-Key header."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Try API key first
        api_key = request.headers.get("X-API-Key")
        if api_key and api_key in VALID_API_KEYS:
            g.user = {"user_id": "api-key-user", "role": "user"}
            return f(*args, **kwargs)

        # Try Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = verify_token(token)
            if payload:
                g.user = payload
                return f(*args, **kwargs)

        return jsonify({"error": "Unauthorized — provide a valid Bearer token or X-API-Key"}), 401
    return decorated


def optional_auth(f):
    """Decorator: auth is optional. Sets g.user if valid credentials are present."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        g.user = None
        api_key = request.headers.get("X-API-Key")
        if api_key and api_key in VALID_API_KEYS:
            g.user = {"user_id": "api-key-user", "role": "user"}
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = verify_token(token)
            if payload:
                g.user = payload
        return f(*args, **kwargs)
    return decorated
