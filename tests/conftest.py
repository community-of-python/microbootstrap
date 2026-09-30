from __future__ import annotations
import dataclasses
import importlib
import typing
from unittest.mock import AsyncMock, MagicMock

import litestar
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY
from sentry_sdk.transport import Transport as SentryTransport

import microbootstrap.settings
from microbootstrap import (
    FastApiPrometheusConfig,
    FastStreamPrometheusConfig,
    LitestarPrometheusConfig,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
)
from microbootstrap.console_writer import ConsoleWriter
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.cors_instrument import CorsConfig
from microbootstrap.instruments.health_checks_instrument import HealthChecksConfig
from microbootstrap.instruments.prometheus_instrument import BasePrometheusConfig
from microbootstrap.instruments.swagger_instrument import SwaggerConfig
from microbootstrap.settings import BaseServiceSettings, ServerConfig


if typing.TYPE_CHECKING:
    from opentelemetry.sdk.resources import Resource
    from sentry_sdk.envelope import Envelope as SentryEnvelope


pytestmark = [pytest.mark.anyio]


@dataclasses.dataclass
class InMemoryOpenTelemetry:
    exporters: list[InMemorySpanExporter] = dataclasses.field(default_factory=list)
    exporter_calls: list[tuple[tuple[object, ...], dict[str, object]]] = dataclasses.field(default_factory=list)
    providers: list[TracerProvider] = dataclasses.field(default_factory=list)

    @staticmethod
    def _flush_provider(provider: TracerProvider) -> None:
        if not provider.force_flush(timeout_millis=1_000):
            raise AssertionError("force_flush returned False")

    @staticmethod
    def _record_cleanup_failure(
        operation: str,
        cleanup: typing.Callable[[], None],
        failures: list[tuple[str, Exception]],
    ) -> None:
        try:
            cleanup()
        except Exception as exc:  # noqa: BLE001 - fixture cleanup must continue for every owned provider.
            failures.append((operation, exc))

    def cleanup(self) -> None:
        failures: list[tuple[str, Exception]] = []
        for provider_index, provider in enumerate(self.providers):

            def flush_provider(selected_provider: TracerProvider = provider) -> None:
                self._flush_provider(selected_provider)

            self._record_cleanup_failure(
                f"provider {provider_index} force_flush",
                flush_provider,
                failures,
            )

        for provider_index, provider in enumerate(self.providers):
            self._record_cleanup_failure(f"provider {provider_index} shutdown", provider.shutdown, failures)

        if failures:
            details = "; ".join(f"{operation}: {failure!r}" for operation, failure in failures)
            raise RuntimeError(f"OpenTelemetry fixture cleanup failed: {details}") from failures[0][1]


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def default_litestar_app() -> litestar.Litestar:
    return litestar.Litestar()


class MockSentryTransport(SentryTransport):
    def capture_envelope(self, envelope: SentryEnvelope) -> None: ...


@pytest.fixture
def minimal_sentry_config() -> SentryConfig:
    return SentryConfig(
        sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
        sentry_tags={"test": "test"},
        sentry_additional_params={"transport": MockSentryTransport()},
    )


@pytest.fixture
def minimal_logging_config() -> LoggingConfig:
    return LoggingConfig(service_debug=False)


@pytest.fixture
def minimal_base_prometheus_config() -> BasePrometheusConfig:
    return BasePrometheusConfig()


@pytest.fixture
def minimal_fastapi_prometheus_config() -> FastApiPrometheusConfig:
    return FastApiPrometheusConfig()


@pytest.fixture
def minimal_litestar_prometheus_config() -> LitestarPrometheusConfig:
    return LitestarPrometheusConfig()


@pytest.fixture
def minimal_faststream_prometheus_config() -> FastStreamPrometheusConfig:
    return FastStreamPrometheusConfig()


@pytest.fixture
def minimal_swagger_config() -> SwaggerConfig:
    return SwaggerConfig()


@pytest.fixture
def minimal_cors_config() -> CorsConfig:
    return CorsConfig(cors_allowed_origins=["*"])


@pytest.fixture
def minimal_health_checks_config() -> HealthChecksConfig:
    return HealthChecksConfig()


@pytest.fixture
def minimal_opentelemetry_config() -> OpentelemetryConfig:
    return OpentelemetryConfig(
        opentelemetry_endpoint="/my-endpoint",
        opentelemetry_namespace="namespace",
        opentelemetry_container_name="container-name",
        opentelemetry_generate_health_check_spans=False,
    )


@pytest.fixture
def minimal_server_config() -> ServerConfig:
    return ServerConfig()


@pytest.fixture
def base_settings() -> BaseServiceSettings:
    return BaseServiceSettings()


@pytest.fixture
def magic_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture
def async_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def console_writer() -> ConsoleWriter:
    return ConsoleWriter(writer_enabled=False)


@pytest.fixture
def reset_reloaded_settings_module() -> typing.Iterator[None]:
    yield
    importlib.reload(microbootstrap.settings)


@pytest.fixture(autouse=True)
def patch_out_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opentelemetry_instrument, "entry_points", MagicMock(return_value=[]))


@pytest.fixture(autouse=True)
def in_memory_otel(monkeypatch: pytest.MonkeyPatch) -> typing.Iterator[InMemoryOpenTelemetry]:
    """Keep real SDK providers/processors while replacing OTLP delivery at its boundary."""
    harness = InMemoryOpenTelemetry()

    def create_exporter(*args: object, **kwargs: object) -> InMemorySpanExporter:
        harness.exporter_calls.append((args, kwargs))
        exporter = InMemorySpanExporter()
        harness.exporters.append(exporter)
        return exporter

    def create_provider(*, resource: Resource | None = None) -> TracerProvider:
        provider = TracerProvider(resource=resource)
        harness.providers.append(provider)
        return provider

    monkeypatch.setattr(opentelemetry_instrument, "OTLPSpanExporter", create_exporter)
    monkeypatch.setattr(opentelemetry_instrument, "SdkTracerProvider", create_provider)

    try:
        yield harness
    finally:
        harness.cleanup()


@pytest.fixture(autouse=True)
def clean_prometheus_registry() -> None:
    REGISTRY._names_to_collectors.clear()  # noqa: SLF001
    REGISTRY._collector_to_names.clear()  # noqa: SLF001
