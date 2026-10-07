import importlib.metadata
import typing
from unittest import mock

import prometheus_client
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from starlette import status
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from microbootstrap.bootstrappers.fastmcp import FastMcpBootstrapper, FastMcpOpentelemetryInstrument, KwargsFastMCP
from microbootstrap.config.fastmcp import FastMcpConfig
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksConfig
from microbootstrap.instruments.logging_instrument import LoggingConfig
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryConfig, OpenTelemetryInstrumentor
from microbootstrap.instruments.prometheus_instrument import FastMcpPrometheusConfig
from microbootstrap.middlewares.fastmcp import FastMcpLoggingMiddleware, FastMcpPrometheusMiddleware
from microbootstrap.settings import FastMcpSettings


def test_fastmcp_bootstrap_uses_service_metadata() -> None:
    test_settings: typing.Final = FastMcpSettings(
        service_name="test-mcp",
        service_description="Test MCP service",
        service_version="2.0.0",
    )

    application: typing.Final = FastMcpBootstrapper(test_settings).bootstrap()

    assert isinstance(application, FastMCP)
    assert application.name == test_settings.service_name
    assert application.instructions == test_settings.service_description
    assert application.version == test_settings.service_version


def test_fastmcp_configure_application_overrides_defaults() -> None:
    test_instructions: typing.Final = "Configured instructions"

    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_application(FastMcpConfig(instructions=test_instructions))
        .bootstrap()
    )

    assert application.instructions == test_instructions


def test_fastmcp_configure_instrument() -> None:
    bootstrapper: typing.Final = FastMcpBootstrapper(FastMcpSettings()).configure_instrument(
        LoggingConfig(logging_enabled=False),
    )

    application: typing.Final = bootstrapper.bootstrap()

    assert isinstance(application, FastMCP)


def test_fastmcp_logging_adds_mcp_middleware() -> None:
    application: typing.Final = FastMcpBootstrapper(FastMcpSettings()).bootstrap()

    assert any(isinstance(middleware, FastMcpLoggingMiddleware) for middleware in application.middleware)


def test_fastmcp_logging_middleware_can_be_disabled() -> None:
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(LoggingConfig(logging_turn_off_middleware=True))
        .bootstrap()
    )

    assert not any(isinstance(middleware, FastMcpLoggingMiddleware) for middleware in application.middleware)


def test_fastmcp_http_app_is_configured_through_fastmcp_interface() -> None:
    application: typing.Final = FastMcpBootstrapper(FastMcpSettings()).bootstrap()

    http_application: typing.Final = application.http_app(path="/api/mcp/", transport="http")

    assert any(getattr(route, "path", None) == "/api/mcp/" for route in http_application.routes)


def test_fastmcp_health_checks() -> None:
    test_health_path: typing.Final = "/test-health/"
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(HealthChecksConfig(health_checks_path=test_health_path))
        .bootstrap()
    )

    response: typing.Final = TestClient(application.http_app()).get(test_health_path)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["health_status"] is True


def test_fastmcp_health_checks_route_can_be_disabled_with_existing_enabled_flag() -> None:
    test_health_path: typing.Final = "/test-health/"
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            HealthChecksConfig(
                health_checks_path=test_health_path,
                health_checks_enabled=False,
            ),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(application.http_app()).get(test_health_path)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_fastmcp_prometheus() -> None:
    test_metrics_path: typing.Final = "/test-metrics"
    metrics_registry: typing.Final = prometheus_client.CollectorRegistry()
    prometheus_client.Counter(
        "fastmcp_test_requests_total",
        "FastMCP test requests.",
        registry=metrics_registry,
    ).inc()
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            FastMcpPrometheusConfig(
                prometheus_metrics_path=test_metrics_path,
                prometheus_registry=metrics_registry,
            ),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(application.http_app()).get(test_metrics_path)

    assert response.status_code == status.HTTP_200_OK
    assert b"fastmcp_test_requests_total 1.0" in response.content


