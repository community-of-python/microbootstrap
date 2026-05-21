import typing

import prometheus_client
from fastmcp import FastMCP
from starlette import status
from starlette.testclient import TestClient

from microbootstrap.bootstrappers.fastmcp import FastMcpBootstrapper
from microbootstrap.config.fastmcp import FastMcpConfig
from microbootstrap.instruments.health_checks_instrument import FastMcpHealthChecksConfig
from microbootstrap.instruments.logging_instrument import LoggingConfig
from microbootstrap.instruments.prometheus_instrument import FastMcpPrometheusConfig
from microbootstrap.middlewares.fastmcp import FastMcpLoggingMiddleware
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
        .configure_instrument(FastMcpHealthChecksConfig(health_checks_path=test_health_path))
        .bootstrap()
    )

    response: typing.Final = TestClient(application.http_app()).get(test_health_path)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["health_status"] is True


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
