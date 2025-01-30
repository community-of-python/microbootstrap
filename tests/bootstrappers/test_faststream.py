import typing
from unittest.mock import MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from faststream.redis import RedisBroker, TestRedisBroker
from faststream.redis.prometheus import RedisPrometheusMiddleware

from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
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
