import time
import typing

import fastapi
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from microbootstrap.helpers import optimize_exclude_paths
from microbootstrap.instruments.logging_instrument import fill_log_message


def build_fastapi_logging_middleware(
    exclude_endpoints: typing.Iterable[str],
) -> type[BaseHTTPMiddleware]:
    endpoints_to_ignore: typing.Collection[str] = optimize_exclude_paths(exclude_endpoints)

    class FastAPILoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self,
            request: fastapi.Request,
            call_next: RequestResponseEndpoint,
        ) -> fastapi.Response:
            request_path: typing.Final = request.url.path.removesuffix("/")

            if request_path in endpoints_to_ignore:
                return await call_next(request)

            start_time: typing.Final = time.perf_counter_ns()
            try:
                response = await call_next(request)
            except Exception:  # noqa: BLE001
                response = fastapi.Response(status_code=500)

            fill_log_message(
                "exception" if response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR else "info",
                request,
                response.status_code,
                start_time,
            )
            return response

    return FastAPILoggingMiddleware
