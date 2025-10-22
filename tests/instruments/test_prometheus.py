import typing

import fastapi
import litestar
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from faststream.redis import RedisBroker, TestRedisBroker
from faststream.redis.prometheus import RedisPrometheusMiddleware
from litestar import status_codes
from litestar.middleware.base import DefineMiddleware
from litestar.testing import TestClient as LitestarTestClient
from prometheus_client import REGISTRY

from microbootstrap import FastApiPrometheusConfig, FastStreamSettings, LitestarPrometheusConfig
from microbootstrap.bootstrappers.fastapi import FastApiPrometheusInstrument
from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper
from microbootstrap.bootstrappers.litestar import LitestarPrometheusInstrument
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.prometheus_instrument import (
    BasePrometheusConfig,
    FastStreamPrometheusConfig,
    PrometheusInstrument,
)


def check_is_metrics_has_labels(custom_labels_keys: set[str]) -> bool:
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            label_keys = set(sample.labels.keys())
            if custom_labels_keys & label_keys:
                return True
    return False


def test_prometheus_is_ready(minimal_base_prometheus_config: BasePrometheusConfig) -> None:
    prometheus_instrument: typing.Final = PrometheusInstrument(minimal_base_prometheus_config)
    assert prometheus_instrument.is_ready()


def test_prometheus_bootstrap_is_not_ready(
    minimal_base_prometheus_config: BasePrometheusConfig,
) -> None:
    minimal_base_prometheus_config.prometheus_metrics_path = ""
    prometheus_instrument: typing.Final = PrometheusInstrument(minimal_base_prometheus_config)
    assert not prometheus_instrument.is_ready()


def test_prometheus_bootstrap_after(
    default_litestar_app: litestar.Litestar,
    minimal_base_prometheus_config: BasePrometheusConfig,
) -> None:
    prometheus_instrument: typing.Final = PrometheusInstrument(minimal_base_prometheus_config)
    assert prometheus_instrument.bootstrap_after(default_litestar_app) == default_litestar_app


def test_prometheus_teardown(
    minimal_base_prometheus_config: BasePrometheusConfig,
) -> None:
    prometheus_instrument: typing.Final = PrometheusInstrument(minimal_base_prometheus_config)
    assert prometheus_instrument.teardown() is None  # type: ignore[func-returns-value]


def test_litestar_prometheus_bootstrap(minimal_litestar_prometheus_config: LitestarPrometheusConfig) -> None:
    prometheus_instrument: typing.Final = LitestarPrometheusInstrument(minimal_litestar_prometheus_config)
    prometheus_instrument.bootstrap()
    prometheus_bootstrap_result: typing.Final = prometheus_instrument.bootstrap_before()

    assert prometheus_bootstrap_result
    assert "route_handlers" in prometheus_bootstrap_result
    assert isinstance(prometheus_bootstrap_result["route_handlers"], list)
    assert len(prometheus_bootstrap_result["route_handlers"]) == 1
    assert "middleware" in prometheus_bootstrap_result
    assert isinstance(prometheus_bootstrap_result["middleware"], list)
    assert len(prometheus_bootstrap_result["middleware"]) == 1
    assert isinstance(prometheus_bootstrap_result["middleware"][0], DefineMiddleware)


def test_litestar_prometheus_bootstrap_working(
    minimal_litestar_prometheus_config: LitestarPrometheusConfig,
) -> None:
    minimal_litestar_prometheus_config.prometheus_metrics_path = "/custom-metrics-path"
    prometheus_instrument: typing.Final = LitestarPrometheusInstrument(minimal_litestar_prometheus_config)

    prometheus_instrument.bootstrap()
    litestar_application: typing.Final = litestar.Litestar(
        **prometheus_instrument.bootstrap_before(),
    )

    with LitestarTestClient(app=litestar_application) as test_client:
        response: typing.Final = test_client.get(minimal_litestar_prometheus_config.prometheus_metrics_path)
        assert response.status_code == status_codes.HTTP_200_OK
        assert response.text


def test_fastapi_prometheus_bootstrap_working(minimal_fastapi_prometheus_config: FastApiPrometheusConfig) -> None:
    minimal_fastapi_prometheus_config.prometheus_metrics_path = "/custom-metrics-path"
    prometheus_instrument: typing.Final = FastApiPrometheusInstrument(minimal_fastapi_prometheus_config)

    fastapi_application = fastapi.FastAPI()
    fastapi_application = prometheus_instrument.bootstrap_after(fastapi_application)

    response: typing.Final = FastAPITestClient(app=fastapi_application).get(
        minimal_fastapi_prometheus_config.prometheus_metrics_path
    )
    assert response.status_code == status_codes.HTTP_200_OK
    assert response.text


@pytest.mark.parametrize(
    ("custom_labels", "expected_label_keys"),
    [
        ({"test_label": "test_value"}, {"test_label"}),
        ({}, {"method", "handler", "status"}),
    ],
)
def test_fastapi_prometheus_custom_labels(
    minimal_fastapi_prometheus_config: FastApiPrometheusConfig,
    custom_labels: dict[str, str],
    expected_label_keys: set[str],
) -> None:
    minimal_fastapi_prometheus_config.prometheus_custom_labels = custom_labels
    prometheus_instrument: typing.Final = FastApiPrometheusInstrument(minimal_fastapi_prometheus_config)

    fastapi_application = fastapi.FastAPI()
    fastapi_application = prometheus_instrument.bootstrap_after(fastapi_application)

    response: typing.Final = FastAPITestClient(app=fastapi_application).get(
        minimal_fastapi_prometheus_config.prometheus_metrics_path
    )

    assert response.status_code == status_codes.HTTP_200_OK
    assert check_is_metrics_has_labels(expected_label_keys)


@pytest.mark.parametrize(
    ("custom_labels", "expected_label_keys"),
    [
        ({"test_label": "test_value"}, {"test_label"}),
        ({}, {"app_name", "broker", "handler"}),
    ],
)
async def test_faststream_prometheus_custom_labels(
    minimal_faststream_prometheus_config: FastStreamPrometheusConfig,
    custom_labels: dict[str, str],
    expected_label_keys: set[str],
) -> None:
    minimal_faststream_prometheus_config.prometheus_custom_labels = custom_labels
    minimal_faststream_prometheus_config.prometheus_middleware_cls = RedisPrometheusMiddleware  # type: ignore[assignment]

    broker: typing.Final = RedisBroker()
    (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_application(FastStreamConfig(broker=broker))
        .configure_instrument(minimal_faststream_prometheus_config)
        .bootstrap()
    )

    def create_test_redis_subscriber(
        broker: RedisBroker,
        topic: str,
    ) -> typing.Callable[[dict[str, str]], typing.Coroutine[typing.Any, typing.Any, None]]:
        @broker.subscriber(topic)
        async def test_subscriber(payload: dict[str, str]) -> None:
            pass

        return test_subscriber

    create_test_redis_subscriber(broker, topic="test-topic")

    async with TestRedisBroker(broker) as tb:
        await tb.publish({"foo": "bar"}, "test-topic")
        assert check_is_metrics_has_labels(expected_label_keys)
