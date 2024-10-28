from __future__ import annotations
import importlib
import typing
from unittest.mock import AsyncMock, MagicMock

import litestar
import pytest

import microbootstrap.settings
from microbootstrap import (
    FastApiPrometheusConfig,
    LitestarPrometheusConfig,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
)
from microbootstrap.console_writer import ConsoleWriter
from microbootstrap.instruments.cors_instrument import CorsConfig
from microbootstrap.instruments.health_checks_instrument import HealthChecksConfig
from microbootstrap.instruments.prometheus_instrument import BasePrometheusConfig
from microbootstrap.instruments.swagger_instrument import SwaggerConfig
from microbootstrap.settings import BaseServiceSettings, ServerConfig


pytestmark = [pytest.mark.anyio]


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def default_litestar_app() -> litestar.Litestar:
    return litestar.Litestar()


@pytest.fixture
def minimal_sentry_config() -> SentryConfig:
    return SentryConfig(sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0")


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
        service_name="test-micro-service",
        service_version="1.0.0",
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
