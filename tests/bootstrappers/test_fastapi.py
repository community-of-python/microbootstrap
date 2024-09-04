import typing
from unittest.mock import MagicMock

from litestar import status_codes
from litestar.testing import AsyncTestClient

from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments.prometheus_instrument import FastApiPrometheusConfig
from microbootstrap.settings import FastApiSettings


async def test_fastapi_configure_instrument() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_instrument(
            FastApiPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    async with AsyncTestClient(app=application) as async_client:
        response: typing.Final = await async_client.get(test_metrics_path)
        assert response.status_code == status_codes.HTTP_200_OK


async def test_fastapi_configure_instruments() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"
    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_instruments(
            FastApiPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    async with AsyncTestClient(app=application) as async_client:
        response: typing.Final = await async_client.get(test_metrics_path)
        assert response.status_code == status_codes.HTTP_200_OK


async def test_fastapi_configure_application() -> None:
    test_title: typing.Final = "new-title"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings()).configure_application(FastApiConfig(title=test_title)).bootstrap()
    )

    assert application.title == test_title


async def test_fastapi_configure_application_add_startup_event(magic_mock: MagicMock) -> None:
    def test_startup() -> None:
        magic_mock()

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_application(FastApiConfig(on_startup=[test_startup]))
        .bootstrap()
    )

    async with AsyncTestClient(app=application):
        assert magic_mock.called
