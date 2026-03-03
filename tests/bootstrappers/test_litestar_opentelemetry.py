import typing
from unittest.mock import Mock, patch

import litestar
import pytest
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig as LitestarOpentelemetryConfig
from litestar.status_codes import HTTP_200_OK
from litestar.testing import TestClient

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import (
    LitestarBootstrapper,
    LitestarOpentelemetryInstrument,
    LitestarOpenTelemetryInstrumentationMiddleware,
    build_litestar_route_details_from_scope,
)
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryConfig


@pytest.mark.parametrize(
    ("scope", "expected_span_name", "expected_attributes"),
    [
        (
            {
                "path": "/users/123",
                "path_template": "/users/{user_id}",
                "method": "GET",
            },
            "GET /users/{user_id}",
            {"http.route": "/users/{user_id}"},
        ),
        (
            {
                "path": "/users/123",
                "method": "POST",
            },
            "POST /users/123",
            {"http.route": "/users/123"},
        ),
        (
            {
                "path": "/test",
            },
            "HTTP /test",
            {"http.route": "/test"},
        ),
        (
            {
                "path": "",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {
                "path": " ",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {
                "path_template": "",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {
                "path_template": " ",
            },
            "HTTP",
            {"http.route": ""},
        ),
        (
            {},
            "HTTP",
            {},
        ),
        (
            {"method": "GET"},
            "GET",
            {},
        ),
        (
            {
                "path": "/users/123",
                "path_template": "/users/{user_id}",
            },
            "HTTP /users/{user_id}",
            {"http.route": "/users/{user_id}"},
        ),
    ],
)
def test_build_litestar_route_details_from_scope(
    scope: dict[str, str],
    expected_span_name: str,
    expected_attributes: dict[str, str],
) -> None:
    span_name, attributes = build_litestar_route_details_from_scope(scope)  # type: ignore[arg-type]

    assert span_name == expected_span_name
    assert attributes == expected_attributes


def test_litestar_opentelemetry_instrument_uses_custom_middleware(
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    opentelemetry_instrument: typing.Final = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)
    opentelemetry_instrument.bootstrap()

    bootstrap_result: typing.Final = opentelemetry_instrument.bootstrap_before()

    assert "middleware" in bootstrap_result
    assert len(bootstrap_result["middleware"]) == 1

    middleware_config: typing.Final = bootstrap_result["middleware"][0].config
    assert middleware_config.middleware.middleware == LitestarOpenTelemetryInstrumentationMiddleware


@pytest.mark.parametrize(
    ("path", "expected_span_name", "expected_path_template"),
    [
        ("/users/123", "GET /users/{user_id}", "/users/{user_id}"),
        ("/users/", "GET /users/", "/users"),
        ("/", "GET /", "/"),
    ],
)
def test_litestar_opentelemetry_integration_with_path_templates(
    path: str,
    expected_span_name: str,
    expected_path_template: str,
    minimal_opentelemetry_config: OpentelemetryConfig,
) -> None:
    @litestar.get("/users/{user_id:int}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"user_id": user_id}

    @litestar.get("/users/")
    async def list_users() -> dict[str, str]:
        return {"message": "list of users"}

    @litestar.get("/")
    async def root() -> dict[str, str]:
        return {"message": "root"}

    with patch("microbootstrap.bootstrappers.litestar.build_litestar_route_details_from_scope") as mock_function:
        mock_function.return_value = (expected_span_name, {"http.route": path})

        application: typing.Final = (
            LitestarBootstrapper(LitestarSettings())
            .configure_instrument(minimal_opentelemetry_config)
            .configure_application(LitestarConfig(route_handlers=[get_user, list_users, root]))
            .bootstrap()
        )

        with TestClient(app=application) as client:
            response: typing.Final = client.get(path)
        assert response.status_code == HTTP_200_OK
        assert mock_function.called
        assert mock_function.call_args_list[0].args[0].get("path_template") == expected_path_template


def test_litestar_opentelemetry_middleware_initialization() -> None:
    mock_app: typing.Final = Mock()

    mock_config: typing.Final = Mock(spec=LitestarOpentelemetryConfig)
    mock_config.scopes = ["http"]
    mock_config.exclude = []
    mock_config.exclude_opt_key = None
    mock_config.client_request_hook_handler = None
    mock_config.client_response_hook_handler = None
    mock_config.exclude_urls_env_key = None
    mock_config.meter = None
    mock_config.meter_provider = None
    mock_config.server_request_hook_handler = None
    mock_config.tracer_provider = None

    middleware: typing.Final = LitestarOpenTelemetryInstrumentationMiddleware(config=mock_config)

    assert middleware.config == mock_config
    otel_middleware = middleware.create_open_telemetry_middleware(mock_app)
    assert otel_middleware is not None
