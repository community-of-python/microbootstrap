from __future__ import annotations
import typing

from fastapi.testclient import TestClient
from sentry_sdk.integrations.opentelemetry.integration import OpenTelemetryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from microbootstrap.base.sentry import SentryBootstrapper
from tests.settings_for_test import TestBootstrapSettings


if typing.TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import Response
    from pytest_mock import MockerFixture


def test_helpers__sentry(
    fastapi_app: FastAPI,
    default_response_content: dict[str, str],
) -> None:
    sentry_bootstrapper = SentryBootstrapper(
        dsn="https://testdsn@test.sentry.com/1",
        traces_sample_rate=2.0,
        environment="test",
        integrations=[
            OpenTelemetryIntegration(),
            RedisIntegration(),
        ],
    )

    sentry_bootstrapper.initialize()

    response: typing.Final[Response] = TestClient(fastapi_app).get("/test")
    assert response.json() == default_response_content

    sentry_bootstrapper.teardown()


def test_helpers__sentry__load(
    fastapi_app: FastAPI,
    default_response_content: dict[str, str],
    mocker: MockerFixture,
) -> None:
    sentry_bootstrapper = SentryBootstrapper(dsn="dsn")

    env_vars = {
        "service_environment": "test",
        "sentry_dsn": "https://testdsn@test.sentry.com/1",
        "sentry_traces_sample_rate": 2.0,
    }
    mocker.patch.object(TestBootstrapSettings, "_settings_build_values", return_value=env_vars)

    bootstrap_settings = TestBootstrapSettings()
    sentry_bootstrapper.load_parameters(settings=bootstrap_settings)

    assert sentry_bootstrapper.traces_sample_rate == env_vars["sentry_traces_sample_rate"]

    sentry_bootstrapper.initialize()

    response: typing.Final[Response] = TestClient(fastapi_app).get("/test")
    assert response.json() == default_response_content

    sentry_bootstrapper.teardown()


def test_helpers__sentry__load__without_settings() -> None:
    sentry_bootstrapper = SentryBootstrapper(
        dsn="dsn",
        traces_sample_rate=2.0,
        environment="test",
        integrations=[
            OpenTelemetryIntegration(),
            RedisIntegration(),
        ],
    )
    sentry_bootstrapper.load_parameters()

    assert sentry_bootstrapper
