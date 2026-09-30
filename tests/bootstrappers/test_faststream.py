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
from faststream.asgi import AsgiFastStream
from faststream.redis import RedisBroker, TestRedisBroker
from faststream.redis.opentelemetry import RedisTelemetryMiddleware
from faststream.redis.prometheus import RedisPrometheusMiddleware
from opentelemetry import baggage, trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from microbootstrap import opentelemetry_baggage_scope
from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper, build_faststream_route_details_from_scope
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksConfig
from microbootstrap.instruments.logging_instrument import LoggingConfig
from microbootstrap.instruments.opentelemetry_instrument import FastStreamOpentelemetryConfig, OpentelemetryConfig
from microbootstrap.instruments.prometheus_instrument import FastStreamPrometheusConfig
from microbootstrap.instruments.sentry_instrument import SentryConfig
from microbootstrap.middlewares.faststream import FastStreamOpenTelemetryBaggageMiddleware
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


@pytest.mark.parametrize("conversation_id", ["authoritative-value", None])
async def test_faststream_opentelemetry(
    monkeypatch: pytest.MonkeyPatch,
    faker: faker.Faker,
    broker: RedisBroker,
    minimal_opentelemetry_config: OpentelemetryConfig,
    conversation_id: str | None,
) -> None:
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", mock.Mock())
    input_channel: typing.Final = faker.pystr()
    output_channel: typing.Final = faker.pystr()
    conversation_id_span_attribute: typing.Final = "conversation.id"
    observed_context: list[tuple[object | None, object | None, object | None]] = []
    minimal_opentelemetry_config.opentelemetry_baggage_span_attributes = {
        "conversation_id": conversation_id_span_attribute
    }

    @broker.subscriber(input_channel)
    async def handler(_: str) -> None:
        with opentelemetry_baggage_scope(
            {"conversation_id": conversation_id},
            current_span_attributes={"conversation_id": conversation_id_span_attribute},
        ):
            await broker.publish(faker.pystr(), channel=output_channel)

    @broker.subscriber(output_channel)
    async def capture_context(_: str) -> None:
        current_span: typing.Final = trace.get_current_span()
        observed_context.append(
            (
                baggage.get_baggage("conversation_id"),
                baggage.get_baggage("existing_key"),
                current_span.attributes.get(conversation_id_span_attribute),  # type: ignore[attr-defined]
            )
        )

    FastStreamBootstrapper(FastStreamSettings()).configure_application(
        FastStreamConfig(broker=broker)
    ).configure_instruments(
        FastStreamOpentelemetryConfig(
            opentelemetry_middleware_cls=RedisTelemetryMiddleware,
            **minimal_opentelemetry_config.model_dump(),
        )
    ).bootstrap()

    async with TestRedisBroker(broker):
        with opentelemetry_baggage_scope({"conversation_id": "stale-value", "existing_key": "existing-value"}):
            await broker.publish(faker.pystr(), channel=input_channel)

    assert observed_context == [(conversation_id, "existing-value", conversation_id)]
    assert baggage.get_baggage("conversation_id") is None


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