def test_fastmcp_prometheus_counts_http_requests_by_route_template() -> None:
    test_metrics_path: typing.Final = "/test-metrics"
    test_health_path: typing.Final = "/test-health/"
    metrics_registry: typing.Final = prometheus_client.CollectorRegistry()
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            FastMcpPrometheusConfig(
                prometheus_metrics_path=test_metrics_path,
                prometheus_registry=metrics_registry,
                prometheus_custom_labels={"team": "platform"},
            ),
        )
        .configure_instrument(HealthChecksConfig(health_checks_path=test_health_path))
        .bootstrap()
    )

    with TestClient(application.http_app(path="/mcp")) as client:
        for _ in range(2):
            assert client.get(test_health_path).status_code == status.HTTP_200_OK
        client.get("/unknown")
        client.post("/mcp", json={})
        assert client.get(test_metrics_path).status_code == status.HTTP_200_OK

    def requests_total(method: str, status_group: str, handler: str) -> float | None:
        return metrics_registry.get_sample_value(
            "http_requests_total",
            {"method": method, "status": status_group, "handler": handler, "team": "platform"},
        )

    assert requests_total("GET", "2xx", test_health_path) == 2  # noqa: PLR2004
    assert requests_total("GET", "4xx", "none") == 1
    assert requests_total("POST", "4xx", "/mcp") == 1
    assert requests_total("GET", "2xx", test_metrics_path) is None


def test_fastmcp_prometheus_instrumentator_params_are_passed() -> None:
    metrics_registry: typing.Final = prometheus_client.CollectorRegistry()
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            FastMcpPrometheusConfig(
                prometheus_registry=metrics_registry,
                prometheus_instrumentator_params={"should_group_status_codes": False, "excluded_handlers": []},
            ),
        )
        .bootstrap()
    )

    with TestClient(application.http_app()) as client:
        assert client.get("/metrics").status_code == status.HTTP_200_OK

    # excluded_handlers is overridden, so the metrics route itself is counted, with the exact status code
    assert (
        metrics_registry.get_sample_value(
            "http_requests_total",
            {"method": "GET", "status": "200", "handler": "/metrics"},
        )
        == 1
    )


async def test_fastmcp_prometheus_counts_tool_calls() -> None:
    metrics_registry: typing.Final = prometheus_client.CollectorRegistry()
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            FastMcpPrometheusConfig(
                prometheus_registry=metrics_registry, prometheus_custom_labels={"team": "platform"}
            ),
        )
        .bootstrap()
    )

    @application.tool
    def echo(text: str) -> str:
        return text

    @application.tool
    def failing() -> str:
        msg: typing.Final = "boom"
        raise ValueError(msg)

    async with Client(application) as client:
        for _ in range(2):
            await client.call_tool("echo", {"text": "hi"})
        with pytest.raises(ToolError):
            await client.call_tool("failing", {})

    def tool_calls_total(tool: str, call_status: str) -> float | None:
        return metrics_registry.get_sample_value(
            "fastmcp_tool_calls_total",
            {"tool": tool, "status": call_status, "team": "platform"},
        )

    assert tool_calls_total("echo", "success") == 2  # noqa: PLR2004
    assert tool_calls_total("echo", "error") is None
    assert tool_calls_total("failing", "error") == 1
    assert (
        metrics_registry.get_sample_value(
            "fastmcp_tool_call_duration_seconds_count",
            {"tool": "failing", "team": "platform"},
        )
        == 1
    )


def test_fastmcp_prometheus_tool_metrics_can_be_disabled() -> None:
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            FastMcpPrometheusConfig(
                prometheus_registry=prometheus_client.CollectorRegistry(),
                prometheus_tool_metrics=False,
            ),
        )
        .bootstrap()
    )

    assert not any(isinstance(middleware, FastMcpPrometheusMiddleware) for middleware in application.middleware)


def test_fastmcp_prometheus_route_can_be_disabled() -> None:
    test_metrics_path: typing.Final = "/test-metrics"
    application: typing.Final = (
        FastMcpBootstrapper(FastMcpSettings())
        .configure_instrument(
            FastMcpPrometheusConfig(
                prometheus_metrics_path=test_metrics_path,
                prometheus_register_route=False,
            ),
        )
        .bootstrap()
    )

    response: typing.Final = TestClient(application.http_app()).get(test_metrics_path)

    assert response.status_code == status.HTTP_404_NOT_FOUND


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
    monkeypatch.delenv(OTEL_SEMCONV_STABILITY_OPT_IN, raising=False)
    monkeypatch.delenv("OTEL_PYTHON_STARLETTE_EXCLUDED_URLS", raising=False)
    monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS", raising=False)
    return exporter


def build_fastmcp_application_with_opentelemetry(**opentelemetry_params: typing.Any) -> FastMCP[typing.Any]:  # noqa: ANN401
    return FastMcpBootstrapper(
        FastMcpSettings(service_debug=False, opentelemetry_log_traces=True, **opentelemetry_params),
    ).bootstrap()


