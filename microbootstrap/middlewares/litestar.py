from __future__ import annotations
import time
import typing

import litestar
import litestar.types
from litestar.middleware.base import MiddlewareProtocol
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from microbootstrap.helpers import optimize_exclude_paths
from microbootstrap.instruments.logging_instrument import fill_log_message


def build_litestar_logging_middleware(
    exclude_endpoints: typing.Iterable[str],
) -> type[MiddlewareProtocol]:
    endpoints_to_ignore: typing.Collection[str] = optimize_exclude_paths(exclude_endpoints)

    class LitestarLoggingMiddleware(MiddlewareProtocol):
        def __init__(self, app: litestar.types.ASGIApp) -> None:
            self.app = app

        async def __call__(
            self,
            request_scope: litestar.types.Scope,
            receive: litestar.types.Receive,
            send_function: litestar.types.Send,
        ) -> None:
            request: typing.Final[litestar.Request] = litestar.Request(request_scope)  # type: ignore[type-arg]

            request_path = request.url.path.removesuffix("/")

            if request_path in endpoints_to_ignore:
                await self.app(request_scope, receive, send_function)
                return

            start_time: typing.Final[int] = time.perf_counter_ns()

            async def log_message_wrapper(message: litestar.types.Message) -> None:
                if message["type"] == "http.response.start":
                    status = message["status"]
                    log_level: str = "info" if status < HTTP_500_INTERNAL_SERVER_ERROR else "exception"
                    fill_log_message(log_level, request, status, start_time)

                await send_function(message)

            await self.app(request_scope, receive, log_message_wrapper)

    return LitestarLoggingMiddleware
