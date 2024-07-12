from __future__ import annotations
import typing

import litestar
import litestar.testing
import pytest
from litestar.contrib import prometheus
from litestar.status_codes import HTTP_200_OK
from opentelemetry.instrumentation.redis import RedisInstrumentor
from sentry_sdk.integrations.opentelemetry.integration import OpenTelemetryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from microbootstrap.base import opentelemetry
from microbootstrap.base.logging.litestar import LitestarLoggingBootstrapper
from microbootstrap.base.sentry import SentryBootstrapper
from microbootstrap.bootstrappers import litestar as litestar_framework
from tests.conftest import CustomPrometheusController, simple_request_hook
from tests.settings_for_test import TestLitestarBootstrapSettings


if typing.TYPE_CHECKING:
    import httpx
    from litestar.handlers.http_handlers.base import HTTPRouteHandler
    from pytest_mock import MockerFixture


def test_frameworks__litestar__prometheus_integration(mocker: MockerFixture) -> None:
    litestar_prometheus_bootstrapper = litestar_framework.LitestarPrometheusBootstrapper(
        controller=CustomPrometheusController,
    )

    env_vars = {
        "prometheus_config": prometheus.PrometheusConfig(),
    }
    mocker.patch.object(TestLitestarBootstrapSettings, "_settings_build_values", return_value=env_vars)

    bootstrap_settings = TestLitestarBootstrapSettings()
    litestar_prometheus_bootstrapper.load_parameters(settings=bootstrap_settings)

    assert litestar_prometheus_bootstrapper.config == env_vars["prometheus_config"]

    litestar_prometheus_bootstrapper.initialize()
    litestar_prometheus_bootstrapper.teardown()


def test_frameworks__litestar__prometheus_integration__load__without_settings() -> None:
    litestar_prometheus_bootstrapper = litestar_framework.LitestarPrometheusBootstrapper(
        controller=CustomPrometheusController,
    )
    litestar_prometheus_bootstrapper.load_parameters()

    assert litestar_prometheus_bootstrapper


@pytest.mark.anyio()
async def test_frameworks__litestar(
    test_litestar_endpoint: HTTPRouteHandler,
    health_litestar_endpoint: HTTPRouteHandler,
    default_response_content: dict[str, str],
    mocker: MockerFixture,
) -> None:
    litestar_bootstrapper: typing.Final = litestar_framework.LitestarBootstrapper(
        logging_bootstrapper=LitestarLoggingBootstrapper(is_debug=False),
        sentry_bootstrapper=SentryBootstrapper(
            dsn="dsn",
            traces_sample_rate=2.0,
            environment="test",
            integrations=[
                OpenTelemetryIntegration(),
                RedisIntegration(),
            ],
        ),
        open_telemetry_bootstrapper=opentelemetry.LitestarOpenTelemetryBootstrapper(
            endpoint="localhost",
            namespace="test",
            service_name="test_service",
            service_version="1.9.2",
            container_name="test_app",
            add_system_metrics=True,
            instruments=[
                opentelemetry.OpenTelemetryInstrumentor(
                    instrumentor=RedisInstrumentor(),
                    additional_params={"request_hook": simple_request_hook},
                ),
            ],
        ),
    )

    env_vars: typing.Final = {
        "opentelemetry_endpoint": "localhost",
        "sentry_dsn": "https://testdsn@test.sentry.com/1",
    }
    mocker.patch.object(TestLitestarBootstrapSettings, "_settings_build_values", return_value=env_vars)

    bootstrap_settings: typing.Final = TestLitestarBootstrapSettings()
    litestar_bootstrapper.load_parameters(settings=bootstrap_settings)

    assert litestar_bootstrapper.sentry_bootstrapper.dsn == env_vars["sentry_dsn"]
    assert litestar_bootstrapper.open_telemetry_bootstrapper.endpoint == env_vars["opentelemetry_endpoint"]

    app_config: typing.Final = litestar_bootstrapper.initialize()
    app_config.route_handlers += [test_litestar_endpoint, health_litestar_endpoint]
    litestar_application: typing.Final = litestar.Litestar.from_config(app_config)

    with litestar.testing.TestClient(app=litestar_application) as test_litestar_client:
        response: typing.Final[httpx.Response] = test_litestar_client.get("/test")
        assert response.status_code == HTTP_200_OK
        assert response.json() == default_response_content

        health_response: typing.Final[httpx.Response] = test_litestar_client.get("/health")
        assert health_response.status_code == HTTP_200_OK
        assert health_response.json() == default_response_content

    litestar_bootstrapper.teardown()


@pytest.mark.anyio()
async def test_frameworks__litestar__custom_prometheus_bootstraped(test_litestar_endpoint: HTTPRouteHandler) -> None:
    litestar_bootstrapper: typing.Final = litestar_framework.LitestarBootstrapper(
        prometheus_bootstrapper=litestar_framework.LitestarPrometheusBootstrapper(
            controller=CustomPrometheusController,
        ),
    )
    app_config: typing.Final = litestar_bootstrapper.initialize()
    app_config.route_handlers.append(test_litestar_endpoint)
    litestar_application: typing.Final = litestar.Litestar.from_config(app_config)

    with litestar.testing.TestClient(app=litestar_application) as test_litestar_client:
        response: typing.Final = test_litestar_client.get("/custom-metrics")
    assert response.status_code == HTTP_200_OK

    litestar_bootstrapper.teardown()
