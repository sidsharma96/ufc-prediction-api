"""Application middleware."""

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and log details."""
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]

        # Record start time
        start_time = time.perf_counter()

        # Add request ID to state
        request.state.request_id = request_id

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error
            duration = time.perf_counter() - start_time
            print(f"[{request_id}] {request.method} {request.url.path} ERROR {duration:.3f}s - {e}")
            raise

        # Calculate duration
        duration = time.perf_counter() - start_time

        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration:.3f}"

        # Log request (skip health checks to reduce noise)
        if request.url.path != "/health":
            print(
                f"[{request_id}] {request.method} {request.url.path} "
                f"{response.status_code} {duration:.3f}s"
            )

        return response
