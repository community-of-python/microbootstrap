import typing
from unittest.mock import MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments import opentelemetry_instrument
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


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter: typing.Final = InMemorySpanExporter()

    def build_tracer_provider(*args: typing.Any, **kwargs: typing.Any) -> SdkTracerProvider:  # noqa: ANN401
        tracer_provider: typing.Final = SdkTracerProvider(*args, **kwargs)
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        return tracer_provider

    monkeypatch.setattr(opentelemetry_instrument, "SdkTracerProvider", build_tracer_provider)
    monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", MagicMock())
    return exporter


def find_server_span_names(span_exporter: InMemorySpanExporter) -> list[str]:
    return [span.name for span in span_exporter.get_finished_spans() if span.kind == SpanKind.SERVER]


def test_fastapi_opentelemetry_exclusions_do_not_silence_lookalike_routes(
    span_exporter: InMemorySpanExporter,
) -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(
            service_debug=False,
            opentelemetry_log_traces=True,
            opentelemetry_generate_health_check_spans=False,
        ),
    ).bootstrap()

    @application.get("/api/metrics-report")
    async def metrics_report() -> str:
        return "ok"

    @application.get("/api/health/details")
    async def health_details() -> str:
        return "ok"

    with TestClient(app=application) as client:
        for path in ("/metrics", "/health/", "/api/metrics-report", "/api/health/details"):
            assert client.get(path).status_code == status.HTTP_200_OK

    assert find_server_span_names(span_exporter) == ["GET /api/metrics-report", "GET /api/health/details"]


def test_fastapi_opentelemetry_metrics_path_is_derived_from_prometheus_settings(
    span_exporter: InMemorySpanExporter,
) -> None:
    application: typing.Final = FastApiBootstrapper(
        FastApiSettings(service_debug=False, opentelemetry_log_traces=True, prometheus_metrics_path="/custom-metrics"),
    ).bootstrap()

    with TestClient(app=application) as client:
        assert client.get("/custom-metrics").status_code == status.HTTP_200_OK

    assert find_server_span_names(span_exporter) == []
