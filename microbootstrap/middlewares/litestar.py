from __future__ import annotations
import time
import typing

import litestar
import litestar.types
from litestar.middleware.base import MiddlewareProtocol
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from microbootstrap.middlewares.logging import fill_log_message
from microbootstrap.middlewares.logging_level import LogLevel


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
            if message["type"] == "http.response.start":
                log_level: typing.Final[LogLevel] = (
                    LogLevel.INFO if message["status"] < HTTP_500_INTERNAL_SERVER_ERROR else LogLevel.EXCEPTION
                )
                fill_log_message(log_level, request, message["status"], start_time)

            await send_function(message)

        await self.app(request_scope, receive, log_message_wrapper)


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

            async def not_log_message_wrapper(message: litestar.types.Message) -> None:
                await send_function(message)

            for one_exclude_endpoint in exclude_endpoints:
                if one_exclude_endpoint in str(request.url):
                    await self.app(
                        request_scope,
                        receive,
                        not_log_message_wrapper,
                    )
                    return

            start_time: typing.Final[int] = time.perf_counter_ns()

            async def log_message_wrapper(message: litestar.types.Message) -> None:
                if message["type"] == "http.response.start":
                    log_level: typing.Final[LogLevel] = (
                        LogLevel.INFO if message["status"] < HTTP_500_INTERNAL_SERVER_ERROR else LogLevel.EXCEPTION
                    )
                    fill_log_message(log_level, request, message["status"], start_time)

                await send_function(message)

            await self.app(request_scope, receive, log_message_wrapper)

    return LitestarLoggingMiddleware