def find_server_spans(span_exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [span for span in span_exporter.get_finished_spans() if span.kind == SpanKind.SERVER]


def count_opentelemetry_middlewares(http_application: Starlette) -> int:
    return sum(
        typing.cast("object", middleware.cls) is OpenTelemetryMiddleware
        for middleware in http_application.user_middleware
    )


def test_fastmcp_settings_include_opentelemetry_config() -> None:
    assert set(OpentelemetryConfig.model_fields) <= set(FastMcpSettings.model_fields)


def test_fastmcp_opentelemetry_creates_tracer_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", mock.Mock())
    bootstrapper: typing.Final = FastMcpBootstrapper(
        FastMcpSettings(service_debug=False, opentelemetry_log_traces=True),
    )

    bootstrapper.bootstrap()

    opentelemetry_instrument_obj: typing.Final = next(
        instrument
        for instrument in bootstrapper.instrument_box.instruments
        if isinstance(instrument, FastMcpOpentelemetryInstrument)
    )
    assert opentelemetry_instrument_obj.is_ready()
    assert isinstance(opentelemetry_instrument_obj.tracer_provider, SdkTracerProvider)


def test_fastmcp_opentelemetry_is_not_ready_without_settings() -> None:
    application: typing.Final = FastMcpBootstrapper(FastMcpSettings(service_debug=False)).bootstrap()

    assert isinstance(application, KwargsFastMCP)
    assert not any(
        isinstance(getattr(postprocessor, "__self__", None), FastMcpOpentelemetryInstrument)
        for postprocessor in application.http_application_postprocessors
    )
    assert count_opentelemetry_middlewares(application.http_app()) == 0


class TestFastMcpHttpOpentelemetry:
    @pytest.mark.parametrize(
        ("semconv_opt_in", "expected_status_attributes"),
        [
            (None, {"http.status_code"}),
            ("http", {"http.response.status_code"}),
            ("http/dup", {"http.status_code", "http.response.status_code"}),
        ],
    )
    def test_health_check_server_span(
        self,
        monkeypatch: pytest.MonkeyPatch,
        span_exporter: InMemorySpanExporter,
        semconv_opt_in: str | None,
        expected_status_attributes: set[str],
    ) -> None:
        if semconv_opt_in is not None:
            monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, semconv_opt_in)
        application: typing.Final = build_fastmcp_application_with_opentelemetry()

        response: typing.Final = TestClient(application.http_app()).get("/health/")

        assert response.status_code == status.HTTP_200_OK
        server_spans: typing.Final = find_server_spans(span_exporter)
        assert [span.name for span in server_spans] == ["GET /health/"]
        assert server_spans[0].attributes
        assert server_spans[0].attributes["http.route"] == "/health/"
        assert {
            attribute_name: server_spans[0].attributes[attribute_name]
            for attribute_name in ("http.status_code", "http.response.status_code")
            if attribute_name in server_spans[0].attributes
        } == dict.fromkeys(expected_status_attributes, status.HTTP_200_OK)

    def test_metrics_are_excluded_by_default(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry()

        response: typing.Final = TestClient(application.http_app()).get("/metrics")

        assert response.status_code == status.HTTP_200_OK
        assert find_server_spans(span_exporter) == []

    def test_custom_exclude_urls(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry(
            opentelemetry_exclude_urls=["/custom"],
        )
        client: typing.Final = TestClient(application.http_app())

        client.get("/custom")
        client.get("/health/")

        assert [span.name for span in find_server_spans(span_exporter)] == ["GET /health/"]

    def test_exclude_urls_from_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        span_exporter: InMemorySpanExporter,
    ) -> None:
        monkeypatch.setenv("OTEL_PYTHON_STARLETTE_EXCLUDED_URLS", "/health/")
        application: typing.Final = build_fastmcp_application_with_opentelemetry()
        client: typing.Final = TestClient(application.http_app())

        client.get("/health/")
        client.get("/missing")

        assert [span.name for span in find_server_spans(span_exporter)] == ["GET"]

    def test_health_check_spans_can_be_disabled(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry(
            opentelemetry_generate_health_check_spans=False,
        )
        client: typing.Final = TestClient(application.http_app())

        client.get("/health/")
        client.get("/missing")

        assert [span.name for span in find_server_spans(span_exporter)] == ["GET"]

    def test_exclusions_do_not_silence_lookalike_routes(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry(
            opentelemetry_generate_health_check_spans=False,
        )

        @application.custom_route("/api/metrics-report", methods=["GET"])
        async def metrics_report(_: Request) -> PlainTextResponse:
            return PlainTextResponse("ok")

        @application.custom_route("/api/health/details", methods=["GET"])
        async def health_details(_: Request) -> PlainTextResponse:
            return PlainTextResponse("ok")

        client: typing.Final = TestClient(application.http_app())
        for path in ("/metrics", "/health/", "/health", "/api/metrics-report", "/api/health/details"):
            client.get(path, follow_redirects=False)

        assert [span.name for span in find_server_spans(span_exporter)] == [
            "GET /api/metrics-report",
            "GET /api/health/details",
        ]

    def test_metrics_path_is_derived_from_prometheus_settings(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry(
            prometheus_metrics_path="/custom-metrics",
        )
        client: typing.Final = TestClient(application.http_app())

        assert client.get("/custom-metrics").status_code == status.HTTP_200_OK
        client.get("/metrics")

        assert [span.name for span in find_server_spans(span_exporter)] == ["GET"]

    def test_unknown_path_has_no_route(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry()

        response: typing.Final = TestClient(application.http_app()).get("/wp-admin/setup.php")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        server_spans: typing.Final = find_server_spans(span_exporter)
        assert [span.name for span in server_spans] == ["GET"]
        assert server_spans[0].attributes
        assert "http.route" not in server_spans[0].attributes
        assert server_spans[0].attributes["http.status_code"] == status.HTTP_404_NOT_FOUND

    def test_mcp_endpoint_has_route(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry()

        with TestClient(application.http_app()) as client:
            client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={"accept": "application/json, text/event-stream"},
            )

        server_spans: typing.Final = [span for span in find_server_spans(span_exporter) if span.name == "POST /mcp"]
        assert len(server_spans) == 1
        assert server_spans[0].attributes
        assert server_spans[0].attributes["http.route"] == "/mcp"

    def test_each_http_app_is_instrumented_once(self, span_exporter: InMemorySpanExporter) -> None:
        application: typing.Final = build_fastmcp_application_with_opentelemetry()

        first_http_application: typing.Final = application.http_app()
        second_http_application: typing.Final = application.http_app(path="/other-mcp")

        assert first_http_application is not second_http_application
        for http_application in (first_http_application, second_http_application):
            assert count_opentelemetry_middlewares(http_application) == 1
            assert getattr(http_application, "_is_instrumented_by_opentelemetry", False)
            TestClient(http_application).get("/health/")
        assert [span.name for span in find_server_spans(span_exporter)] == ["GET /health/", "GET /health/"]

    def test_starlette_instrumentor_entry_point_does_not_duplicate_middleware(
        self,
        monkeypatch: pytest.MonkeyPatch,
        span_exporter: InMemorySpanExporter,
    ) -> None:
        starlette_entry_point: typing.Final = next(
            entry_point
            for entry_point in importlib.metadata.entry_points(group="opentelemetry_instrumentor")
            if entry_point.name == "starlette"
        )
        monkeypatch.setattr(opentelemetry_instrument, "entry_points", mock.Mock(return_value=[starlette_entry_point]))
        try:
            application: typing.Final = build_fastmcp_application_with_opentelemetry()
            assert StarletteInstrumentor().is_instrumented_by_opentelemetry

            http_application: typing.Final = application.http_app()
            TestClient(http_application).get("/health/")
        finally:
            StarletteInstrumentor().uninstrument()

        assert count_opentelemetry_middlewares(http_application) == 1
        assert getattr(http_application, "_is_instrumented_by_opentelemetry", False)
        assert [span.name for span in find_server_spans(span_exporter)] == ["GET /health/"]

    def test_already_instrumented_http_app_is_skipped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        span_exporter: InMemorySpanExporter,
    ) -> None:
        original_http_app: typing.Final = FastMCP.http_app

        def instrumented_http_app(self: FastMCP[typing.Any], *args: typing.Any, **kwargs: typing.Any) -> Starlette:  # noqa: ANN401
            http_application: typing.Final = original_http_app(self, *args, **kwargs)
            StarletteInstrumentor.instrument_app(http_application)
            return http_application

        monkeypatch.setattr(FastMCP, "http_app", instrumented_http_app)
        application: typing.Final = build_fastmcp_application_with_opentelemetry()

        http_application: typing.Final = application.http_app()

        assert count_opentelemetry_middlewares(http_application) == 1
        assert span_exporter.get_finished_spans() == ()

    def test_instrumentors_are_applied_and_torn_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", mock.Mock())
        httpx_instrumentor: typing.Final = HTTPXClientInstrumentor()
        bootstrapper: typing.Final = FastMcpBootstrapper(FastMcpSettings(service_debug=False)).configure_instrument(
            OpentelemetryConfig(
                opentelemetry_log_traces=True,
                opentelemetry_instrumentors=[OpenTelemetryInstrumentor(httpx_instrumentor)],
            ),
        )

        bootstrapper.bootstrap()
        assert httpx_instrumentor.is_instrumented_by_opentelemetry

        bootstrapper.teardown()
        assert not httpx_instrumentor.is_instrumented_by_opentelemetry
