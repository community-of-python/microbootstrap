from __future__ import annotations
import time
import typing

import litestar
import litestar.types
from litestar.middleware.base import MiddlewareProtocol
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from microbootstrap.instruments.logging_instrument import fill_log_message


def build_litestar_logging_middleware(
    exclude_endpoints: typing.Iterable[str],
) -> type[MiddlewareProtocol]:
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
            start_time: typing.Final[int] = time.perf_counter_ns()

            async def log_message_wrapper(message: litestar.types.Message) -> None:
                should_log: typing.Final = not any(
                    exclude_endpoint in str(request.url) for exclude_endpoint in exclude_endpoints
                )
                if message["type"] == "http.response.start" and should_log:
                    log_level: str = "info" if message["status"] < HTTP_500_INTERNAL_SERVER_ERROR else "exception"
                    fill_log_message(log_level, request, message["status"], start_time)

                await send_function(message)

            await self.app(request_scope, receive, log_message_wrapper)

    return LitestarLoggingMiddleware
