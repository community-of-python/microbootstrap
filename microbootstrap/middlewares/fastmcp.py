from __future__ import annotations
import time
import typing

import prometheus_client
import structlog
from fastmcp.server.middleware import Middleware, MiddlewareContext


if typing.TYPE_CHECKING:
    import mcp.types as mcp_types
    from fastmcp.server.middleware import CallNext
    from fastmcp.tools.base import ToolResult


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


TOOL_CALL_STATUS_SUCCESS: typing.Final = "success"
TOOL_CALL_STATUS_ERROR: typing.Final = "error"


class FastMcpPrometheusMiddleware(Middleware):
    def __init__(
        self,
        registry: prometheus_client.CollectorRegistry | None = None,
        custom_labels: dict[str, str] | None = None,
        duration_buckets: typing.Sequence[float] = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, float("inf")),
    ) -> None:
        self.custom_labels: typing.Final = custom_labels or {}
        self.tool_calls_total: typing.Final = prometheus_client.Counter(
            name="fastmcp_tool_calls_total",
            documentation="Number of MCP tool calls by tool and outcome.",
            labelnames=["tool", "status", *self.custom_labels],
            registry=registry or prometheus_client.REGISTRY,
        )
        self.tool_call_duration_seconds: typing.Final = prometheus_client.Histogram(
            name="fastmcp_tool_call_duration_seconds",
            documentation="Duration of MCP tool calls by tool.",
            labelnames=["tool", *self.custom_labels],
            buckets=duration_buckets,
            registry=registry or prometheus_client.REGISTRY,
        )

    async def on_call_tool(
        self,
        context: MiddlewareContext[mcp_types.CallToolRequestParams],
        call_next: CallNext[mcp_types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        tool_name: typing.Final = context.message.name
        start_time: typing.Final = time.perf_counter()
        try:
            result: typing.Final = await call_next(context)
        except Exception:
            self.tool_calls_total.labels(tool=tool_name, status=TOOL_CALL_STATUS_ERROR, **self.custom_labels).inc()
            raise
        else:
            self.tool_calls_total.labels(tool=tool_name, status=TOOL_CALL_STATUS_SUCCESS, **self.custom_labels).inc()
            return result
        finally:
            self.tool_call_duration_seconds.labels(tool=tool_name, **self.custom_labels).observe(
                time.perf_counter() - start_time
            )
