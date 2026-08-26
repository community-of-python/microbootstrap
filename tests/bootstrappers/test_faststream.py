import asyncio
import logging
import typing
from unittest import mock
from unittest.mock import MagicMock

import faker
import pytest
import sentry_sdk
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
from microbootstrap.instruments.sentry_instrument import SentryConfig
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


async def test_faststream_sentry_isolates_concurrent_messages(
    broker: RedisBroker,
    minimal_sentry_config: SentryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel: typing.Final = "test-channel"
    conversation_id_tag: typing.Final = "conversation_id"
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    second_logged = asyncio.Event()
    captured_tags: dict[str, str | None] = {}
    monkeypatch.setattr(sentry_sdk, "init", mock.Mock())
    minimal_sentry_config.sentry_tags = None

    @broker.subscriber(channel)
    async def handler(conversation_id: str) -> None:
        sentry_sdk.get_isolation_scope().set_tag(conversation_id_tag, conversation_id)
        if conversation_id == "first":
            first_started.set()
            await second_started.wait()
            await second_logged.wait()
        else:
            second_started.set()
            await first_started.wait()
        raise ValueError(conversation_id)

    FastStreamBootstrapper(FastStreamSettings()).configure_application(
        FastStreamConfig(broker=broker)
    ).configure_instruments(minimal_sentry_config).bootstrap()

    original_log = broker.config.logger.log

    def record_error_tag(*args: typing.Any, **kwargs: typing.Any) -> None:  # noqa: ANN401
        if kwargs.get("log_level") == logging.ERROR:
            error_message = typing.cast("str", kwargs["message"])
            captured_tags[error_message] = sentry_sdk.get_isolation_scope()._tags.get(conversation_id_tag)  # noqa: SLF001
            if error_message.endswith("second"):
                second_logged.set()
        original_log(*args, **kwargs)

    monkeypatch.setattr(broker.config.logger, "log", record_error_tag)
    event_loop = asyncio.get_running_loop()
    previous_exception_handler = event_loop.get_exception_handler()
    event_loop.set_exception_handler(lambda *_: None)
    try:
        async with TestRedisBroker(broker):
            errors: typing.Final = await asyncio.gather(
                broker.publish("first", channel),
                broker.publish("second", channel),
                return_exceptions=True,
            )
    finally:
        event_loop.set_exception_handler(previous_exception_handler)

    assert all(isinstance(error, ValueError) for error in errors)
    assert captured_tags == {
        "ValueError: first": "first",
        "ValueError: second": "second",
    }
    assert conversation_id_tag not in sentry_sdk.get_isolation_scope()._tags  # noqa: SLF001


async def test_faststream_sentry_isolates_broker_configured_on_startup(
    broker: RedisBroker,
    minimal_sentry_config: SentryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application: typing.Any

    @broker.subscriber("test-channel")
    async def handler(message: str) -> None:
        pass

    def set_broker() -> None:
        application.set_broker(broker)

    monkeypatch.setattr(sentry_sdk, "init", mock.Mock())
    monkeypatch.setattr(broker, "start", mock.AsyncMock())
    application = (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_application(FastStreamConfig(on_startup=[set_broker]))
        .configure_instruments(minimal_sentry_config)
        .bootstrap()
    )

    await application.start()

    assert hasattr(broker.subscribers[0].process_message, "__wrapped__")
