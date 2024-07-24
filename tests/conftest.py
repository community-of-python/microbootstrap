from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import litestar
import pytest

from microbootstrap import OpentelemetryConfig, PrometheusConfig, SentryConfig


pytestmark = [pytest.mark.anyio]


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def default_litestar_app() -> litestar.Litestar:
    return litestar.Litestar()


@pytest.fixture()
def minimum_sentry_config() -> SentryConfig:
    class TestSentryConfig(SentryConfig):
        sentry_dsn: str = "https://examplePublicKey@o0.ingest.sentry.io/0"

    return TestSentryConfig()


@pytest.fixture()
def minimum_prometheus_config() -> PrometheusConfig:
    return PrometheusConfig()


@pytest.fixture()
def minimum_opentelemetry_config() -> OpentelemetryConfig:
    class TestOpentelemetryConfig(OpentelemetryConfig):
        service_name: str = "test-micro-service"
        service_version: str = "1.0.0"

        opentelemetry_endpoint: str = "/my-engdpoint"
        opentelemetry_namespace: str = "namespace"
        opentelemetry_container_name: str = "container-name"

    return TestOpentelemetryConfig()


@pytest.fixture()
def magic_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def async_mock() -> AsyncMock:
    return AsyncMock()
