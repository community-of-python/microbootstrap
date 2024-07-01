from __future__ import annotations
import typing

import pytest
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk import resources

from microbootstrap.helpers import opentelemetry
from tests import settings_for_test
from tests.conftest import simple_request_hook


if typing.TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import Response
    from pytest_mock import MockerFixture

    from microbootstrap.settings.base import BootstrapSettings


@pytest.mark.parametrize(
    "opentelemetry_bootstrapper_type",
    [
        opentelemetry.LitestarOpenTelemetryBootstrapper,
        opentelemetry.OpenTelemetryBootstrapper,
    ],
)
def test_helpers__opentelemetry(
    opentelemetry_bootstrapper_type: type[opentelemetry.OpenTelemetryBootstrapper[typing.Any]],
    fastapi_app: FastAPI,
    default_response_content: dict[str, str],
) -> None:
    open_telemetry_bootstrapper = opentelemetry_bootstrapper_type(
        endpoint="localhost.old",
        namespace="test",
        service_name="test_service",
        service_version="1.9.2",
        container_name="test_app",
        instruments=[
            opentelemetry.OpenTelemetryInstrumentor(
                instrumentor=RedisInstrumentor(),
                additional_params={"request_hook": simple_request_hook},
            ),
        ],
        add_system_metrics=True,
        prometheus_integration_bootstrapper=opentelemetry.OpenTelemetryPrometheusIntegrationBootstrapper(
            endpoint="localhost",
            basic_auth={
                "username": "username",
                "password": "password",
            },
            timeout=20,
        ),
    )
    if isinstance(open_telemetry_bootstrapper, opentelemetry.LitestarOpenTelemetryBootstrapper):
        open_telemetry_bootstrapper.exclude_urls = ["/health"]

    open_telemetry_bootstrapper.initialize()

    response: typing.Final[Response] = TestClient(fastapi_app).get("/test")
    assert response.json() == default_response_content

    open_telemetry_bootstrapper.teardown()


@pytest.mark.parametrize(
    "opentelemetry_bootstrapper_type",
    [
        opentelemetry.LitestarOpenTelemetryBootstrapper,
        opentelemetry.OpenTelemetryBootstrapper,
    ],
)
def test_helpers__opentelemetry__load(
    opentelemetry_bootstrapper_type: type[opentelemetry.OpenTelemetryBootstrapper[typing.Any]],
    fastapi_app: FastAPI,
    default_response_content: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    open_telemetry_bootstrapper = opentelemetry_bootstrapper_type()

    monkeypatch.setenv("bootstrap_namespace", "test")
    monkeypatch.setenv("service_name", "test_service")
    monkeypatch.setenv("ci_commit_tag", "1.9.2")
    monkeypatch.setenv("hostname", "test_app")
    monkeypatch.setenv("bootstrap_opentelemetry_endpoint", "localhost")
    monkeypatch.setenv("bootstrap_opentelemetry_add_system_metrics", "true")

    bootstrap_settings_type: type[BootstrapSettings] = settings_for_test.TestBootstrapSettings
    if isinstance(open_telemetry_bootstrapper, opentelemetry.LitestarOpenTelemetryBootstrapper):
        monkeypatch.setenv("bootstrap_opentelemetry_exclude_urls", '["/health"]')
        bootstrap_settings_type = settings_for_test.TestLitestarBootstrapSettings

    bootstrap_settings = bootstrap_settings_type(
        opentelemetry_instruments=[
            opentelemetry.OpenTelemetryInstrumentor(
                instrumentor=RedisInstrumentor(),
                additional_params={"request_hook": simple_request_hook},
            ),
        ],
    )
    open_telemetry_bootstrapper.load_parameters(settings=bootstrap_settings)

    assert open_telemetry_bootstrapper.endpoint == "localhost"
    assert open_telemetry_bootstrapper.add_system_metrics

    open_telemetry_bootstrapper.initialize()

    response: typing.Final[Response] = TestClient(fastapi_app).get("/test")
    assert response.json() == default_response_content

    open_telemetry_bootstrapper.teardown()


@pytest.mark.parametrize(
    "opentelemetry_bootstrapper_type",
    [
        opentelemetry.LitestarOpenTelemetryBootstrapper,
        opentelemetry.OpenTelemetryBootstrapper,
    ],
)
def test_helpers__opentelemetry__load__without_settings(
    opentelemetry_bootstrapper_type: type[opentelemetry.OpenTelemetryBootstrapper[typing.Any]],
) -> None:
    open_telemetry_bootstrapper = opentelemetry_bootstrapper_type(
        endpoint="localhost",
        namespace="test",
        service_name="test_service",
        service_version="1.9.2",
        container_name="test_app",
        instruments=[
            opentelemetry.OpenTelemetryInstrumentor(
                instrumentor=RedisInstrumentor(),
                additional_params={"request_hook": simple_request_hook},
            ),
        ],
        add_system_metrics=True,
        prometheus_integration_bootstrapper=opentelemetry.OpenTelemetryPrometheusIntegrationBootstrapper(
            endpoint="localhost",
            basic_auth={
                "username": "username",
                "password": "password",
            },
            timeout=20,
        ),
    )
    open_telemetry_bootstrapper.load_parameters()

    assert open_telemetry_bootstrapper


def test_helpers__opentelemetry__prometheus_integration(mocker: MockerFixture) -> None:
    prometheus_integration_bootstrapper = opentelemetry.OpenTelemetryPrometheusIntegrationBootstrapper(
        endpoint="localhost",
        basic_auth={
            "username": "username",
            "password": "password",
        },
        timeout=20,
    )
    prometheus_integration_bootstrapper.resource = resources.Resource.create()

    env_vars = {
        "prometheus_endpoint": "prometheus.test",
    }
    mocker.patch.object(settings_for_test.TestBootstrapSettings, "_settings_build_values", return_value=env_vars)

    bootstrap_settings = settings_for_test.TestBootstrapSettings()
    prometheus_integration_bootstrapper.load_parameters(settings=bootstrap_settings)

    assert prometheus_integration_bootstrapper.endpoint == env_vars["prometheus_endpoint"]

    prometheus_integration_bootstrapper.initialize()
    prometheus_integration_bootstrapper.teardown()
