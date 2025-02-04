import typing
from unittest import mock
from unittest.mock import MagicMock

import faker
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from faststream.redis import RedisBroker, TestRedisBroker
from faststream.redis.opentelemetry import RedisTelemetryMiddleware
from faststream.redis.prometheus import RedisPrometheusMiddleware

from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.health_checks_instrument import HealthChecksConfig
from microbootstrap.instruments.logging_instrument import LoggingConfig
from microbootstrap.instruments.opentelemetry_instrument import FastStreamOpentelemetryConfig, OpentelemetryConfig
from microbootstrap.instruments.prometheus_instrument import FastStreamPrometheusConfig
from microbootstrap.settings import FastStreamSettings


@pytest.fixture
def broker() -> RedisBroker:
    return RedisBroker()


async def test_faststream_configure_instrument(broker: RedisBroker) -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"

    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_application(FastStreamConfig(broker=broker))
        .configure_instrument(
            FastStreamPrometheusConfig(
                prometheus_metrics_path=test_metrics_path, prometheus_middleware_cls=RedisPrometheusMiddleware
            ),
        )
        .bootstrap()
    )

    async with TestRedisBroker(broker):
        response: typing.Final = TestClient(app=application).get(test_metrics_path)
        assert response.status_code == status.HTTP_200_OK


def test_faststream_configure_instruments(broker: RedisBroker) -> None:
    test_metrics_path: typing.Final = "/test-metrics-path"
    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_application(FastStreamConfig(broker=broker))
        .configure_instruments(
            FastStreamPrometheusConfig(
                prometheus_metrics_path=test_metrics_path, prometheus_middleware_cls=RedisPrometheusMiddleware
            ),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(app=application).get(test_metrics_path)
    assert response.status_code == status.HTTP_200_OK


def test_faststream_configure_application_lifespan(broker: RedisBroker, magic_mock: MagicMock) -> None:
    application: typing.Final = (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_application(FastStreamConfig(broker=broker, lifespan=magic_mock))
        .bootstrap()
    )

    with TestClient(app=application):
        assert magic_mock.called


class TestFastStreamHealthCheck:
    def test_500(self, broker: RedisBroker) -> None:
        test_health_path: typing.Final = "/test-health-path"
        application: typing.Final = (
            FastStreamBootstrapper(FastStreamSettings())
            .configure_application(FastStreamConfig(broker=broker))
            .configure_instruments(HealthChecksConfig(health_checks_path=test_health_path))
            .bootstrap()
        )

        response: typing.Final = TestClient(app=application).get(test_health_path)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    async def test_ok(self, broker: RedisBroker) -> None:
        test_health_path: typing.Final = "/test-health-path"
        application: typing.Final = (
            FastStreamBootstrapper(FastStreamSettings())
            .configure_application(FastStreamConfig(broker=broker))
            .configure_instruments(HealthChecksConfig(health_checks_path=test_health_path))
            .bootstrap()
        )

        async with TestRedisBroker(broker):
            response: typing.Final = TestClient(app=application).get(test_health_path)
        assert response.status_code == status.HTTP_200_OK


async def test_faststream_opentelemetry(
    monkeypatch: pytest.MonkeyPatch,
    faker: faker.Faker,
    broker: RedisBroker,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", mock.Mock())

    FastStreamBootstrapper(FastStreamSettings()).configure_application(
        FastStreamConfig(broker=broker)
    ).configure_instruments(
        FastStreamOpentelemetryConfig(
            opentelemetry_middleware_cls=RedisTelemetryMiddleware, **minimal_opentelemetry_config.model_dump()
        )
    ).bootstrap()

    async with TestRedisBroker(broker):
        with mock.patch("opentelemetry.trace.use_span") as mock_capture_event:
            await broker.publish(faker.pystr(), channel=faker.pystr())
            assert mock_capture_event.called


async def test_faststream_logging(broker: RedisBroker, minimal_logging_config: LoggingConfig) -> None:
    FastStreamBootstrapper(FastStreamSettings()).configure_application(
        FastStreamConfig(broker=broker)
    ).configure_instruments(minimal_logging_config).bootstrap()
