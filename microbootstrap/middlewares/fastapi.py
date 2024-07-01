import time
import typing

import fastapi
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from microbootstrap.middlewares.logging import fill_log_message
from microbootstrap.middlewares.logging_level import LogLevel


class FastAPILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: fastapi.Request,
        call_next: RequestResponseEndpoint,
    ) -> fastapi.Response:
        start_time: typing.Final = time.perf_counter_ns()
        try:
            response: typing.Final = await call_next(request)
        except Exception:  # noqa: BLE001
            error_response: typing.Final = fastapi.Response(status_code=500)
            fill_log_message(LogLevel.EXCEPTION, request, error_response.status_code, start_time)
            return error_response

        fill_log_message(LogLevel.INFO, request, response.status_code, start_time)
        return response
