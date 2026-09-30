import typing
from unittest.mock import Mock, patch

import litestar
import pytest
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig as LitestarOpentelemetryConfig
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.testing import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Span, SpanKind

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import (
    LitestarBootstrapper,
    LitestarOpentelemetryInstrument,
    LitestarOpenTelemetryInstrumentationMiddleware,
    build_litestar_route_details_from_scope,
)
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryConfig


def _require_span_attributes(span: ReadableSpan) -> typing.Mapping[str, object]:
    assert span.attributes is not None
    return span.attributes


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


def test_litestar_opentelemetry_body_post_hooks_export_completed_spans(
    minimal_opentelemetry_config: OpentelemetryConfig,
    in_memory_otel: typing.Any,  # noqa: ANN401
) -> None:
    expected_request_count: typing.Final = 2
    server_hook_calls: list[tuple[Span, dict[str, typing.Any]]] = []
    client_hook_calls: list[tuple[Span, dict[str, typing.Any], dict[str, typing.Any]]] = []

    def server_request_hook(span: Span, scope: dict[str, typing.Any]) -> None:
        server_hook_calls.append((span, scope))
        span.set_attribute("test.server.scope_path", scope["path"])

    def client_message_hook(span: Span, scope: dict[str, typing.Any], message: dict[str, typing.Any]) -> None:
        client_hook_calls.append((span, scope, message))
        span.set_attribute("test.client.message_type", message["type"])

    instrument = LitestarOpentelemetryInstrument(minimal_opentelemetry_config)
    instrument.bootstrap()
    bootstrap_result = instrument.bootstrap_before()
    middleware = bootstrap_result["middleware"][0]
    assert isinstance(middleware, LitestarOpenTelemetryInstrumentationMiddleware)
    middleware.config.server_request_hook_handler = server_request_hook
    middleware.config.client_request_hook_handler = client_message_hook
    middleware.config.client_response_hook_handler = client_message_hook

    @litestar.post("/widgets/{widget_id:int}")
    async def create_widget(widget_id: int, data: dict[str, str]) -> dict[str, str | int]:
        return {"widget_id": widget_id, "name": data["name"]}

    application = litestar.Litestar(route_handlers=[create_widget], **bootstrap_result)
    with TestClient(app=application) as client:
        first_response = client.post("/widgets/41", json={"name": "first"})
        second_response = client.post("/widgets/42", json={"name": "second"})

    assert first_response.status_code == second_response.status_code == HTTP_201_CREATED
    assert [scope["path"] for _, scope in server_hook_calls] == ["/widgets/41", "/widgets/42"]
    assert all(message["type"].startswith("http.") for _, _, message in client_hook_calls)
    assert in_memory_otel.providers[-1].force_flush(timeout_millis=1_000)

    spans: list[ReadableSpan] = in_memory_otel.exporters[-1].get_finished_spans()
    server_spans = [
        span
        for span in spans
        if span.kind == SpanKind.SERVER
        and span.name == "POST /widgets/{widget_id}"
        and _require_span_attributes(span)["http.route"] == "/widgets/{widget_id}"
    ]
    assert len(server_spans) == expected_request_count
    assert all(_require_span_attributes(span)["http.status_code"] == HTTP_201_CREATED for span in server_spans)
    assert {_require_span_attributes(span)["test.server.scope_path"] for span in server_spans} == {
        "/widgets/41",
        "/widgets/42",
    }
    assert {_require_span_attributes(span).get("test.client.message_type") for span in spans} >= {
        "http.request",
        "http.response.start",
    }
    assert all(
        event.attributes is None or event.attributes.get("exception.type") != "TypeError"
        for span in spans
        for event in span.events
    )

    for server_span in server_spans:
        assert server_span.parent is None
        assert any(span.parent is not None and span.parent.span_id == server_span.context.span_id for span in spans)


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
