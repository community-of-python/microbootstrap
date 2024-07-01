from __future__ import annotations
import typing
from uuid import uuid4

import litestar
import pytest
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from litestar.contrib.prometheus import PrometheusController


if typing.TYPE_CHECKING:
    from litestar.handlers.http_handlers.base import HTTPRouteHandler


def simple_request_hook(*_args: object, **_kwargs: object) -> None:
    """Request hook that do nothing."""


class CustomPrometheusController(PrometheusController):
    path = "/custom-metrics"
    openmetrics_format = True


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Anyio backend.

    Backend for anyio pytest plugin.
    """
    return "asyncio"


@pytest.fixture()
def default_response_content() -> dict[str, str]:
    """Just default response content."""
    return {uuid4().hex: uuid4().hex}


@pytest.fixture()
def fastapi_app(default_response_content: dict[str, str]) -> FastAPI:
    """Build fastapi application with one endpoint."""
    test_fastapi_app: typing.Final[FastAPI] = FastAPI()
    test_fastapi_router: typing.Final[APIRouter] = APIRouter()

    @test_fastapi_router.get("/test")
    async def for_test_endpoint() -> JSONResponse:
        structlog.get_logger().info("Test log here!")
        return JSONResponse(content=default_response_content)

    test_fastapi_app.include_router(test_fastapi_router)

    return test_fastapi_app


@pytest.fixture()
def test_litestar_endpoint(
    default_response_content: dict[str, str],
) -> HTTPRouteHandler:
    @litestar.get("/test")
    async def endpoint() -> typing.Dict[str, str]:  # noqa: UP006
        structlog.get_logger().info("Test log here!")
        return default_response_content

    return endpoint


@pytest.fixture()
def health_litestar_endpoint(
    default_response_content: dict[str, str],
) -> HTTPRouteHandler:
    @litestar.get("/health")
    async def endpoint() -> typing.Dict[str, str]:  # noqa: UP006
        return default_response_content

    return endpoint
