import typing
from unittest.mock import MagicMock

import litestar
from litestar import status_codes
from litestar.config.app import AppConfig
from litestar.middleware.base import MiddlewareProtocol
from litestar.testing import AsyncTestClient
from litestar.types import ASGIApp, Receive, Scope, Send

from microbootstrap import LitestarSettings, PrometheusConfig
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper


async def test_litestar_configure_instrument() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"
    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_instrument(
            PrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    async with AsyncTestClient(app=application) as async_client:
        response: typing.Final = await async_client.get(test_metrics_path)
        assert response.status_code == status_codes.HTTP_200_OK


async def test_litestar_configure_application_add_handler() -> None:
    test_handler_path: typing.Final = "/test-handler"
    test_response: typing.Final = {"hello": "world"}

    @litestar.get(test_handler_path)
    async def test_handler() -> dict[str, str]:
        return test_response

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_application(AppConfig(route_handlers=[test_handler]))
        .bootstrap()
    )

    async with AsyncTestClient(app=application) as async_client:
        response: typing.Final = await async_client.get(test_handler_path)
        assert response.status_code == status_codes.HTTP_200_OK
        assert response.json() == test_response


async def test_litestar_configure_application_add_middleware(magic_mock: MagicMock) -> None:
    test_handler_path: typing.Final = "/test-handler"

    class TestMiddleware(MiddlewareProtocol):
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            magic_mock()
            await self.app(scope, receive, send)

    @litestar.get(test_handler_path)
    async def test_handler() -> str:
        return "Ok"

    application: typing.Final = (
        LitestarBootstrapper(LitestarSettings())
        .configure_application(AppConfig(route_handlers=[test_handler], middleware=[TestMiddleware]))
        .bootstrap()
    )

    async with AsyncTestClient(app=application) as async_client:
        response: typing.Final = await async_client.get(test_handler_path)
        assert response.status_code == status_codes.HTTP_200_OK
        assert magic_mock.called