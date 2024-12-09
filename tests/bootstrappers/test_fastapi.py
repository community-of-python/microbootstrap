import typing
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient

from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments.prometheus_instrument import FastApiPrometheusConfig
from microbootstrap.settings import FastApiSettings


def test_fastapi_configure_instrument() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_instrument(
            FastApiPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_fastapi_configure_instruments() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"
    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings())
        .configure_instruments(
            FastApiPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_fastapi_configure_application() -> None:
    test_title: typing.Final = "new-title"

    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings()).configure_application(FastApiConfig(title=test_title)).bootstrap()
    )

    assert application.title == test_title


def test_fastapi_configure_application_lifespan(magic_mock: MagicMock) -> None:
    application: typing.Final = (
        FastApiBootstrapper(FastApiSettings()).configure_application(FastApiConfig(lifespan=magic_mock)).bootstrap()
    )

    with TestClient(app=application):
        assert magic_mock.called
