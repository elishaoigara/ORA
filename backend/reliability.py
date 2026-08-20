"""Small, dependency-free reliability primitives for the ORA backend."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class RuntimeMetrics:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = Lock()
        self._requests = 0
        self._errors = 0
        self._by_path: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "errors": 0})
        self._latencies: deque[float] = deque(maxlen=200)

    def record(self, path: str, status_code: int, elapsed_ms: float) -> None:
        with self._lock:
            self._requests += 1
            self._errors += int(status_code >= 500)
            self._by_path[path]["requests"] += 1
            self._by_path[path]["errors"] += int(status_code >= 500)
            self._latencies.append(elapsed_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = sorted(self._latencies)
            p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
            return {
                "uptime_seconds": round(max(0.0, time.time() - self.started_at), 1),
                "requests": self._requests,
                "errors": self._errors,
                "error_rate": round(self._errors / self._requests, 4) if self._requests else 0.0,
                "latency_p95_ms": round(p95, 2),
                "paths": {key: dict(value) for key, value in self._by_path.items()},
            }


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - now))
                return False, retry_after
            events.append(now)
            return True, 0


runtime_metrics = RuntimeMetrics()
voice_limiter = SlidingWindowLimiter()
VOICE_REQUESTS_PER_MINUTE = 12


async def metrics_middleware(request: Request, call_next):
    started = time.perf_counter()
    if request.url.path == "/api/voice/command":
        client_key = request.client.host if request.client else "unknown"
        allowed, retry_after = voice_limiter.allow(client_key, VOICE_REQUESTS_PER_MINUTE, 60)
        if not allowed:
            runtime_metrics.record(request.url.path, 429, (time.perf_counter() - started) * 1000)
            return JSONResponse(
                status_code=429,
                content={"ok": False, "error": "Too many voice requests; try again shortly"},
                headers={"Retry-After": str(retry_after), "X-Request-ID": uuid.uuid4().hex},
            )
    response = await call_next(request)
    runtime_metrics.record(request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = uuid.uuid4().hex
    return response
