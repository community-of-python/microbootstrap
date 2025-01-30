import typing
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.prometheus_instrument import FastStreamPrometheusConfig
from microbootstrap.settings import FastStreamSettings


def test_faststream_configure_instrument() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"

    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_instrument(
            FastStreamPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_faststream_configure_instruments() -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"
    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_instruments(
            FastStreamPrometheusConfig(prometheus_metrics_path=test_metrics_path),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_faststream_configure_application() -> None:
    test_title: typing.Final = "new-title"

    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings()).configure_application(FastStreamConfig(title=test_title)).bootstrap()
    )

    assert application.title == test_title


def test_faststream_configure_application_lifespan(magic_mock: MagicMock) -> None:
    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings()).configure_application(FastStreamConfig(lifespan=magic_mock)).bootstrap()
    )

    with TestClient(app=application):
        assert magic_mock.called
