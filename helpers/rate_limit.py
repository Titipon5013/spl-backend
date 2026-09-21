"""Minimal in-memory login rate limiter (per client host, sliding 60s window).

This is a first-line control; a deployment should also enforce throttling at the
ingress/WAF. Disable by setting LOGIN_RATE_LIMIT_PER_MINUTE=0.
"""

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_attempts: dict[str, deque] = defaultdict(deque)


def reset_login_rate_limits() -> None:
    _attempts.clear()


def login_rate_limit(request: Request) -> None:
    limit = int(os.getenv("LOGIN_RATE_LIMIT_PER_MINUTE", "30"))
    if limit <= 0:
        return
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    history = _attempts[key]
    while history and now - history[0] >= 60:
        history.popleft()
    if len(history) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": "60"},
        )
    history.append(now)
