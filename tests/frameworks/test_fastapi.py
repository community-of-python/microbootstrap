from __future__ import annotations
import typing

from fastapi.testclient import TestClient
from sentry_sdk.integrations.opentelemetry.integration import OpenTelemetryIntegration
from starlette import status

from microbootstrap.base import opentelemetry
from microbootstrap.base.sentry import SentryBootstrapper
from microbootstrap.bootstrappers.fastapi import FastAPIBootstrapper


if typing.TYPE_CHECKING:
    import fastapi
    import httpx


def test_frameworks__fastapi(
    fastapi_app: fastapi.FastAPI,
    default_response_content: dict[str, str],
) -> None:
    fastapi_bootstrapper = FastAPIBootstrapper(
        app=fastapi_app,
        excluded_urls="/metrics",
        enable_prometheus_instrumentator=True,
        prometheus_instrumentator_params={
            "should_round_latency_decimals": True,
            "inprogress_labels": True,
        },
        sentry_bootstrapper=SentryBootstrapper(
            dsn="https://testdsn@test.sentry.com/1",
            traces_sample_rate=2.0,
            environment="test",
            integrations=[
                OpenTelemetryIntegration(),
            ],
        ),
        open_telemetry_bootstrapper=opentelemetry.OpenTelemetryBootstrapper(
            endpoint="localhost",
            namespace="test",
            service_name="test_service",
            service_version="1.9.2",
            container_name="test_app",
            add_system_metrics=True,
            prometheus_integration_bootstrapper=opentelemetry.OpenTelemetryPrometheusIntegrationBootstrapper(
                endpoint="localhost",
                basic_auth={
                    "username": "username",
                    "password": "password",
                },
                timeout=20,
            ),
        ),
    )

    fastapi_bootstrapper.initialize()

    response: typing.Final[httpx.Response] = TestClient(fastapi_app).get("/test")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == default_response_content

    fastapi_bootstrapper.teardown()


def test_frameworks__fastapi__without_app() -> None:
    fastapi_bootstrapper = FastAPIBootstrapper(excluded_urls="/metrics")
    fastapi_bootstrapper.initialize()

    assert fastapi_bootstrapper
