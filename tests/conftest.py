from __future__ import annotations
import importlib
import typing
from unittest.mock import AsyncMock, MagicMock

import litestar
import pytest
from sentry_sdk.transport import Transport as SentryTransport

import microbootstrap.settings
from microbootstrap import (
    FastApiPrometheusConfig,
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
    from sentry_sdk.envelope import Envelope as SentryEnvelope


pytestmark = [pytest.mark.anyio]


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
        opentelemetry_endpoint="/my-engdpoint",
        opentelemetry_namespace="namespace",
        opentelemetry_container_name="container-name",
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
    monkeypatch.setattr(opentelemetry_instrument, "entry_points", MagicMock(retrun_value=[]))
