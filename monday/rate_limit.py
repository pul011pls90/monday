"""Lightweight sliding-window rate limiting with strict TESTING-only exemption guard."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, request

_LOCK = threading.Lock()
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _exempt_testing_apps(app) -> bool:
    """Return True ONLY when Flask TESTING is explicitly boolean True."""
    return app.config.get("TESTING") is True


def reset_rate_limits() -> None:
    """Clear in-memory rate-limit buckets (for unit tests)."""
    with _LOCK:
        _BUCKETS.clear()


def rate_limit(key_prefix: str, max_requests: int = 10, window_seconds: int = 60):
    """Enforce per-client sliding-window rate limit unless TESTING is explicitly True."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if _exempt_testing_apps(current_app):
                return view(*args, **kwargs)
            now = time.monotonic()
            ident = request.remote_addr or "local"
            bucket_key = f"{key_prefix}:{ident}"
            with _LOCK:
                q = _BUCKETS[bucket_key]
                cutoff = now - window_seconds
                while q and q[0] <= cutoff:
                    q.popleft()
                if len(q) >= max_requests:
                    abort(429)
                q.append(now)
            return view(*args, **kwargs)
        return wrapped
    return decorator