async def test_faststream_sentry_automatic_errors_use_concurrent_baggage_snapshots(
    broker: RedisBroker,
    minimal_sentry_config: SentryConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel: typing.Final = "test-channel"
    conversation_id_tag: typing.Final = "conversation_id"
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    second_captured = asyncio.Event()
    captured_tags: dict[str, str | None] = {}

    init = mock.Mock()
    monkeypatch.setattr(sentry_sdk, "init", init)
    minimal_sentry_config.sentry_tags = None
    minimal_sentry_config.sentry_opentelemetry_baggage_keys = {conversation_id_tag}

    @broker.subscriber(channel)
    async def handler(conversation_id: str) -> None:
        with opentelemetry_baggage_scope({conversation_id_tag: conversation_id}):
            if conversation_id == "first":
                first_started.set()
                await second_started.wait()
                await second_captured.wait()
            else:
                second_started.set()
                await first_started.wait()
            raise ValueError(conversation_id)

    FastStreamBootstrapper(FastStreamSettings()).configure_application(
        FastStreamConfig(broker=broker)
    ).configure_instruments(minimal_sentry_config).bootstrap()

    baggage_integration: typing.Final = next(
        integration
        for integration in init.call_args.kwargs["integrations"]
        if integration.identifier == "microbootstrap_opentelemetry_baggage"
    )
    client = mock.Mock()
    client.get_integration.return_value = baggage_integration
    monkeypatch.setattr(sentry_sdk, "get_client", mock.Mock(return_value=client))
    before_send: typing.Final = init.call_args.kwargs["before_send"]
    original_log = broker.config.logger.log

    def record_automatic_error(*args: typing.Any, **kwargs: typing.Any) -> None:  # noqa: ANN401
        if kwargs.get("log_level") == logging.ERROR:
            exception = typing.cast("ValueError", kwargs["exc_info"])
            event = before_send(
                {},
                {"exc_info": (type(exception), exception, exception.__traceback__)},
            )
            captured_tags[str(exception)] = event.get("tags", {}).get(conversation_id_tag)
            if str(exception) == "second":
                second_captured.set()
        original_log(*args, **kwargs)

    monkeypatch.setattr(broker.config.logger, "log", record_automatic_error)

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
    assert captured_tags == {"first": "first", "second": "second"}


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


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter: typing.Final = InMemorySpanExporter()

    def build_tracer_provider(*args: typing.Any, **kwargs: typing.Any) -> SdkTracerProvider:  # noqa: ANN401
        tracer_provider: typing.Final = SdkTracerProvider(*args, **kwargs)
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        return tracer_provider

    monkeypatch.setattr(opentelemetry_instrument, "SdkTracerProvider", build_tracer_provider)
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", mock.Mock())
    monkeypatch.setattr(_OpenTelemetrySemanticConventionStability, "_initialized", False)
    return exporter


def build_faststream_application_with_opentelemetry(
    broker: RedisBroker,
    **opentelemetry_params: typing.Any,  # noqa: ANN401
) -> AsgiFastStream:
    return (
        FastStreamBootstrapper(FastStreamSettings())
        .configure_application(FastStreamConfig(broker=broker))
        .configure_instruments(
            FastStreamOpentelemetryConfig(
                opentelemetry_log_traces=True,
                opentelemetry_middleware_cls=RedisTelemetryMiddleware,
                **opentelemetry_params,
            ),
            FastStreamPrometheusConfig(prometheus_middleware_cls=RedisPrometheusMiddleware),
        )
        .bootstrap()
    )


def find_server_spans(span_exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [span for span in span_exporter.get_finished_spans() if span.kind == SpanKind.SERVER]


class TestFastStreamHttpOpentelemetry:
    @pytest.mark.parametrize(
        ("semconv_opt_in", "expected_status_attributes"),
        [
            (None, {"http.status_code"}),
            ("http", {"http.response.status_code"}),
            ("http/dup", {"http.status_code", "http.response.status_code"}),
        ],
    )
    async def test_health_check_server_span(
        self,
        monkeypatch: pytest.MonkeyPatch,
        broker: RedisBroker,
        span_exporter: InMemorySpanExporter,
        semconv_opt_in: str | None,
        expected_status_attributes: set[str],
    ) -> None:
        if semconv_opt_in is None:
            monkeypatch.delenv(OTEL_SEMCONV_STABILITY_OPT_IN, raising=False)
        else:
            monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, semconv_opt_in)
        application: typing.Final = build_faststream_application_with_opentelemetry(broker)

        async with TestRedisBroker(broker):
            response: typing.Final = TestClient(app=application).get("/health/")

        assert response.status_code == status.HTTP_200_OK
        assert [span.name for span in span_exporter.get_finished_spans() if span.name == "GET /health/"] == [
            "GET /health/"
        ]
        server_spans: typing.Final = find_server_spans(span_exporter)
        assert len(server_spans) == 1
        assert server_spans[0].name == "GET /health/"
        assert server_spans[0].attributes
        assert server_spans[0].attributes["http.route"] == "/health/"
        assert {
            attribute_name: server_spans[0].attributes[attribute_name]
            for attribute_name in ("http.status_code", "http.response.status_code")
            if attribute_name in server_spans[0].attributes
        } == dict.fromkeys(expected_status_attributes, status.HTTP_200_OK)

    def test_unhealthy_broker_server_span(
        self,
        monkeypatch: pytest.MonkeyPatch,
        broker: RedisBroker,
        span_exporter: InMemorySpanExporter,
    ) -> None:
        monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, "http")
        application: typing.Final = build_faststream_application_with_opentelemetry(broker)

        response: typing.Final = TestClient(app=application).get("/health/")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        server_spans: typing.Final = find_server_spans(span_exporter)
        assert len(server_spans) == 1
        assert server_spans[0].attributes
        assert server_spans[0].attributes["http.response.status_code"] == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert server_spans[0].status.status_code == StatusCode.ERROR

    def test_metrics_are_excluded(self, broker: RedisBroker, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_faststream_application_with_opentelemetry(broker)

        response: typing.Final = TestClient(app=application).get("/metrics")

        assert response.status_code == status.HTTP_200_OK
        assert not span_exporter.get_finished_spans()

    def test_health_check_spans_disabled(self, broker: RedisBroker, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_faststream_application_with_opentelemetry(
            broker, opentelemetry_generate_health_check_spans=False
        )
        client: typing.Final = TestClient(app=application)

        client.get("/health/")
        assert not span_exporter.get_finished_spans()

        response: typing.Final = client.get("/asyncapi")
        assert response.status_code == status.HTTP_200_OK
        server_spans: typing.Final = find_server_spans(span_exporter)
        assert [span.name for span in server_spans] == ["GET /asyncapi"]

    def test_unknown_route_has_no_http_route(self, broker: RedisBroker, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_faststream_application_with_opentelemetry(broker)

        response: typing.Final = TestClient(app=application).get("/unknown")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        server_spans: typing.Final = find_server_spans(span_exporter)
        assert len(server_spans) == 1
        assert server_spans[0].name == "GET"
        assert server_spans[0].attributes is not None
        assert "http.route" not in server_spans[0].attributes

    def test_server_spans_without_broker_middleware(
        self, broker: RedisBroker, span_exporter: InMemorySpanExporter
    ) -> None:
        application: typing.Final = (
            FastStreamBootstrapper(FastStreamSettings())
            .configure_application(FastStreamConfig(broker=broker))
            .configure_instruments(FastStreamOpentelemetryConfig(opentelemetry_log_traces=True))
            .bootstrap()
        )

        TestClient(app=application).get("/health/")

        assert [span.name for span in find_server_spans(span_exporter)] == ["GET /health/"]
        assert not any(
            isinstance(middleware, (RedisTelemetryMiddleware, FastStreamOpenTelemetryBaggageMiddleware))
            for middleware in application.broker.middlewares  # type: ignore[union-attr]
        )

    async def test_broker_spans_are_not_duplicated(
        self, faker: faker.Faker, broker: RedisBroker, span_exporter: InMemorySpanExporter
    ) -> None:
        channel: typing.Final = faker.pystr()

        @broker.subscriber(channel)
        async def handler(_: str) -> None: ...

        application: typing.Final = build_faststream_application_with_opentelemetry(broker)

        async with TestRedisBroker(broker):
            await broker.publish(faker.pystr(), channel=channel)

        telemetry_middlewares: typing.Final = [
            middleware
            for middleware in application.broker.middlewares  # type: ignore[union-attr]
            if isinstance(middleware, RedisTelemetryMiddleware)
        ]
        assert len(telemetry_middlewares) == 1
        assert sorted(span.name for span in span_exporter.get_finished_spans()) == [
            f"{channel} create",
            f"{channel} process",
            f"{channel} publish",
        ]

    def test_lifespan_bypasses_middleware(
        self, broker: RedisBroker, span_exporter: InMemorySpanExporter, magic_mock: MagicMock
    ) -> None:
        application: typing.Final = (
            FastStreamBootstrapper(FastStreamSettings())
            .configure_application(FastStreamConfig(broker=broker, lifespan=magic_mock))
            .configure_instruments(
                FastStreamOpentelemetryConfig(
                    opentelemetry_log_traces=True, opentelemetry_middleware_cls=RedisTelemetryMiddleware
                )
            )
            .bootstrap()
        )

        with mock.patch.object(broker, "start"), mock.patch.object(broker, "stop"), TestClient(app=application):
            assert magic_mock.called

        assert isinstance(application, AsgiFastStream)
        assert application.broker is broker
        assert not find_server_spans(span_exporter)


@pytest.mark.parametrize(
    ("scope", "expected_span_name", "expected_attributes"),
    [
        ({"path": "/health/", "method": "GET"}, "GET /health/", {"http.route": "/health/"}),
        ({"path": "/health/"}, "HTTP /health/", {"http.route": "/health/"}),
        ({"path": "/health", "method": "GET"}, "GET", {}),
        ({"path": "/wp-admin/", "method": "GET"}, "GET", {}),
        ({"method": "GET"}, "GET", {}),
    ],
)
def test_build_faststream_route_details_from_scope(
    scope: dict[str, str],
    expected_span_name: str,
    expected_attributes: dict[str, str],
) -> None:
    routes: typing.Final = [("/health/", mock.AsyncMock())]

    assert build_faststream_route_details_from_scope(scope, routes) == (expected_span_name, expected_attributes)
