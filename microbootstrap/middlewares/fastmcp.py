from __future__ import annotations
import time
import typing

import structlog
from fastmcp.server.middleware import Middleware, MiddlewareContext


if typing.TYPE_CHECKING:
    from fastmcp.server.middleware import CallNext


fastmcp_access_logger: typing.Final = structlog.get_logger("mcp.access")


class FastMcpLoggingMiddleware(Middleware):
    async def on_message(
        self,
        context: MiddlewareContext[typing.Any],
        call_next: CallNext[typing.Any, typing.Any],
    ) -> typing.Any:  # noqa: ANN401
        start_time: typing.Final = time.perf_counter_ns()
        try:
            result: typing.Final = await call_next(context)
        except Exception:
            fastmcp_access_logger.exception(
                context.method or "unknown",
                mcp={
                    "method": context.method,
                    "source": context.source,
                    "type": context.type,
                },
                duration=time.perf_counter_ns() - start_time,
            )
            raise

        fastmcp_access_logger.info(
            context.method or "unknown",
            mcp={
                "method": context.method,
                "source": context.source,
                "type": context.type,
            },
            duration=time.perf_counter_ns() - start_time,
        )
        return result
