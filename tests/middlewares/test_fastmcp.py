import typing
from unittest.mock import MagicMock

import pytest
from fastmcp.server.middleware import MiddlewareContext

from microbootstrap.middlewares.fastmcp import FastMcpLoggingMiddleware


async def test_fastmcp_logging_middleware_logs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_logger: typing.Final = MagicMock()
    middleware: typing.Final = FastMcpLoggingMiddleware()
    middleware_context: typing.Final = MiddlewareContext(
        message={"payload": "test"},
        method="tools/list",
        source="client",
        type="request",
    )

    async def call_next(context: MiddlewareContext[typing.Any]) -> dict[str, str]:
        assert context is middleware_context
        return {"status": "ok"}

    monkeypatch.setattr("microbootstrap.middlewares.fastmcp.fastmcp_access_logger", fake_logger)

    result: typing.Final = await middleware.on_message(middleware_context, call_next)

    assert result == {"status": "ok"}
    fake_logger.info.assert_called_once()


async def test_fastmcp_logging_middleware_logs_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_logger: typing.Final = MagicMock()
    middleware: typing.Final = FastMcpLoggingMiddleware()
    middleware_context: typing.Final = MiddlewareContext(
        message={"payload": "test"},
        method="tools/call",
        source="client",
        type="request",
    )

    async def call_next(context: MiddlewareContext[typing.Any]) -> dict[str, str]:
        assert context is middleware_context
        msg = "MCP call failed"
        raise RuntimeError(msg)

    monkeypatch.setattr("microbootstrap.middlewares.fastmcp.fastmcp_access_logger", fake_logger)

    with pytest.raises(RuntimeError, match="MCP call failed"):
        await middleware.on_message(middleware_context, call_next)

    fake_logger.exception.assert_called_once()
